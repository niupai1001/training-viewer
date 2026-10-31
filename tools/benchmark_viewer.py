"""生成合成 TVLP 日志并测量索引/查询耗时；用于评审性能，不修改原始实现。

用法：
    python tools/benchmark_viewer.py --points 100000
    python tools/benchmark_viewer.py --points 1000000 --keep

输出 JSON，包含生成、首次索引、自动横轴查询、指标列表耗时与数据库大小。
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from training_viewer.application_paths import ApplicationPaths
from training_viewer.service import TrainingViewerService
from training_viewer.writer import TrainingRunWriter


def generate(run_directory: Path, points: int) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with (run_directory / "metrics.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for index in range(points):
            step = index
            epoch = index // 1000 + 1
            loss = 0.3 + 0.6 * math.exp(-step / 20000) + 0.01 * math.sin(step / 7)
            miou = 0.35 + 0.6 * (1 - math.exp(-step / 30000))
            record = {
                "timestamp": (start + timedelta(seconds=index)).isoformat().replace("+00:00", "Z"),
                "phase": "train" if index % 10 else "val",
                "global_step": step,
                "epoch": epoch,
                "metrics": {"loss": loss, "miou": miou},
            }
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=100_000)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if args.points < 1:
        parser.error("--points 必须 >= 1")

    temporary = Path(tempfile.mkdtemp(prefix="training-viewer-bench-"))
    log_root = temporary / "logs"
    log_root.mkdir()
    data_root = temporary / "data"
    started = time.perf_counter()
    with TrainingRunWriter(
        log_root=log_root,
        project="benchmark",
        name=f"{args.points} points",
        config={"epochs": max(1, args.points // 1000)},
        metric_definitions={
            "train/loss": {"direction": "min", "unit": "none"},
            "train/miou": {"direction": "max", "unit": "ratio"},
            "val/loss": {"direction": "min", "unit": "none"},
            "val/miou": {"direction": "max", "unit": "ratio"},
        },
    ) as writer:
        pass
    generate(writer.run_directory, args.points)
    generated_seconds = time.perf_counter() - started

    paths = ApplicationPaths.resolve(data_root)
    service = TrainingViewerService(paths, scan_interval_seconds=3600)
    started = time.perf_counter()
    service.add_root(str(log_root))
    index_seconds = time.perf_counter() - started
    run = service.queries.list_runs()["runs"][0]

    started = time.perf_counter()
    keys = service.queries.metric_keys(run["run_id"])
    metrics_seconds = time.perf_counter() - started
    started = time.perf_counter()
    series = service.queries.query_series(
        run["run_id"], ["train/loss", "val/miou"], "auto", 2000
    )
    query_seconds = time.perf_counter() - started
    started = time.perf_counter()
    service.queries.query_series(
        run["run_id"], ["train/loss", "val/miou"], "auto", 2000
    )
    cached_query_seconds = time.perf_counter() - started
    database_bytes = paths.database_file.stat().st_size
    result = {
        "points": args.points,
        "generated_seconds": round(generated_seconds, 3),
        "index_seconds": round(index_seconds, 3),
        "metric_keys_seconds": round(metrics_seconds, 3),
        "query_seconds": round(query_seconds, 3),
        "cached_query_seconds": round(cached_query_seconds, 4),
        "database_megabytes": round(database_bytes / (1024 * 1024), 2),
        "series": [
            {
                "key": item["key"],
                "axis": item["axis"],
                "total_points": item["total_points"],
                "returned_points": item["returned_points"],
            }
            for item in series["series"]
        ],
        "metric_count": len(keys),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.keep:
        shutil.rmtree(temporary, ignore_errors=True)
    else:
        print(f"临时目录保留：{temporary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
