"""通用日志文件来源适配器。

发现没有 run.json 的既有训练日志：任意文件名的 CSV / TSV / JSONL / 普通文本。
先做内容嗅探，只有能证明包含 Step/Epoch 与数值指标的文件才会被导入；每个文件
生成一个独立 Run（同一目录可包含多个文件），不修改原始文件。
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..log_readers.base import format_timestamp
from ..log_readers.csv_metric_reader import CsvMetricLogReader
from ..log_readers.generic_jsonl_reader import GenericJsonlMetricReader
from ..log_readers.plain_text_log_reader import PlainTextLogReader, _is_metric_key
from .base import DiscoveredRun, LogFileSpec

GENERIC_SOURCE_KINDS = ("generic-csv", "generic-tsv", "generic-jsonl", "plain-text")
_STEP_ALIASES = {"step", "global_step", "iteration", "iter", "iters"}
_EPOCH_ALIASES = {"epoch", "epochs"}
_METADATA_COLUMNS = {
    "timestamp",
    "time",
    "wall_time",
    "date",
    "datetime",
    "global_step",
    "step",
    "iteration",
    "iter",
    "epoch",
    "epochs",
    "phase",
    "mode",
    "split",
    "session_id",
    "session",
    "run_id",
    "run",
}


def _normalized_header(value: str) -> str:
    return value.strip().lstrip("\ufeff").lower()


def _looks_numeric(value: str) -> bool:
    try:
        number = float(value.strip())
    except ValueError:
        return False
    return number == number and number not in (float("inf"), float("-inf"))


def _synthetic_metadata(
    adapter_id: str, path: Path, source_kind: str, confidence: str
) -> dict:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = datetime.now(timezone.utc).timestamp()
    digest = hashlib.sha1(str(path).lower().encode("utf-8")).hexdigest()[:16]
    label = {
        "generic-csv": "csv",
        "generic-tsv": "tsv",
        "generic-jsonl": "jsonl",
        "plain-text": "text",
    }[source_kind]
    return {
        "schema_version": "1.0",
        "run_id": f"{label}-{digest}",
        "project": path.parent.name or "未命名项目",
        "name": path.stem,
        "experiment": "文件导入",
        "created_at": format_timestamp(datetime.fromtimestamp(mtime, tz=timezone.utc)),
        "tags": [label],
        "extensions": {
            "source_adapter": adapter_id,
            "source_kind": source_kind,
            "source_file": path.name,
            "synthetic_metadata": True,
            "confidence": confidence,
            "note": (
                "没有 run.json；项目/运行名称由目录推导，指标来自文件内容。"
                "该文件每次变化会重新读取，按行/字节偏移幂等导入。"
            ),
        },
    }


class GenericLogFileSourceAdapter:
    """无 run.json 的通用日志文件来源。"""

    adapter_id = "source.generic_log_file"
    display_name = "通用日志文件（CSV/TSV/JSONL/纯文本）"

    def discover(self, run_directory: Path) -> DiscoveredRun | None:
        runs = self.discover_many(run_directory)
        return runs[0] if runs else None

    def discover_many(self, run_directory: Path) -> list[DiscoveredRun]:
        if (run_directory / "run.json").exists():
            return []
        runs: list[DiscoveredRun] = []
        try:
            entries = sorted(run_directory.iterdir(), key=lambda item: item.name)
        except OSError:
            return []
        for path in entries:
            if not path.is_file() or path.is_symlink():
                continue
            suffix = path.suffix.lower()
            discovered = self._discover_file(run_directory, path, suffix)
            if discovered is not None:
                runs.append(discovered)
        return runs

    def _discover_file(
        self, run_directory: Path, path: Path, suffix: str
    ) -> DiscoveredRun | None:
        if suffix in (".csv", ".tsv"):
            delimiter = "\t" if suffix == ".tsv" else ","
            if not self._csv_looks_like_metrics(path, delimiter):
                return None
            reader = CsvMetricLogReader(None, delimiter=delimiter)
            source_kind = "generic-tsv" if suffix == ".tsv" else "generic-csv"
            confidence = "structured"
        elif suffix == ".jsonl":
            if not self._jsonl_looks_like_metrics(path):
                return None
            reader = GenericJsonlMetricReader()
            source_kind = "generic-jsonl"
            confidence = "structured"
        elif suffix in (".log", ".txt", ".out"):
            if not PlainTextLogReader.looks_like_training_log(path):
                return None
            reader = PlainTextLogReader()
            source_kind = "plain-text"
            confidence = "template"
        else:
            return None
        metadata = _synthetic_metadata(self.adapter_id, path, source_kind, confidence)
        return DiscoveredRun(
            source_kind=source_kind,
            adapter_id=self.adapter_id,
            run_directory=run_directory,
            run_id=metadata["run_id"],
            metadata=metadata,
            log_files=[LogFileSpec(path, reader)],
            metadata_file=None,
            metadata_synthetic=True,
        )

    @staticmethod
    def _csv_looks_like_metrics(path: Path, delimiter: str) -> bool:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                headers = next(reader, None)
                if not headers or len(headers) < 2:
                    return False
                normalized = [_normalized_header(header) for header in headers]
                if not (
                    _STEP_ALIASES.intersection(normalized)
                    or _EPOCH_ALIASES.intersection(normalized)
                ):
                    return False
                metric_like_header = any(_is_metric_key(header) for header in headers)
                context_header = any(
                    header in {"timestamp", "time", "wall_time", "date", "datetime", "phase", "mode", "split"}
                    for header in normalized
                )
                filename_hint = any(
                    token in path.stem.lower()
                    for token in ("train", "metric", "log", "history", "eval", "valid", "loss", "result")
                )
                if not (metric_like_header or context_header or filename_hint):
                    # 例如 name,price,step：虽有 step 和数字列，但不是训练指标日志。
                    return False
                numeric_columns = set()
                rows = 0
                for row in reader:
                    if rows >= 20:
                        break
                    rows += 1
                    for index, cell in enumerate(row[: len(headers)]):
                        if index in numeric_columns:
                            continue
                        if _normalized_header(headers[index]) in _METADATA_COLUMNS:
                            continue
                        if cell.strip() and _looks_numeric(cell):
                            numeric_columns.add(index)
                return bool(numeric_columns)
        except (OSError, UnicodeDecodeError, csv.Error):
            return False

    @staticmethod
    def _jsonl_looks_like_metrics(path: Path) -> bool:
        found = False
        try:
            with path.open("r", encoding="utf-8", errors="strict") as handle:
                for index, line in enumerate(handle):
                    if index >= 20:
                        break
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        return False
                    if not isinstance(payload, dict):
                        return False
                    has_axis = any(
                        key in payload and payload[key] is not None
                        for key in ("global_step", "step", "epoch")
                    )
                    metrics = payload.get("metrics")
                    if isinstance(metrics, dict):
                        has_metric = any(
                            isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            for value in metrics.values()
                        )
                    else:
                        has_metric = any(
                            isinstance(value, (int, float))
                            and not isinstance(value, bool)
                            for key, value in payload.items()
                            if key not in _METADATA_COLUMNS
                        )
                    if has_axis and has_metric:
                        found = True
        except (OSError, UnicodeDecodeError):
            return False
        return found
