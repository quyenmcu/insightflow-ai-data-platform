import base64
from copy import deepcopy
import json
from pathlib import Path

import pytest

from infrastructure import export_dashboard as exporter, publish_dashboard as publisher, run_cloud_pipeline
from ingestion.batch.dashboard_contract import aggregate_digest


def cloud_data():
    totals = dict(orders=3, delivered=2, labeled=2, late=1, gmv_brl="30.01", freight_brl="5.00", payments_brl="35.01")
    return dict(audit=dict(build_id="build", built_at="2026-11-03T00:00:00Z", source_fingerprint="source"),
                rows=[dict(month="2018-01", state="SP", **totals)], totals=totals,
                daily={key: totals[key] for key in ("delivered", "labeled", "late", "gmv_brl")})


def baseline():
    return dict(order_count=3, delivered_order_count=2, labeled_deliveries=2, late_deliveries=1, delivered_items_gmv_brl="30.01")


def mock_query(monkeypatch, data, estimated=100):
    calls = []
    def query(args, **kwargs):
        calls.append((args, kwargs))
        return {"statistics": {"totalBytesProcessed": str(estimated)}} if "--dry_run=true" in args else [{"payload": json.dumps(data)}]
    monkeypatch.setattr(exporter, "command", query)
    return calls


def test_cloud_export_caps_cost_and_preserves_exact_financial_totals(monkeypatch, tmp_path):
    calls = mock_query(monkeypatch, cloud_data())
    path = tmp_path / "snapshot.json"
    report = exporter.export({"projectId": "project-id", "location": "us-central1"}, {"datasetSha256": "source"}, baseline(), "build", path)
    snapshot = json.loads(path.read_text())
    assert snapshot["totals"]["gmv_cents"] == 3001
    assert report["groups"] == 1
    assert report["aggregateSha256"] == aggregate_digest(snapshot["rows"])
    assert len(calls) == 2
    assert all("--maximum_bytes_billed=1073741824" in args for args, _ in calls)
    assert "--max_rows=1" in calls[1][0]


@pytest.mark.parametrize("fault", ["source", "build", "daily", "group_hash"])
def test_rejected_cloud_export_leaves_previous_file_unchanged(monkeypatch, tmp_path, fault):
    data = cloud_data()
    if fault in ("source", "build"):
        data["audit"]["source_fingerprint" if fault == "source" else "build_id"] = "wrong"
    if fault == "daily":
        data["daily"]["gmv_brl"] = "0"
    mock_query(monkeypatch, data)
    path = tmp_path / "snapshot.json"
    path.write_text("previous")
    with pytest.raises(ValueError):
        exporter.export({"projectId": "project-id", "location": "us-central1"}, {"datasetSha256": "source"}, baseline(), "build", path, expected_digest="wrong" if fault == "group_hash" else None)
    assert path.read_text() == "previous"


def test_over_budget_dry_run_does_not_submit_query(monkeypatch, tmp_path):
    calls = mock_query(monkeypatch, cloud_data(), estimated=2**31)
    with pytest.raises(ValueError, match="cap"):
        exporter.export({"projectId": "project-id", "location": "us-central1"}, {}, {}, "build", tmp_path / "out")
    assert len(calls) == 1


def test_export_sql_quotes_reserved_payload_field():
    query = exporter.snapshot_sql("project-id")
    assert "AS `rows`" in query
    assert "FROM `project-id.analytics.order_summary`" in query


def test_pipeline_does_not_export_after_model_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(run_cloud_pipeline, "load_raw", lambda *_: {})
    def failure(*_):
        raise ValueError("bad model")
    def forbidden(*_, **__):
        pytest.fail("Dashboard must not follow a failed model build")
    monkeypatch.setattr(run_cloud_pipeline, "build", failure)
    monkeypatch.setattr(run_cloud_pipeline, "export_dashboard", forbidden)
    assert run_cloud_pipeline.execute({"projectId": "project-id"}, {}, {}, {}, dashboard_output=tmp_path / "out")["status"] == "failure"


def test_pipeline_exports_after_build_and_reports_export_failure(monkeypatch, tmp_path):
    reference = tmp_path / "dashboard/dist/snapshot.json"
    reference.parent.mkdir(parents=True)
    reference.write_text(json.dumps({"aggregate_sha256": "reference"}))
    monkeypatch.setattr(run_cloud_pipeline, "ROOT", tmp_path / "infrastructure")
    monkeypatch.setattr(run_cloud_pipeline, "load_raw", lambda *_: {})
    monkeypatch.setattr(run_cloud_pipeline, "build", lambda *_: {"buildId": "build"})
    def exported(settings, contract, expected, build_id, output, **kwargs):
        assert build_id == "build"
        assert kwargs["expected_digest"] == "reference"
        return {"groups": 1}
    monkeypatch.setattr(run_cloud_pipeline, "export_dashboard", exported)
    report = run_cloud_pipeline.execute({"projectId": "project-id"}, {}, {}, {}, dashboard_output=tmp_path / "out")
    assert report["status"] == "success"
    assert list(report["stages"]) == ["raw", "models", "dashboard"]
    def failure(*_, **__):
        raise ValueError("dashboard mismatch")
    monkeypatch.setattr(run_cloud_pipeline, "export_dashboard", failure)
    report = run_cloud_pipeline.execute({"projectId": "project-id"}, {}, {}, {}, dashboard_output=tmp_path / "out")
    assert report["status"] == "failure"
    assert "models" in report["stages"]
    assert "dashboard" not in report["stages"]


@pytest.mark.parametrize("existing", [False, True])
def test_publication_writes_data_only_and_verifies_readback(monkeypatch, tmp_path, existing):
    data = cloud_data()
    snapshot = {"rows": [exporter.normalize(data["rows"][0], grouped=True)], "totals": exporter.normalize(data["totals"]), "source_fingerprint": "source"}
    snapshot["aggregate_sha256"] = aggregate_digest(snapshot["rows"])
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    monkeypatch.setenv("GITHUB_REPOSITORY", publisher.REPOSITORY)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    calls = []
    def api(method, route, payload=None, **kwargs):
        calls.append((method, route, payload))
        if route.startswith("git/ref/"):
            return {"object": {"sha": "old"}} if existing else None
        if route == "git/trees":
            assert [entry["path"] for entry in payload["tree"]] == ["snapshot.json"]
            return {"sha": "tree"}
        if route == "git/commits":
            assert payload["parents"] == (["old"] if existing else [])
            return {"sha": "new"}
        if route.startswith("contents/"):
            assert "ref=new" in route
            return {"encoding": "base64", "content": base64.b64encode(path.read_bytes()).decode()}
        assert payload.get("force") is not True
        return {}
    monkeypatch.setattr(publisher, "api", api)
    result = publisher.publish(path, baseline(), "source")
    assert result["readbackVerified"] is True
    assert calls[3][0] == ("PATCH" if existing else "POST")


def test_untrusted_publication_context_cannot_call_github(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/other")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    with pytest.raises(ValueError, match="trusted main"):
        publisher.publish(tmp_path / "absent", {}, "source")
