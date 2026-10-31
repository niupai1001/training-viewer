"""REST API：筛选、曲线、对比、导出、产物安全边界与用户界面数据。"""
from __future__ import annotations

import json
from pathlib import Path

from conftest import EXAMPLE_RUNS, make_run_directory, metric_record
from training_viewer.api import routes_catalog

EXAMPLES = EXAMPLE_RUNS


def _add_examples(client) -> None:
    response = client.post("/api/v1/roots", json={"path": str(EXAMPLES)})
    assert response.status_code == 201, response.text


def _run_by_name(client, name: str) -> dict:
    response = client.get("/api/v1/runs", params={"q": name})
    assert response.status_code == 200
    for run in response.json()["runs"]:
        if run["name"] == name:
            return run
    raise AssertionError(f"没有找到运行 {name}")


def test_health_meta_and_projects(client) -> None:
    test_client, _ = client
    health = test_client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["application"] == "training-viewer"
    meta = test_client.get("/api/v1/meta").json()
    assert meta["tvlp_schema_version"] == "1.0"
    assert "tvlp" in meta["source_kinds"]
    projects = test_client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert projects.json()["roots"] == []


def test_add_and_remove_root_validates_path(client) -> None:
    test_client, _ = client
    bad = test_client.post("/api/v1/roots", json={"path": "not-a-real-directory"})
    assert bad.status_code == 400
    _add_examples(test_client)
    roots = test_client.get("/api/v1/roots").json()["roots"]
    assert len(roots) == 1
    removed = test_client.delete(f"/api/v1/roots/{roots[0]['id']}")
    assert removed.status_code == 200
    assert test_client.get("/api/v1/runs").json()["total"] == 0


def test_runs_filters_and_facets(client) -> None:
    test_client, _ = client
    _add_examples(test_client)
    all_runs = test_client.get("/api/v1/runs", params={"limit": 100}).json()
    assert all_runs["total"] >= 3
    filtered = test_client.get(
        "/api/v1/runs", params={"project": "disaster-detection", "tag": "baseline"}
    ).json()
    assert filtered["total"] == 1
    assert filtered["runs"][0]["tags"] == ["baseline", "10-band"]
    facets = test_client.get("/api/v1/facets").json()
    assert "SegFormer" in facets["models"]
    assert "landslide-dataset" in facets["datasets"]
    assert "baseline" in facets["tags"]
    search = test_client.get("/api/v1/runs", params={"q": "波长"}).json()
    assert search["total"] == 1


def test_run_detail_metric_keys_and_series(client) -> None:
    test_client, _ = client
    _add_examples(test_client)
    run = _run_by_name(test_client, "segformer-baseline")
    detail = test_client.get(f"/api/v1/runs/{run['run_id']}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["schema_version"] == "1.0"
    assert {item["key"] for item in payload["metric_keys"]} == {
        "train/loss",
        "train/lr",
        "val/loss",
        "val/miou",
        "val/f1",
    }
    keys = test_client.get(f"/api/v1/runs/{run['run_id']}/metric-keys")
    assert keys.status_code == 200
    series = test_client.get(
        f"/api/v1/runs/{run['run_id']}/metrics",
        params=[("series", "val/miou"), ("series", "train/loss"), ("axis", "global_step")],
    )
    assert series.status_code == 200
    body = series.json()
    assert [item["key"] for item in body["series"]] == ["val/miou", "train/loss"]
    miou = body["series"][0]
    assert miou["best"]["value"] == 0.52
    assert miou["last"]["value"] == 0.52
    assert len(miou["points"]) == 2

    epoch_series = test_client.get(
        f"/api/v1/runs/{run['run_id']}/metrics",
        params={"series": "val/miou", "axis": "epoch"},
    ).json()["series"][0]
    assert [point["x"] for point in epoch_series["points"]] == [1, 2]

    time_series = test_client.get(
        f"/api/v1/runs/{run['run_id']}/metrics",
        params={"series": "val/miou", "axis": "timestamp"},
    ).json()["series"][0]
    assert all(isinstance(point["x"], (int, float)) for point in time_series["points"])


def test_compare_marks_comparable_and_shows_hyperparameter_differences(client) -> None:
    test_client, _ = client
    _add_examples(test_client)
    baseline = _run_by_name(test_client, "segformer-baseline")
    wavelength = _run_by_name(test_client, "SegFormer 波长条件化输入｜10 波段｜随机种子 43")
    response = test_client.post(
        "/api/v1/compare/query",
        json={
            "run_ids": [baseline["run_id"], wavelength["run_id"]],
            "series": ["val/miou"],
            "axis": "global_step",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    metric = body["series"][0]
    assert metric["ranking_allowed"] is True
    assert len(metric["runs"]) == 2
    assert metric["runs"][0]["best"]["value"] == 0.52
    assert metric["runs"][1]["best"]["value"] == 0.61
    diff_paths = {row["path"] for row in body["hyperparameters"]["rows"] if row["different"]}
    assert "optimizer.lr" in diff_paths
    assert "wavelength_embedding" in diff_paths
    assert body["run_fields"]["seed"][baseline["run_id"]] == 42
    assert body["run_fields"]["seed"][wavelength["run_id"]] == 43


def test_compare_is_not_ranked_when_dataset_or_unit_differs(client) -> None:
    test_client, service = client
    logs = Path(service.paths.data_dir).parent / "logs"
    make_run_directory(
        logs / "a",
        run_id="run-a",
        dataset={"name": "dataset-A", "version": "v1", "split_definition": "s1"},
        metrics=[metric_record("2026-10-31T08:00:00Z", "val", {"miou": 0.5}, 100, 1)],
    )
    make_run_directory(
        logs / "b",
        run_id="run-b",
        dataset={"name": "dataset-B", "version": "v1", "split_definition": "s1"},
        metrics=[metric_record("2026-10-31T08:00:00Z", "val", {"miou": 0.6}, 100, 1)],
    )
    test_client.post("/api/v1/roots", json={"path": str(logs)})
    response = test_client.post(
        "/api/v1/compare/query",
        json={"run_ids": ["run-a", "run-b"], "series": ["val/miou"], "axis": "global_step"},
    )
    metric = response.json()["series"][0]
    assert metric["ranking_allowed"] is False
    assert any(warning["code"] == "dataset_mismatch" for warning in metric["warnings"])

    # 缺失指标不会被插值补齐。
    missing = test_client.post(
        "/api/v1/compare/query",
        json={"run_ids": ["run-a", "run-b"], "series": ["val/does-not-exist"], "axis": "epoch"},
    ).json()
    assert all(not item["runs"] for item in missing["series"])


def test_export_csv_and_json_include_provenance(client) -> None:
    test_client, _ = client
    _add_examples(test_client)
    run = _run_by_name(test_client, "segformer-baseline")
    csv_response = test_client.get(
        f"/api/v1/runs/{run['run_id']}/metrics/export",
        params=[
            ("series", "val/miou"),
            ("format", "csv"),
            ("axis", "global_step"),
            ("smoothing_method", "ema"),
        ],
    )
    assert csv_response.status_code == 200
    assert csv_response.text.startswith("# exported_at:")
    assert "# axis: \"global_step\"" in csv_response.text
    assert "smoothing_method" in csv_response.text
    assert "val/miou" in csv_response.text
    assert "attachment" in csv_response.headers["content-disposition"]

    json_response = test_client.get(
        f"/api/v1/runs/{run['run_id']}/metrics/export",
        params=[("series", "val/miou"), ("format", "json"), ("axis", "global_step")],
    )
    assert json_response.status_code == 200
    payload = json.loads(json_response.text)
    assert payload["metadata"]["axis"] == "global_step"
    assert payload["series"][0]["key"] == "val/miou"


def test_artifact_listing_groups_content_and_table_preview(client) -> None:
    test_client, _ = client
    _add_examples(test_client)
    run = _run_by_name(test_client, "SegFormer 波长条件化输入｜10 波段｜随机种子 43")
    groups = test_client.get(f"/api/v1/runs/{run['run_id']}/artifact-groups").json()["groups"]
    assert len(groups) == 2
    preview_group = next(group for group in groups if group["tag"] == "segmentation-preview")
    assert set(preview_group["roles"]) == {"prediction", "ground_truth"}
    prediction = preview_group["roles"]["prediction"][0]
    content = test_client.get(prediction["content_url"])
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"
    assert "sandbox" in content.headers["content-security-policy"]
    assert content.headers["x-content-type-options"] == "nosniff"

    table_group = next(group for group in groups if group["tag"] == "segmentation-metrics")
    table = table_group["roles"]["confusion_matrix"][0]
    preview = test_client.get(f"/api/v1/artifacts/{table['id']}/table-preview")
    assert preview.status_code == 200
    table_payload = preview.json()
    assert table_payload["columns"][0] == "真实类别"
    assert len(table_payload["rows"]) == 5


def test_html_artifact_is_not_served_as_executable_html(client) -> None:
    test_client, service = client
    logs = Path(service.paths.data_dir).parent / "logs"
    run_directory = make_run_directory(
        logs,
        run_id="html-run",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 100, 1)],
        events=[
            {
                "type": "artifact",
                "timestamp": "2026-10-31T08:01:00Z",
                "path": "artifacts/report.html",
                "artifact_type": "html",
                "tag": "report",
                "role": "figure",
            }
        ],
    )
    (run_directory / "artifacts").mkdir(exist_ok=True)
    (run_directory / "artifacts" / "report.html").write_text(
        "<html><script>alert('x')</script></html>", encoding="utf-8"
    )
    test_client.post("/api/v1/roots", json={"path": str(logs)})
    artifacts = test_client.get("/api/v1/runs/html-run/artifacts").json()["artifacts"]
    assert len(artifacts) == 1
    content = test_client.get(artifacts[0]["content_url"])
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("text/plain")
    assert content.headers["content-disposition"].startswith("attachment")
    assert "script" in content.text


def test_artifact_path_traversal_is_rejected_even_if_database_is_tampered(client) -> None:
    test_client, service = client
    logs = Path(service.paths.data_dir).parent / "logs"
    run_directory = make_run_directory(
        logs,
        run_id="tampered-run",
        metrics=[metric_record("2026-10-31T08:00:00Z", "train", {"loss": 0.9}, 100, 1)],
    )
    (run_directory.parent / "secret.txt").write_text("secret", encoding="utf-8")
    test_client.post("/api/v1/roots", json={"path": str(logs)})
    with service.database.transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO artifacts (
                run_id, path, artifact_type, tag, timestamp, source_file, source_offset,
                exists_on_disk
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                "tampered-run",
                "../secret.txt",
                "file",
                "malicious",
                "2026-10-31T08:00:00.000000Z",
                "events.jsonl",
                999,
            ),
        )
        artifact_id = cursor.lastrowid
    response = test_client.get(f"/api/v1/artifacts/{artifact_id}/content")
    assert response.status_code == 403


def test_artifact_content_is_denied_outside_registered_root(client) -> None:
    test_client, service = client
    _add_examples(test_client)
    run = _run_by_name(test_client, "segformer-baseline")
    artifacts = test_client.get(f"/api/v1/runs/{run['run_id']}/artifacts").json()["artifacts"]
    assert artifacts
    with service.user_state.transaction() as connection:
        connection.execute("DELETE FROM watched_roots")
    response = test_client.get(artifacts[0]["content_url"])
    assert response.status_code == 403


def test_host_and_origin_checks_reject_foreign_pages(client) -> None:
    test_client, _ = client
    foreign_host = test_client.get("/api/v1/health", headers={"Host": "evil.example"})
    assert foreign_host.status_code == 403
    foreign_origin = test_client.get(
        "/api/v1/health", headers={"Origin": "https://evil.example"}
    )
    assert foreign_origin.status_code == 403
    lookalike_origin = test_client.get(
        "/api/v1/health", headers={"Origin": "http://127.0.0.1.evil.example"}
    )
    assert lookalike_origin.status_code == 403
    local_origin = test_client.get(
        "/api/v1/health", headers={"Origin": "http://127.0.0.1:8765"}
    )
    assert local_origin.status_code == 200


def test_annotations_and_saved_views(client) -> None:
    test_client, _ = client
    _add_examples(test_client)
    run = _run_by_name(test_client, "segformer-baseline")
    update = test_client.put(
        f"/api/v1/runs/{run['run_id']}/annotation",
        json={"note": "备注内容", "favorite": True},
    )
    assert update.status_code == 200
    assert update.json() == {"note": "备注内容", "favorite": True}
    detail = test_client.get(f"/api/v1/runs/{run['run_id']}").json()
    assert detail["note"] == "备注内容"
    assert detail["favorite"] is True

    created = test_client.post(
        "/api/v1/saved-views",
        json={
            "name": "基线与波长编码对比",
            "view_kind": "comparison",
            "payload": {"run_ids": [run["run_id"]], "series": ["val/miou"], "axis": "epoch"},
        },
    )
    assert created.status_code == 201
    view_id = created.json()["id"]
    views = test_client.get("/api/v1/saved-views").json()["saved_views"]
    assert views[0]["name"] == "基线与波长编码对比"
    restored = test_client.get(f"/api/v1/saved-views/{view_id}")
    assert restored.status_code == 200
    assert restored.json()["payload"]["run_ids"] == [run["run_id"]]
    assert test_client.delete(f"/api/v1/saved-views/{view_id}").status_code == 200
    assert test_client.get("/api/v1/saved-views").json()["saved_views"] == []
    assert test_client.get(f"/api/v1/saved-views/{view_id}").status_code == 404


def test_system_directory_picker_returns_selected_path(client, monkeypatch) -> None:
    test_client, _ = client
    monkeypatch.setattr(
        routes_catalog,
        "select_directory_with_system_dialog",
        lambda: str(EXAMPLES),
    )
    response = test_client.post("/api/v1/roots/select")
    assert response.status_code == 200
    assert response.json()["path"] == str(EXAMPLES)
    monkeypatch.setattr(routes_catalog, "select_directory_with_system_dialog", lambda: None)
    assert test_client.post("/api/v1/roots/select").status_code == 400


def test_diagnostics_lists_broken_run(client, tmp_path) -> None:
    test_client, service = client
    logs = Path(service.paths.data_dir).parent / "logs"
    broken = logs / "broken"
    broken.mkdir(parents=True)
    (broken / "run.json").write_text('{"schema_version": "1.0"}', encoding="utf-8")
    test_client.post("/api/v1/roots", json={"path": str(logs)})
    diagnostics = test_client.get("/api/v1/diagnostics").json()
    assert any("run_id" in issue["message"] for issue in diagnostics["scan_issues"])


def test_frontend_assets_are_served_or_missing_message(client) -> None:
    test_client, _ = client
    response = test_client.get("/")
    assert response.status_code in (200, 503)
    if response.status_code == 503:
        assert "前端资源尚未构建" in response.text


def test_table_preview_rejects_non_table_artifact(client) -> None:
    test_client, _ = client
    _add_examples(test_client)
    run = _run_by_name(test_client, "segformer-baseline")
    artifacts = test_client.get(f"/api/v1/runs/{run['run_id']}/artifacts").json()["artifacts"]
    image = next(item for item in artifacts if item["artifact_type"] == "image")
    response = test_client.get(f"/api/v1/artifacts/{image['id']}/table-preview")
    assert response.status_code == 400
