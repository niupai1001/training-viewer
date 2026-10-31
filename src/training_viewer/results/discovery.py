"""从训练输出目录发现结果图片，作为事件关联的补充通道。

文件名和目录推断只作为**候选**，每条都标记 `requires_confirmation=True`；
Viewer 不会因为猜出 `_pred/_label` 就把它当作科学结论。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_ROLE_TOKENS = {
    "prediction": ("prediction", "pred", "output", "logits"),
    "ground_truth": ("ground_truth", "groundtruth", "gt", "label", "mask", "target"),
    "input": ("input", "image", "rgb", "original"),
}
_EPOCH_RE = re.compile(r"(?:epoch|ep)[-_]?(\d+)", re.IGNORECASE)


def _role_for(relative: Path) -> tuple[str | None, str]:
    tokens = " ".join(part.lower() for part in relative.parts)
    stem = relative.stem.lower()
    for role, words in _ROLE_TOKENS.items():
        if any(word in stem for word in words):
            return role, "filename-hint"
    for role, words in _ROLE_TOKENS.items():
        if any(word in tokens for word in words):
            return role, "path-convention"
    return None, "low"


def _sample_id(relative: Path) -> str:
    stem = _EPOCH_RE.sub("", relative.stem)
    for word in ("prediction", "pred", "ground_truth", "groundtruth", "gt", "label", "mask", "input", "rgb"):
        stem = re.sub(rf"[-_]?{word}[-_]?", "-", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[-_]+", "-", stem).strip("-_")
    return stem or relative.stem


def discover_result_files(run_directory: Path, known_paths: set[str] | None = None) -> list[dict]:
    if not run_directory.is_dir():
        return []
    known_paths = known_paths or set()
    candidates: list[dict] = []
    scanned = 0
    for path in sorted(run_directory.rglob("*")):
        scanned += 1
        if scanned > 20000 or len(candidates) >= 5000:
            break
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if any(part.startswith(".") for part in path.relative_to(run_directory).parts):
            continue
        relative = path.relative_to(run_directory)
        if relative.as_posix() in known_paths:
            continue
        role, confidence = _role_for(relative)
        epoch_match = _EPOCH_RE.search(relative.stem)
        candidates.append(
            {
                "path": relative.as_posix(),
                "role_guess": role,
                "sample_id": _sample_id(relative),
                "epoch": int(epoch_match.group(1)) if epoch_match else None,
                "confidence": confidence,
                "requires_confirmation": True,
                "note": "由目录/文件名推断，未经过事件或用户确认；确认前不应作为指标结论。",
            }
        )
    return candidates


def discover_tensorboard_images(
    run_directory: Path, cache_root: Path, run_id: str
) -> list[dict]:
    """用 TensorBoard 官方 loader 提取 image 事件，缓存为 Viewer 数据目录中的 PNG。"""
    try:
        from tensorboard.backend.event_processing.event_file_loader import EventFileLoader
    except ImportError:
        return []
    event_files = sorted(
        path
        for path in run_directory.glob("events.out.tfevents.*")
        if path.is_file() and not path.is_symlink()
    )
    if not event_files:
        return []
    cache_directory = cache_root / run_id
    manifest_path = cache_directory / "manifest.json"
    signature = [
        [path.name, path.stat().st_size, path.stat().st_mtime] for path in event_files
    ]
    if manifest_path.is_file():
        try:
            cached = json.loads(manifest_path.read_text(encoding="utf-8"))
            if cached.get("signature") == signature:
                return cached.get("candidates", [])
        except (OSError, ValueError):
            pass
    cache_directory.mkdir(parents=True, exist_ok=True)
    candidates: list[dict] = []
    for event_file in event_files:
        try:
            loader = EventFileLoader(str(event_file))
            for event in loader.Load():
                if not event.HasField("summary"):
                    continue
                for value in event.summary.value:
                    encoded = b""
                    if value.HasField("image"):
                        encoded = value.image.encoded_image_string
                    elif value.HasField("tensor") and len(value.tensor.string_val) >= 1:
                        # TensorBoard 新版 data_compat 把 legacy image 迁移成
                        # DT_STRING tensor：[height, width, encoded_image]。
                        encoded = value.tensor.string_val[-1]
                    if not encoded:
                        continue
                    digest = hashlib.sha1(encoded).hexdigest()[:24]
                    filename = f"{digest}.png"
                    target = cache_directory / filename
                    if not target.is_file():
                        target.write_bytes(encoded)
                    tag_path = Path(value.tag.replace("\\", "/"))
                    role, confidence = _role_for(tag_path)
                    candidates.append(
                        {
                            "path": value.tag,
                            "role_guess": role,
                            "sample_id": tag_path.stem or value.tag,
                            "epoch": int(event.step) if event.step else None,
                            "confidence": "event-image",
                            "requires_confirmation": False,
                            "note": "来自 TensorBoard image 事件；已缓存到 Viewer 数据目录，原始事件文件未修改。",
                            "cache_file": filename,
                        }
                    )
        except Exception:  # noqa: BLE001 - 半写事件文件不应让接口失败
            continue
    manifest_path.write_text(
        json.dumps({"signature": signature, "candidates": candidates}, ensure_ascii=False),
        encoding="utf-8",
    )
    return candidates
