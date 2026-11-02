from infrastructure import run_cloud_pipeline


def test_raw_failure_stops_before_model_publication(monkeypatch):
    def failed_load(*_):
        raise RuntimeError("source checksum mismatch")

    def forbidden_build(*_):
        raise AssertionError("Model build must not follow a failed raw load")

    monkeypatch.setattr(run_cloud_pipeline, "load_raw", failed_load)
    monkeypatch.setattr(run_cloud_pipeline, "build", forbidden_build)
    report = run_cloud_pipeline.execute({"projectId": "project"}, {}, {}, {})
    assert report["status"] == "failure"
    assert report["stages"] == {}
    assert "checksum mismatch" in report["error"]


def test_stage_order_and_success_report(monkeypatch):
    stages = []

    def raw(*_):
        stages.append("raw")
        return {"totalRows": 12}

    def model(*_):
        assert stages == ["raw"]
        stages.append("models")
        return {"buildId": "build", "bytesBilled": "100"}

    monkeypatch.setattr(run_cloud_pipeline, "load_raw", raw)
    monkeypatch.setattr(run_cloud_pipeline, "build", model)
    report = run_cloud_pipeline.execute({"projectId": "project"}, {}, {}, {})
    assert report["status"] == "success"
    assert stages == ["raw", "models"]
    assert report["stages"]["raw"]["totalRows"] == 12


def test_failed_model_keeps_raw_stage_evidence(monkeypatch):
    monkeypatch.setattr(run_cloud_pipeline, "load_raw", lambda *_: {"totalRows": 12})

    def fail(*_):
        raise RuntimeError("parity mismatch")

    monkeypatch.setattr(run_cloud_pipeline, "build", fail)
    report = run_cloud_pipeline.execute({"projectId": "project"}, {}, {}, {})
    assert report["status"] == "failure"
    assert report["stages"]["raw"] == {"totalRows": 12}
    assert "models" not in report["stages"]
