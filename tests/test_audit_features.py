"""审计新增接口：来源清单、逻辑映射、结果候选与插件清单。"""
from __future__ import annotations

import base64
from pathlib import Path

import pytest
from conftest import make_run_directory, metric_record


def _run(client, name: str = "segformer-baseline") -> dict:
    response = client.get("/api/v1/runs", params={"q": name})
    assert response.status_code == 200
    return response.json()["runs"][0]


def test_source_inventory_and_plugin_manifest(client) -> None:
    test_client, _ = client
    test_client.post("/api/v1/roots", json={"path": str(Path("examples").resolve())})
    sources = test_client.get("/api/v1/audit/sources").json()["sources"]
    assert sources
    assert {"source_path", "logical_run_id", "confidence", "point_count"}.issubset(sources[0])
    plugins = test_client.get("/api/v1/plugins").json()["plugins"]
    assert any(item["adapter_id"] == "source.standard_training_log" for item in plugins)
    assert all(item["status"] == "builtin" for item in plugins)


def test_result_candidates_are_labeled_and_safely_served(client) -> None:
    test_client, service = client
    logs = Path(service.paths.data_dir).parent / "logs"
    run_directory = make_run_directory(
        logs,
        run_id="result-candidate-run",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.5}, 1, 1)],
    )
    predictions = run_directory / "predictions"
    predictions.mkdir()
    (predictions / "sample-001-pred.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"0" * 20
    )
    test_client.post("/api/v1/roots", json={"path": str(logs)})
    payload = test_client.get(
        "/api/v1/runs/result-candidate-run/result-candidates"
    ).json()
    candidate = payload["candidates"][0]
    assert candidate["role_guess"] == "prediction"
    assert candidate["requires_confirmation"] is True
    assert candidate["confidence"] == "filename-hint"
    content = test_client.get(candidate["content_url"])
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/png")
    traversal = test_client.get(
        "/api/v1/runs/result-candidate-run/result-candidates/content",
        params={"path": "../../secret.png"},
    )
    assert traversal.status_code in (403, 404)


def test_tensorboard_image_events_are_cached_as_results(client, tmp_path: Path) -> None:
    pytest.importorskip("tensorboard")
    from tensorboard.compat.proto.event_pb2 import Event
    from tensorboard.compat.proto.summary_pb2 import Summary
    from tensorboard.summary.writer.event_file_writer import EventFileWriter

    test_client, service = client
    log_root = Path(service.paths.data_dir).parent / "tb-images"
    log_root.mkdir(parents=True)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    writer = EventFileWriter(str(log_root))
    try:
        writer.add_event(
            Event(
                step=3,
                wall_time=1761900000.0,
                summary=Summary(
                    value=[
                        Summary.Value(
                            tag="val/prediction/sample-001",
                            image=Summary.Image(
                                encoded_image_string=png,
                                height=1,
                                width=1,
                                colorspace=1,
                            ),
                        )
                    ]
                ),
            )
        )
        writer.flush()
    finally:
        writer.close()
    test_client.post("/api/v1/roots", json={"path": str(log_root)})
    runs = test_client.get("/api/v1/runs", params={"q": "tb-images"}).json()["runs"]
    assert runs
    payload = test_client.get(
        f"/api/v1/runs/{runs[0]['run_id']}/result-candidates"
    ).json()
    event_candidates = [
        item for item in payload["candidates"] if item["confidence"] == "event-image"
    ]
    assert event_candidates
    assert event_candidates[0]["requires_confirmation"] is False
    content = test_client.get(event_candidates[0]["content_url"])
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"


def test_logical_override_api_round_trip(client) -> None:
    test_client, service = client
    logs = Path(service.paths.data_dir).parent / "logical-api"
    directory = logs / "alpha"
    directory.mkdir(parents=True)
    first = directory / "train.csv"
    second = directory / "val.csv"
    for path, value in ((first, 1.0), (second, 0.8)):
        path.write_text(f"step,loss\n1,{value}\n", encoding="utf-8")
    test_client.post("/api/v1/roots", json={"path": str(logs)})
    response = test_client.post(
        "/api/v1/logical-runs/overrides",
        json={
            "logical_run_id": "logical-api-run",
            "name": "API 归并实验",
            "files": [str(first), str(second)],
            "reason": "测试确认",
        },
    )
    assert response.status_code == 200, response.text
    assert test_client.get("/api/v1/logical-runs/overrides").json()["overrides"][0][
        "logical_run_id"
    ] == "logical-api-run"
    assert test_client.delete("/api/v1/logical-runs/overrides/logical-api-run").status_code == 200
