"""训练日志写入器（TrainingRunWriter）。

这是训练程序侧的轻量写入辅助，不是查看器服务：只依赖 Python 标准库，可单独复制到
训练仓库。它负责创建 Run 目录、原子写 run.json、追加 metrics.jsonl / events.jsonl、
生成会话与心跳，并在结束时写入生命周期；不会连接 HTTP、不会修改已有日志。

最低兼容 Python 3.11。
"""
from __future__ import annotations

import json
import math
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

WRITER_VERSION = "1.0.0"
_SCHEMA_VERSION = "1.0"
_LIFECYCLE_STATUSES = {"started", "resumed", "completed", "failed", "cancelled"}
_ARTIFACT_TYPES = {"image", "table", "figure", "html", "model", "file"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _validate_relative_path(value: str) -> str:
    candidate = value.replace("\\", "/").strip()
    if not candidate or candidate.startswith("/") or candidate.startswith("~"):
        raise ValueError(f"产物路径必须是 Run 目录内的相对路径：{value!r}")
    parts = candidate.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"产物路径不能包含空段、'.' 或 '..'：{value!r}")
    if len(candidate) >= 2 and candidate[1] == ":":
        raise ValueError(f"产物路径不能是绝对路径：{value!r}")
    return candidate


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


class TrainingRunWriter:
    """把一次训练/评估写成标准 TVLP 1.0 Run。

    推荐用上下文管理器，自动写入 started/completed（异常时 failed）：
    ``with TrainingRunWriter(log_root="D:/runs", project="p", name="n") as run: ...``。
    """

    def __init__(
        self,
        log_root: str | os.PathLike | None = None,
        *,
        project: str,
        name: str,
        run_id: str | None = None,
        run_directory: str | os.PathLike | None = None,
        experiment: str | None = None,
        task: str | None = None,
        model: dict | None = None,
        dataset: dict | None = None,
        config: dict | None = None,
        source: dict | None = None,
        tags: list[str] | None = None,
        metric_definitions: dict | None = None,
        session_id: str | None = None,
        heartbeat_interval_seconds: float | None = 30.0,
        resume: bool = False,
    ):
        if not project or not str(project).strip():
            raise ValueError("project 不能为空")
        if not name or not str(name).strip():
            raise ValueError("name 不能为空")
        if log_root is None and run_directory is None:
            raise ValueError("必须提供 log_root 或 run_directory")
        self.project = str(project)
        self.name = str(name)
        self.run_id = run_id or str(uuid.uuid4())
        self.experiment = experiment
        self.task = task
        self.model = model
        self.dataset = dataset
        self.config = config or {}
        self.source = source or {}
        self.tags = tags or []
        self.metric_definitions = metric_definitions or {}
        self.session_id = session_id or (
            f"session-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
        )
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.resume = resume
        self.log_root = (
            Path(log_root).expanduser().resolve() if log_root is not None else None
        )
        self._explicit_run_directory = (
            Path(run_directory).expanduser().resolve()
            if run_directory is not None
            else None
        )
        self.run_directory = self._explicit_run_directory or (
            self.log_root / self.run_id  # type: ignore[operator]
        )
        self._lock = threading.RLock()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._metrics_file = None
        self._events_file = None
        self._started = False
        self._closed = False
        self._last_global_step: int | None = None

    # ------------------------------------------------------------------ 生命周期
    def __enter__(self) -> "TrainingRunWriter":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is not None:
            self.finish("failed", message=f"{exc_type.__name__}: {exc_value}")
        else:
            self.finish("completed")
        return False

    def start(self) -> "TrainingRunWriter":
        """创建/恢复运行目录、写元数据、打开日志并写 started/resumed。"""
        with self._lock:
            if self._started:
                return self
            self.run_directory.mkdir(parents=True, exist_ok=True)
            metadata_path = self.run_directory / "run.json"
            if metadata_path.exists():
                if not self.resume:
                    raise FileExistsError(
                        f"运行目录已存在：{self.run_directory}。"
                        "如果要继续写入同一个 Run，请设置 resume=True 并保持相同 run_id。"
                    )
                existing = json.loads(metadata_path.read_text(encoding="utf-8"))
                if existing.get("run_id") != self.run_id:
                    raise ValueError(
                        f"恢复运行的 run_id 不一致：现有 {existing.get('run_id')!r}，"
                        f"请求 {self.run_id!r}"
                    )
                if existing.get("project") not in (None, self.project):
                    raise ValueError(
                        f"恢复运行的项目不一致：现有 {existing.get('project')!r}，"
                        f"请求 {self.project!r}"
                    )
            else:
                _write_json_atomic(
                    metadata_path,
                    self._build_metadata(),
                )
            self._metrics_file = (self.run_directory / "metrics.jsonl").open(
                "a", encoding="utf-8", newline="\n"
            )
            self._events_file = (self.run_directory / "events.jsonl").open(
                "a", encoding="utf-8", newline="\n"
            )
            self._started = True
            self.log_lifecycle("resumed" if self.resume else "started")
            self._start_heartbeat()
            return self

    def finish(self, status: str = "completed", message: str | None = None) -> None:
        """写入结束生命周期并关闭文件；重复调用安全。"""
        self._heartbeat_stop.set()
        thread = self._heartbeat_thread
        if thread is not None and thread is not threading.current_thread():
            # 先停止心跳再拿写锁，避免与正在等待锁的心跳线程互相等待。
            thread.join(timeout=2)
        self._heartbeat_thread = None
        with self._lock:
            if self._closed:
                return
            if self._started and status in _LIFECYCLE_STATUSES:
                self.log_lifecycle(status, message=message)
            if self._metrics_file is not None:
                self._metrics_file.close()
                self._metrics_file = None
            if self._events_file is not None:
                self._events_file.close()
                self._events_file = None
            self._closed = True

    close = finish

    # ------------------------------------------------------------------ 指标
    def log_metrics(
        self,
        phase: str,
        metrics: dict,
        *,
        global_step: int | None = None,
        epoch: int | None = None,
        epoch_progress: float | None = None,
        wall_time_sec: float | None = None,
        context: dict | None = None,
    ) -> None:
        """追加一条指标记录。同一 Step 的不同 phase 允许同时存在。"""
        self._require_started()
        if not isinstance(phase, str) or not phase.strip():
            raise ValueError("phase 必须是非空字符串")
        if not isinstance(metrics, dict) or not metrics:
            raise ValueError("metrics 必须是非空字典")
        clean_metrics: dict[str, float] = {}
        for key, value in metrics.items():
            if not isinstance(key, str) or not key:
                raise ValueError("metrics 的键必须是非空字符串")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"指标 {key} 必须是数字")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"指标 {key} 必须是有限数字")
            clean_metrics[key] = number
        if global_step is None and epoch is None:
            raise ValueError("必须提供 global_step 或 epoch")
        if global_step is not None:
            if isinstance(global_step, bool) or not isinstance(global_step, int) or global_step < 0:
                raise ValueError("global_step 必须是 >= 0 的整数")
            self._last_global_step = global_step
        if epoch is not None:
            if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
                raise ValueError("epoch 必须是从 1 开始的整数")
        if epoch_progress is not None:
            if not isinstance(epoch_progress, (int, float)) or isinstance(epoch_progress, bool):
                raise ValueError("epoch_progress 必须是数字")
            if not 0.0 <= float(epoch_progress) <= 1.0:
                raise ValueError("epoch_progress 必须在 [0, 1] 区间")
        if wall_time_sec is not None:
            if (
                not isinstance(wall_time_sec, (int, float))
                or isinstance(wall_time_sec, bool)
                or not math.isfinite(float(wall_time_sec))
                or float(wall_time_sec) < 0
            ):
                raise ValueError("wall_time_sec 必须是 >= 0 的有限数字")
        if context is not None and not isinstance(context, dict):
            raise ValueError("context 必须是字典")
        record = {
            "timestamp": _utc_now(),
            "event_id": uuid.uuid4().hex,
            "session_id": self.session_id,
            "phase": phase,
            "metrics": clean_metrics,
        }
        for key, value in (
            ("global_step", global_step),
            ("epoch", epoch),
            ("epoch_progress", None if epoch_progress is None else float(epoch_progress)),
            ("wall_time_sec", wall_time_sec),
            ("context", context),
        ):
            if value is not None:
                record[key] = value
        self._write_jsonl(self._metrics_file, record)

    def log_heartbeat(self, global_step: int | None = None) -> None:
        """追加心跳；不要把心跳当作训练完成的证据。"""
        self._require_started()
        if global_step is not None:
            if isinstance(global_step, bool) or not isinstance(global_step, int) or global_step < 0:
                raise ValueError("global_step 必须是 >= 0 的整数")
        record = {
            "type": "heartbeat",
            "timestamp": _utc_now(),
            "session_id": self.session_id,
        }
        step = global_step if global_step is not None else self._last_global_step
        if step is not None:
            record["global_step"] = step
        self._write_jsonl(self._events_file, record)

    def log_lifecycle(self, status: str, message: str | None = None) -> None:
        """追加生命周期事件（started/resumed/completed/failed/cancelled）。"""
        self._require_started()
        if status not in _LIFECYCLE_STATUSES:
            raise ValueError(f"未知生命周期状态：{status}")
        record = {
            "type": "lifecycle",
            "timestamp": _utc_now(),
            "session_id": self.session_id,
            "status": status,
        }
        if message:
            record["message"] = str(message)
        self._write_jsonl(self._events_file, record)

    # ------------------------------------------------------------------ 产物
    def artifact_path(self, relative_path: str) -> Path:
        """返回 Run 目录内的产物绝对路径，并创建父目录；文件仍需由训练代码写入。"""
        relative = _validate_relative_path(relative_path)
        path = self.run_directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def log_artifact(
        self,
        path: str,
        *,
        artifact_type: str,
        tag: str,
        phase: str | None = None,
        global_step: int | None = None,
        epoch: int | None = None,
        group_id: str | None = None,
        sample_id: str | None = None,
        role: str | None = None,
        mime_type: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """追加产物引用。同一个 group_id 可对齐原图/标签/预测。"""
        self._require_started()
        relative = _validate_relative_path(path)
        if artifact_type not in _ARTIFACT_TYPES:
            raise ValueError(f"artifact_type 必须是 {sorted(_ARTIFACT_TYPES)} 之一")
        if not tag:
            raise ValueError("tag 不能为空")
        if global_step is not None:
            if isinstance(global_step, bool) or not isinstance(global_step, int) or global_step < 0:
                raise ValueError("global_step 必须是 >= 0 的整数")
        if epoch is not None:
            if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
                raise ValueError("epoch 必须是从 1 开始的整数")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata 必须是字典")
        record = {
            "type": "artifact",
            "timestamp": _utc_now(),
            "session_id": self.session_id,
            "path": relative,
            "artifact_type": artifact_type,
            "tag": tag,
        }
        for key, value in (
            ("phase", phase),
            ("global_step", global_step),
            ("epoch", epoch),
            ("group_id", group_id),
            ("sample_id", sample_id),
            ("role", role),
            ("mime_type", mime_type),
            ("metadata", metadata),
        ):
            if value is not None:
                record[key] = value
        self._write_jsonl(self._events_file, record)

    # ------------------------------------------------------------------ 内部
    def _build_metadata(self) -> dict:
        metadata = {
            "schema_version": _SCHEMA_VERSION,
            "run_id": self.run_id,
            "project": self.project,
            "name": self.name,
            "created_at": _utc_now(),
            "config": self.config,
            "source": self.source,
            "tags": self.tags,
            "metric_definitions": self.metric_definitions,
            "extensions": {
                "writer": "TrainingRunWriter",
                "writer_version": WRITER_VERSION,
            },
        }
        for key, value in (
            ("experiment", self.experiment),
            ("task", self.task),
            ("model", self.model),
            ("dataset", self.dataset),
        ):
            if value is not None:
                metadata[key] = value
        return metadata

    def _require_started(self) -> None:
        if not self._started:
            raise RuntimeError("写入器尚未启动，请调用 start() 或使用 with 语句")
        if self._closed:
            raise RuntimeError("写入器已关闭")

    def _write_jsonl(self, file_handle, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False, allow_nan=False)
        with self._lock:
            if file_handle is None:
                raise RuntimeError("日志文件已关闭")
            file_handle.write(line + "\n")
            file_handle.flush()

    def _start_heartbeat(self) -> None:
        if not self.heartbeat_interval_seconds or self.heartbeat_interval_seconds <= 0:
            return
        interval = float(self.heartbeat_interval_seconds)

        def beat() -> None:
            while not self._heartbeat_stop.wait(interval):
                try:
                    self.log_heartbeat()
                except Exception:
                    # 心跳失败不应中断训练；最终状态仍由 finish 写入。
                    return

        self._heartbeat_thread = threading.Thread(
            target=beat, name="training-viewer-writer-heartbeat", daemon=True
        )
        self._heartbeat_thread.start()
