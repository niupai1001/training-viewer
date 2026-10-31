"""训练日志协议 1.0 的 `run.json` 元数据读取与校验。

这里执行比 JSON Schema 更严格的中文错误检查，并把时间统一为 UTC。
读取是只读的；训练程序用临时文件 + 原子替换写入的 `run.json` 也能安全读取。
"""
from __future__ import annotations

import json
from pathlib import Path

from .log_readers.base import InvalidRunDirectoryError, parse_timestamp, require_object, require_string

_ALLOWED_FIELDS = {
    "schema_version",
    "run_id",
    "project",
    "experiment",
    "name",
    "created_at",
    "task",
    "model",
    "dataset",
    "config",
    "source",
    "tags",
    "metric_definitions",
    "extensions",
}
_ALLOWED_METRIC_DEFINITION_FIELDS = {
    "display_name",
    "direction",
    "unit",
    "description",
    "comparison_key",
    "aggregation",
    "definition",
}


def _reject_non_finite(value: str) -> float:
    raise ValueError(f"run.json 含非有限数字：{value}")


class RunMetadataReader:
    """运行元数据读取器：`run.json` → 校验后的元数据字典。"""

    def read(self, run_directory: Path) -> dict:
        metadata_path = run_directory / "run.json"
        if not metadata_path.is_file() or metadata_path.is_symlink():
            raise InvalidRunDirectoryError(f"缺少普通文件 run.json：{metadata_path}")
        try:
            payload = json.loads(
                metadata_path.read_text(encoding="utf-8"), parse_constant=_reject_non_finite
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise InvalidRunDirectoryError(f"run.json 不是合法 JSON：{error}") from error
        try:
            return self.validate(payload)
        except InvalidRunDirectoryError:
            raise
        except ValueError as error:
            raise InvalidRunDirectoryError(f"run.json 校验失败：{error}") from error

    def validate(self, payload: object) -> dict:
        data = require_object(payload, "run.json")
        unknown = sorted(set(data) - _ALLOWED_FIELDS)
        if unknown:
            raise InvalidRunDirectoryError(f"run.json 含未知字段：{', '.join(unknown)}")
        if data.get("schema_version") != "1.0":
            raise InvalidRunDirectoryError("schema_version 必须为字符串 \"1.0\"")
        run_id = require_string(data.get("run_id"), "run_id")
        require_string(data.get("project"), "project")
        require_string(data.get("name"), "name")
        created_at = parse_timestamp(data.get("created_at"), "created_at")
        if "experiment" in data:
            require_string(data.get("experiment"), "experiment")
        if "task" in data:
            require_string(data.get("task"), "task")
        for section in ("model", "dataset"):
            if section in data:
                section_value = require_object(data.get(section), section)
                if "name" in section_value:
                    require_string(section_value.get("name"), f"{section}.name")
                elif section == "model":
                    raise InvalidRunDirectoryError("model 存在时必须提供 model.name")
        if "config" in data:
            require_object(data.get("config"), "config")
        if "source" in data:
            require_object(data.get("source"), "source")
        if "extensions" in data:
            require_object(data.get("extensions"), "extensions")
        if "tags" in data:
            tags = data.get("tags")
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise InvalidRunDirectoryError("tags 必须是字符串数组")
            if len(set(tags)) != len(tags):
                raise InvalidRunDirectoryError("tags 不能重复")
        definitions = data.get("metric_definitions", {})
        if definitions is not None:
            definitions = require_object(definitions, "metric_definitions")
            for metric_key, definition in definitions.items():
                require_string(metric_key, "metric_definitions 的键")
                entry = require_object(definition, f"metric_definitions[{metric_key}]")
                unknown_definition_fields = sorted(set(entry) - _ALLOWED_METRIC_DEFINITION_FIELDS)
                if unknown_definition_fields:
                    raise InvalidRunDirectoryError(
                        f"metric_definitions[{metric_key}] 含未知字段："
                        f"{', '.join(unknown_definition_fields)}"
                    )
                if entry.get("direction") not in ("min", "max", "none"):
                    raise InvalidRunDirectoryError(
                        f"metric_definitions[{metric_key}].direction 必须是 min、max 或 none"
                    )
                for option in ("display_name", "unit", "description", "comparison_key", "aggregation", "definition"):
                    if option in entry and not isinstance(entry[option], str):
                        raise InvalidRunDirectoryError(
                            f"metric_definitions[{metric_key}].{option} 必须是字符串"
                        )
        normalized = dict(data)
        normalized["created_at"] = created_at
        normalized["run_id"] = run_id
        return normalized
