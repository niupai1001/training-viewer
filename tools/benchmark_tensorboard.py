"""测量 TensorBoard 事件文件首次导入与追加更新的耗时。

TensorBoard 读取器目前每次从事件文件开头重放（没有利用 TFRecord 偏移），
因此本脚本用于量化“全量重读”的成本，而不是声称已做增量读取。
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

from tensorboard.summary.writer.event_file_writer import EventFileWriter
from tensorboard.compat.proto.event_pb2 import Event
from tensorboard.compat.proto.summary_pb2 import Summary

from training_viewer.application_paths import ApplicationPaths
from training_viewer.service import TrainingViewerService


def write_scalars(log_dir: Path, start: int, count: int) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    writer = EventFileWriter(str(log_dir))
    try:
        for step in range(start, start + count):
            value = 0.5 + 0.4 * (1.0 - step / max(1, start + count))
            summary = Summary(
                value=[Summary.Value(tag="val/miou", simple_value=value)]
            )
            event = Event(step=step, wall_time=time.time(), summary=summary)
            writer.add_event(event)
        writer.flush()
    finally:
        writer.close()
    files = sorted(log_dir.glob("events.out.tfevents.*"), key=lambda item: item.stat().st_mtime)
    if not files:
        raise RuntimeError("TensorBoard 没有生成事件文件")
    return files[-1]


def main() -> int:
    temporary = Path(tempfile.mkdtemp(prefix="training-viewer-tb-bench-"))
    log_root = temporary / "tensorboard"
    first = write_scalars(log_root, 0, 20000)

    service = TrainingViewerService(ApplicationPaths.resolve(temporary / "data"))
    started = time.perf_counter()
    service.add_root(str(log_root))
    first_seconds = time.perf_counter() - started
    run = service.queries.list_runs()["runs"][0]
    keys = service.queries.metric_keys(run["run_id"])

    # 同一目录追加新标量；读取器会从事件文件开头重放。
    write_scalars(log_root, 20000, 100)
    started = time.perf_counter()
    service.synchronize(force_full=True)
    append_seconds = time.perf_counter() - started
    keys_after = service.queries.metric_keys(run["run_id"])
    print(
        json.dumps(
            {
                "initial_scalars": 20000,
                "initial_index_seconds": round(first_seconds, 3),
                "append_scalars": 100,
                "append_sync_seconds": round(append_seconds, 3),
                "event_file_megabytes": round(first.stat().st_size / (1024 * 1024), 2),
                "points_before": sum(item["step_point_count"] for item in keys),
                "points_after": sum(item["step_point_count"] for item in keys_after),
                "note": "TensorBoard 仍为全量重读；这是测量结果，不是增量实现。",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    shutil.rmtree(temporary, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
