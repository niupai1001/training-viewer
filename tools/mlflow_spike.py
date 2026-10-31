"""隔离的 MLflow Tracking 原型：导入同一批 TVLP 指标并比较查询能力。

不进入主程序、不改现有索引。需要可选安装 mlflow-skinny：
    uv pip install mlflow-skinny
    python tools/mlflow_spike.py --points 100000
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

from training_viewer.application_paths import ApplicationPaths
from training_viewer.service import TrainingViewerService
from benchmark_viewer import generate
from training_viewer.writer import TrainingRunWriter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=int, default=100_000)
    args = parser.parse_args()
    try:
        import mlflow
        from mlflow.entities import Metric
    except ImportError:
        print(json.dumps({"status": "skipped", "reason": "mlflow-skinny 未安装"}))
        return 0

    temporary = Path(tempfile.mkdtemp(prefix="training-viewer-mlflow-spike-"))
    log_root = temporary / "logs"
    log_root.mkdir()
    with TrainingRunWriter(
        log_root=log_root,
        project="spike",
        name="mlflow-spike",
        metric_definitions={
            "train/loss": {"direction": "min", "unit": "none"},
            "val/miou": {"direction": "max", "unit": "ratio"},
        },
    ) as writer:
        pass
    generate(writer.run_directory, args.points)
    service = TrainingViewerService(ApplicationPaths.resolve(temporary / "viewer-data"))
    started = time.perf_counter()
    service.add_root(str(log_root))
    viewer_index_seconds = time.perf_counter() - started
    run_id = service.queries.list_runs()["runs"][0]["run_id"]
    keys = service.queries.metric_keys(run_id)

    tracking = temporary / "mlruns"
    tracking.mkdir()
    mlflow.set_tracking_uri(tracking.as_uri())
    experiment = mlflow.set_experiment("training-viewer-spike")
    client = mlflow.MlflowClient()
    started = time.perf_counter()
    mlflow_run = client.create_run(
        experiment_id=experiment.experiment_id, run_name="mlflow-spike"
    )
    batch = []
    imported = 0
    with service.database.connection() as connection:
        rows = connection.execute(
            """
            SELECT phase, metric_name, value, global_step, epoch
            FROM metric_points WHERE run_id = ? ORDER BY global_step, id
            """,
            (run_id,),
        ).fetchall()
    for row in rows:
        batch.append(
            Metric(
                key=f"{row['phase']}/{row['metric_name']}",
                value=float(row["value"]),
                timestamp=0,
                step=int(row["global_step"] or row["epoch"] or 0),
            )
        )
        imported += 1
        if len(batch) >= 5000:
            client.log_batch(mlflow_run.info.run_id, metrics=batch)
            batch = []
    if batch:
        client.log_batch(mlflow_run.info.run_id, metrics=batch)
    mlflow_import_seconds = time.perf_counter() - started
    started = time.perf_counter()
    history = client.get_metric_history(mlflow_run.info.run_id, "train/loss")
    mlflow_query_seconds = time.perf_counter() - started
    result = {
        "points": args.points,
        "viewer_index_seconds": round(viewer_index_seconds, 3),
        "viewer_metric_count": len(keys),
        "mlflow_version": mlflow.__version__,
        "mlflow_import_seconds": round(mlflow_import_seconds, 3),
        "mlflow_history_seconds": round(mlflow_query_seconds, 3),
        "mlflow_history_points": len(history),
        "mlflow_database_megabytes": round(
            sum(item.stat().st_size for item in tracking.rglob("*") if item.is_file())
            / (1024 * 1024),
            2,
        ),
        "mlflow_supports": [
            "run/param/metric 元数据",
            "metric history 与 search",
            "artifact 管理",
            "SQLite 本地 tracking",
        ],
        "mlflow_gaps": [
            "epoch-only 指标需要映射/额外字段",
            "session_id/epoch_progress 无原生一一对应",
            "导入器必须维护 source_run_id → mlflow_run_id 与高水位游标",
            "默认 UI 不符合本产品工作区目标",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    shutil.rmtree(temporary, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
