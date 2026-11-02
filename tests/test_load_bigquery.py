import pytest

from infrastructure import load_bigquery


def contract():
    return {"datasetSha256": "snapshot", "tables": [{
        "table": "customers", "file": "customers.csv", "rows": 2,
        "sha256": "source", "schema": [{"name": "customer_id", "type": "STRING", "mode": "NULLABLE"}],
    }]}


def test_verify_only_never_submits_load_job(monkeypatch):
    monkeypatch.setattr(load_bigquery, "validate_snapshot", lambda *_: None)
    calls = []

    def fake_command(arguments, **_):
        calls.append(arguments)
        return {"numRows": "2", "schema": {"fields": contract()["tables"][0]["schema"]}}

    monkeypatch.setattr(load_bigquery, "command", fake_command)
    settings = {"projectId": "project-id", "location": "us-central1", "rawBucket": "bucket", "sourcePrefix": "prefix/"}
    assert load_bigquery.run(settings, contract(), verify_only=True)["totalRows"] == 2
    assert all("load" not in arguments for arguments in calls)


def test_verify_rejects_incorrect_remote_row_count(monkeypatch):
    monkeypatch.setattr(load_bigquery, "validate_snapshot", lambda *_: None)
    monkeypatch.setattr(load_bigquery, "command", lambda *_args, **_kwargs: {"numRows": "3"})
    settings = {"projectId": "project-id", "location": "us-central1", "rawBucket": "bucket", "sourcePrefix": "prefix/"}
    with pytest.raises(ValueError, match="row count differs"):
        load_bigquery.run(settings, contract(), verify_only=True)


def test_invalid_snapshot_stops_before_cloud_commands(monkeypatch):
    def unexpected_command(*_, **__):
        pytest.fail("Invalid snapshot must be rejected before cloud operations")

    monkeypatch.setattr(load_bigquery, "command", unexpected_command)
    settings = {"projectId": "valid-project", "location": "us-central1", "sourcePrefix": "wrong/"}
    with pytest.raises(ValueError, match="source prefix"):
        load_bigquery.validate_snapshot(settings, contract())
