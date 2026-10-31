"""大曲线降采样：保留极值，Best/Last 使用原始数据。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from conftest import make_run_directory, metric_record


def test_downsampling_preserves_extremes_and_uses_raw_best_last(viewer) -> None:
    service, _ = viewer
    logs = Path(service.paths.data_dir).parent / "logs"
    start = datetime(2026, 10, 31, 8, 0, 0, tzinfo=timezone.utc)
    points = []
    for index in range(5000):
        value = 10 + (index % 97) / 10
        if index == 1234:
            value = 0.01
        if index == 4321:
            value = 99.0
        timestamp = (start + timedelta(seconds=index)).strftime("%Y-%m-%dT%H:%M:%SZ")
        points.append(
            metric_record(
                timestamp,
                "train",
                {"loss": value},
                index,
                index // 100 + 1,
            )
        )
    run_directory = make_run_directory(logs, metrics=points)
    service.add_root(str(logs))
    assert run_directory.is_dir()

    result = service.queries.query_series("run-0001", ["train/loss"], "global_step", 200)
    series = result["series"][0]
    assert series["total_points"] == 5000
    assert series["downsampled"] is True
    assert series["returned_points"] <= 220
    assert series["best"]["value"] == 0.01
    assert series["best"]["global_step"] == 1234
    # 最后一条记录的 index=4999，值是 10 + (4999 % 97) / 10。
    assert series["last"]["value"] == 10 + (4999 % 97) / 10
    assert series["last"]["global_step"] == 4999

    sampled = series["points"]
    assert any(point["value"] == 0.01 for point in sampled)
    assert any(point["value"] == 99.0 for point in sampled)

    with service.database.connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*), SUM(point_count) FROM metric_rollups WHERE run_id = ? AND axis = 'global_step'",
            ("run-0001",),
        ).fetchone()
    assert row[0] > 0
    assert row[1] == 5000
