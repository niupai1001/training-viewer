"""逻辑实验身份：把多个原始日志文件归并为一个可审计的 LogicalRun。

原始文件永不修改；用户确认的归并规则保存在 Viewer 数据目录的
`logical_runs.json`。默认不按目录自动合并，避免把不同 seed/数据集/重启实验
静默变成一个 Run。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..source_adapters.base import DiscoveredRun


@dataclass(frozen=True)
class LogicalRunOverride:
    logical_run_id: str
    name: str
    files: list[str]
    reason: str
    created_at: str

    @classmethod
    def from_dict(cls, payload: dict) -> "LogicalRunOverride":
        files = payload.get("files")
        if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
            raise ValueError("files 必须是绝对路径字符串列表")
        if not isinstance(payload.get("logical_run_id"), str) or not payload["logical_run_id"].strip():
            raise ValueError("logical_run_id 不能为空")
        if not isinstance(payload.get("name"), str) or not payload["name"].strip():
            raise ValueError("name 不能为空")
        return cls(
            logical_run_id=payload["logical_run_id"].strip(),
            name=payload["name"].strip(),
            files=[str(Path(item).resolve()) for item in files],
            reason=str(payload.get("reason") or "user-confirmed"),
            created_at=str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )


class LogicalRunOverrideStore:
    """Viewer 数据目录中的归并覆盖规则；不写入训练日志目录。"""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[LogicalRunOverride]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(f"无法读取逻辑实验映射 {self.path}：{error}") from error
        items = payload.get("overrides", []) if isinstance(payload, dict) else []
        return [LogicalRunOverride.from_dict(item) for item in items]

    def save(self, overrides: list[LogicalRunOverride]) -> None:
        payload = {
            "schema_version": "1.0",
            "overrides": [asdict(item) for item in overrides],
        }
        temporary = self.path.with_name(self.path.name + ".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def upsert(self, override: LogicalRunOverride) -> list[LogicalRunOverride]:
        overrides = [item for item in self.load() if item.logical_run_id != override.logical_run_id]
        overrides.append(override)
        self.save(overrides)
        return overrides

    def delete(self, logical_run_id: str) -> list[LogicalRunOverride]:
        overrides = [item for item in self.load() if item.logical_run_id != logical_run_id]
        self.save(overrides)
        return overrides

    def resolve(self, discovered_runs: list[DiscoveredRun]) -> tuple[list[DiscoveredRun], list[dict]]:
        """应用明确覆盖；无覆盖的文件保持独立。返回结果和审计说明。"""
        overrides = self.load()
        file_to_override: dict[str, LogicalRunOverride] = {}
        for override in overrides:
            for file_path in override.files:
                file_to_override[str(Path(file_path).resolve())] = override
        groups: dict[str, list[DiscoveredRun]] = {}
        passthrough: list[DiscoveredRun] = []
        audit: list[dict] = []
        for discovered in discovered_runs:
            matched: set[str] = set()
            for log_file in discovered.log_files:
                override = file_to_override.get(str(log_file.file_path.resolve()))
                if override is not None:
                    matched.add(override.logical_run_id)
            if not matched:
                passthrough.append(discovered)
                continue
            if len(matched) > 1:
                audit.append(
                    {
                        "run_id": discovered.run_id,
                        "action": "rejected",
                        "reason": f"同一来源文件被多个逻辑实验映射：{sorted(matched)}",
                    }
                )
                passthrough.append(discovered)
                continue
            logical_run_id = next(iter(matched))
            groups.setdefault(logical_run_id, []).append(discovered)
        merged: list[DiscoveredRun] = []
        for logical_run_id, members in groups.items():
            override = next(item for item in overrides if item.logical_run_id == logical_run_id)
            primary = members[0]
            directories = {str(member.run_directory.resolve()) for member in members}
            file_paths = {str(spec.file_path.resolve()) for member in members for spec in member.log_files}
            if len(directories) != 1:
                # 跨目录归并会让相对来源路径逃出 Run 目录，暂不允许静默跨越。
                audit.append(
                    {
                        "logical_run_id": logical_run_id,
                        "action": "rejected",
                        "reason": "当前只允许同一目录内的文件归并，跨目录规则未启用",
                    }
                )
                passthrough.extend(members)
                continue
            metadata = json.loads(json.dumps(primary.metadata))
            metadata["run_id"] = logical_run_id
            metadata["name"] = override.name
            extensions = metadata.setdefault("extensions", {})
            extensions["logical_run_id"] = logical_run_id
            extensions["merged_source_run_ids"] = [member.run_id for member in members]
            extensions["merge_reason"] = override.reason
            extensions["merge_confidence"] = "user-confirmed"
            extensions["merged_files"] = sorted(file_paths)
            log_files = []
            seen_files: set[str] = set()
            for member in members:
                for spec in member.log_files:
                    key = str(spec.file_path.resolve())
                    if key not in seen_files:
                        seen_files.add(key)
                        log_files.append(spec)
            merged.append(
                DiscoveredRun(
                    source_kind=primary.source_kind,
                    adapter_id=primary.adapter_id,
                    run_directory=primary.run_directory,
                    run_id=logical_run_id,
                    metadata=metadata,
                    log_files=log_files,
                    metadata_file=None,
                    metadata_synthetic=True,
                )
            )
            audit.append(
                {
                    "logical_run_id": logical_run_id,
                    "action": "merged",
                    "source_run_ids": [member.run_id for member in members],
                    "file_count": len(log_files),
                }
            )
        return passthrough + merged, audit


def suggested_logical_run_id(files: list[str]) -> str:
    digest = hashlib.sha1("\n".join(sorted(files)).encode("utf-8")).hexdigest()[:12]
    return f"logical-{digest}"
