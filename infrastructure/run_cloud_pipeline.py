"""Run the fixed Olist snapshot through raw ingestion and model publication."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

# Support both the module entry point and the older documented script path.
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from .load_bigquery import run as load_raw
    from .build_bigquery import build
except ImportError:
    from load_bigquery import run as load_raw
    from build_bigquery import build


ROOT = Path(__file__).parent
from infrastructure.export_dashboard import export as export_dashboard


def execute(settings, contract, model, baseline, *, dashboard_output=None):
    report = {"startedAt": datetime.now(timezone.utc).isoformat(), "projectId": settings["projectId"], "status": "running", "stages": {}}
    try:
        report["stages"]["raw"] = load_raw(settings, contract)
        report["stages"]["models"] = build(settings, contract, model, baseline)
        if dashboard_output is not None:
            report["stages"]["dashboard"] = export_dashboard(settings, contract, baseline,
                report["stages"]["models"]["buildId"], dashboard_output,
                expected_digest=json.loads((ROOT.parent / "dashboard/dist/snapshot.json").read_text())["aggregate_sha256"])
        report["status"] = "success"
    except Exception as error:
        report["status"] = "failure"
        report["error"] = str(error)
    report["finishedAt"] = datetime.now(timezone.utc).isoformat()
    return report


def save_report(report, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        lines = ["## InsightFlow cloud pipeline", f"Result: **{report['status']}**", f"Project: `{report['projectId']}`"]
        if report["status"] == "success":
            raw = report["stages"]["raw"]
            models = report["stages"]["models"]
            lines.extend([f"Raw rows verified: **{raw['totalRows']:,}**", f"Model build: `{models['buildId']}`", f"Model query billed bytes: {models['bytesBilled']}"])
            if "dashboard" in report["stages"]:
                dashboard = report["stages"]["dashboard"]
                lines.append(f"Dashboard groups verified: **{dashboard['groups']}**; aggregate SHA-256: `{dashboard['aggregateSha256']}`")
        else:
            lines.append("The pipeline stopped. Review the stage logs and JSON report. The dashboard data branch is not updated unless all warehouse and export checks succeed; an export failure can occur after analytics tables were successfully refreshed.")
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("\n\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "cloud_pipeline.json")
    parser.add_argument("--report", type=Path, default=Path("data/processed/cloud_pipeline_report.json"))
    parser.add_argument("--dashboard-output", type=Path)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8-sig"))
    report = execute(read(args.config), read(ROOT / "bigquery_tables.json"), read(ROOT / "bigquery_models.json"), read(ROOT / "postgres_baseline.json"), dashboard_output=args.dashboard_output)
    save_report(report, args.report)
    print(json.dumps(report, indent=2), flush=True)
    if report["status"] != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
