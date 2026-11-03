"""训练日志协议 1.0 的独立校验器。

`training-viewer validate <Run目录>` 使用与 `tools/validate_log.py` 相同的 JSON Schema，
并额外检查产物路径安全与文件存在性。校验只读，不写入训练目录。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .security.path_guard import is_safe_relative_path


@dataclass
class ValidationMessage:
    level: str
    file_name: str
    line_number: int
    message: str


@dataclass
class ValidationReport:
    run_directory: Path
    messages: list[ValidationMessage] = field(default_factory=list)
    checked_records: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for message in self.messages if message.level == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for message in self.messages if message.level == "warning")


def _load_json(path: Path):
    def reject_constant(value: str):
        raise ValueError(f"不允许的非有限数字：{value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def _describe_schema_error(error) -> str:
    location = "/".join(str(part) for part in error.absolute_path)
    return f"{location}: {error.message}" if location else error.message


def _validate_jsonl(
    path: Path,
    schema: dict,
    report: ValidationReport,
    label: str,
    check_artifacts: bool,
) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    raw = path.read_bytes()
    lines = raw.split(b"\n")
    if lines and lines[-1]:
        report.messages.append(
            ValidationMessage(
                "info",
                path.name,
                len(lines),
                "文件末尾存在尚未写完的行，按协议等待补齐，本次不判为错误。",
            )
        )
    for line_number, line in enumerate(lines[:-1], start=1):
        if not line.strip():
            continue
        report.checked_records += 1
        try:
            payload = json.loads(
                line.decode("utf-8"),
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            report.messages.append(
                ValidationMessage("error", path.name, line_number, f"不是合法 JSON：{error}")
            )
            continue
        issues = sorted(validator.iter_errors(payload), key=lambda item: list(map(str, item.path)))
        if issues:
            for issue in issues:
                report.messages.append(
                    ValidationMessage(
                        "error", path.name, line_number, _describe_schema_error(issue)
                    )
                )
            continue
        if label == "metrics":
            values = payload["metrics"].values()
            if any(
                isinstance(value, bool) or not math.isfinite(float(value))
                for value in values
            ):
                report.messages.append(
                    ValidationMessage("error", path.name, line_number, "指标值必须是有限数字")
                )
        if label == "events" and payload.get("type") == "artifact":
            _check_artifact_reference(path, payload, line_number, report, check_artifacts)


def _check_artifact_reference(
    path: Path,
    payload: dict,
    line_number: int,
    report: ValidationReport,
    check_artifacts: bool,
) -> None:
    relative = payload["path"]
    if not is_safe_relative_path(relative):
        report.messages.append(
            ValidationMessage(
                "error",
                path.name,
                line_number,
                f"产物路径必须是 Run 目录内的相对路径：{relative!r}",
            )
        )
        return
    if not check_artifacts:
        return
    run_directory = path.parent.resolve()
    resolved = (run_directory / relative.replace("\\", "/")).resolve()
    if not resolved.is_relative_to(run_directory):
        report.messages.append(
            ValidationMessage(
                "error",
                path.name,
                line_number,
                f"产物路径通过符号链接越出 Run 目录：{relative!r}",
            )
        )
    elif not resolved.is_file():
        report.messages.append(
            ValidationMessage(
                "warning",
                path.name,
                line_number,
                f"产物文件当前不存在：{relative}",
            )
        )


def validate_run_directory(run_directory: Path, schema_directory: Path) -> ValidationReport:
    report = ValidationReport(run_directory=run_directory)
    if not run_directory.is_dir():
        report.messages.append(
            ValidationMessage("error", "", 0, f"目录不存在：{run_directory}")
        )
        return report
    run_file = run_directory / "run.json"
    run_schema = "run.schema.json"
    if run_file.is_file():
        try:
            version = _load_json(run_file).get("schema_version")
        except (OSError, ValueError, AttributeError):
            version = None
        if version == "1.1":
            run_schema = "run-1.1.schema.json"
        elif version not in (None, "1.0"):
            report.messages.append(
                ValidationMessage("error", "run.json", 0, f"不支持的 schema_version：{version!r}")
            )
    schema_files = [
        ("run.json", run_schema, "run", False),
        ("metrics.jsonl", "metrics.schema.json", "metrics", False),
        ("events.jsonl", "events.schema.json", "events", True),
    ]
    for file_name, schema_name, label, check_artifacts in schema_files:
        target = run_directory / file_name
        schema_path = schema_directory / schema_name
        try:
            schema = _load_json(schema_path)
        except (OSError, ValueError) as error:
            report.messages.append(
                ValidationMessage("error", schema_name, 0, f"无法加载协议 Schema：{error}")
            )
            continue
        if not target.exists():
            if file_name == "run.json":
                report.messages.append(
                    ValidationMessage("error", file_name, 0, "缺少必需文件 run.json")
                )
            else:
                report.messages.append(
                    ValidationMessage("info", file_name, 0, "可选日志文件不存在，跳过校验")
                )
            continue
        if target.suffix == ".jsonl":
            _validate_jsonl(target, schema, report, label, check_artifacts)
            continue
        report.checked_records += 1
        try:
            payload = _load_json(target)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            report.messages.append(
                ValidationMessage("error", file_name, 0, f"不是合法 JSON：{error}")
            )
            continue
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        issues = sorted(validator.iter_errors(payload), key=lambda item: list(map(str, item.path)))
        for issue in issues:
            report.messages.append(
                ValidationMessage("error", file_name, 0, _describe_schema_error(issue))
            )
    return report
