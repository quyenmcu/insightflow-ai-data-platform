import pytest

from infrastructure import build_bigquery


def baseline():
    return {metric: "1" for metric in build_bigquery.METRICS}


def forbid_cloud(*_args, **_kwargs):
    pytest.fail("Rejected input must not submit cloud operations")


def test_invalid_baseline_does_not_touch_cloud(monkeypatch):
    monkeypatch.setattr(build_bigquery, "command", forbid_cloud)
    monkeypatch.setattr(build_bigquery, "verify_raw", forbid_cloud)
    invalid = baseline()
    invalid["items_value_brl"] = "NaN"
    with pytest.raises(ValueError, match="baseline"):
        build_bigquery.build({}, {}, {}, invalid)


def test_excessive_byte_limit_does_not_touch_cloud(monkeypatch):
    monkeypatch.setattr(build_bigquery, "command", forbid_cloud)
    monkeypatch.setattr(build_bigquery, "verify_raw", forbid_cloud)
    with pytest.raises(ValueError, match="billed bytes"):
        build_bigquery.build({}, {}, {}, baseline(), maximum_bytes_billed=2**40)


def test_dry_run_cannot_publish_models(monkeypatch):
    monkeypatch.setattr(build_bigquery, "sql_scripts", lambda *_: ("SCHEMA", "MUTATION", "PROJECTION", "VERIFY"))
    monkeypatch.setattr(build_bigquery, "verify_raw", lambda *_args, **_kwargs: {})
    calls = []

    def fake_command(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return {"statistics": {"totalBytesProcessed": "100"}}

    monkeypatch.setattr(build_bigquery, "command", fake_command)
    result = build_bigquery.build({"projectId": "project-id", "location": "us-central1"}, {}, {}, baseline(), dry_run_only=True)
    assert result["dryRunOnly"] is True
    assert len(calls) == 1
    assert "--dry_run=true" in calls[0][0]
    assert calls[0][1]["input_text"] == "PROJECTION"
