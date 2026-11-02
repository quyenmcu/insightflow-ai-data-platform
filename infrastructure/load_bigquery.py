"""Load a verified Olist snapshot from Cloud Storage into BigQuery raw tables.

Uses the bq and gcloud binaries in Google's official CLI image. All load schemas
are explicit STRING columns. Each table is replaced atomically; the nine-table
batch is not a single transaction. A failed run can be rerun without appending.
"""

import argparse
import base64
import json
from pathlib import Path
import re
import subprocess
import tempfile
import uuid


def command(arguments, *, parse_json=False):
    result = subprocess.run(arguments, text=True, capture_output=True)
    if result.returncode:
        # These commands contain project/table identifiers, not auth credentials.
        raise RuntimeError(f"{arguments[0]} command failed: {result.stderr.strip()} {result.stdout.strip()}")
    return json.loads(result.stdout) if parse_json else result.stdout


def validate_snapshot(settings, contract):
    project = settings["projectId"]
    location = settings["location"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise ValueError("Invalid Google Cloud project ID")
    if settings["sourcePrefix"] != f"olist/{contract['datasetSha256']}/":
        raise ValueError("Configured source prefix differs from the validated snapshot")
    if len(contract["tables"]) != 9 or len({table["table"] for table in contract["tables"]}) != 9:
        raise ValueError("Expected nine distinct raw tables")
    metadata = command(["bq", f"--project_id={project}", "--format=json", "show", "--dataset", f"{project}:raw"], parse_json=True)
    if metadata["location"].lower() != location.lower():
        raise ValueError("Raw dataset location differs from the configured location")
    bucket = command(["gcloud", "storage", "buckets", "describe", f"gs://{settings['rawBucket']}", f"--project={project}", "--format=json"], parse_json=True)
    if bucket["location"].lower() != location.lower():
        raise ValueError("Source bucket and raw dataset must be co-located")
    objects = command([
        "gcloud", "storage", "ls", "--json",
        f"gs://{settings['rawBucket']}/{settings['sourcePrefix']}*.csv", f"--project={project}",
    ], parse_json=True)
    remote = {obj["metadata"]["name"]: obj["metadata"] for obj in objects}
    if len(remote) != 9:
        raise ValueError("Expected exactly nine source CSV objects")
    for table in contract["tables"]:
        if not re.fullmatch(r"[a-z_]+", table["table"]):
            raise ValueError("Invalid raw table identifier")
        if Path(table["file"]).name != table["file"]:
            raise ValueError("Source must be a filename without directories")
        if not table["schema"] or any(field["type"] != "STRING" or field["mode"] != "NULLABLE" for field in table["schema"]):
            raise ValueError("Raw load requires an explicit nullable STRING schema")
        source = remote.get(settings["sourcePrefix"] + table["file"])
        if source is None or int(source["size"]) != table["bytes"] or base64.b64decode(source["md5Hash"]).hex() != table["md5"]:
            raise ValueError(f"Cloud source differs from the validated snapshot: {table['file']}")


def run(settings, contract, verify_only=False):
    validate_snapshot(settings, contract)
    project = settings["projectId"]
    common = ["bq", f"--project_id={project}", f"--location={settings['location']}", "--format=json"]
    report = []
    for table in contract["tables"]:
        destination = f"{project}:raw.{table['table']}"
        source = f"gs://{settings['rawBucket']}/{settings['sourcePrefix']}{table['file']}"
        job_id = None
        if not verify_only:
            print(f"Loading raw.{table['table']} ({table['rows']:,} expected rows)...", flush=True)
            with tempfile.TemporaryDirectory() as directory:
                schema_path = Path(directory) / "schema.json"
                schema_path.write_text(json.dumps(table["schema"]), encoding="utf-8")
                job_id = f"insightflow_raw_{table['table']}_{uuid.uuid4().hex}"
                command(common + [
                    f"--job_id={job_id}", "load", "--replace", "--source_format=CSV",
                    "--skip_leading_rows=1", "--allow_quoted_newlines=true", "--encoding=UTF-8",
                    "--max_bad_records=0", "--ignore_unknown_values=false",
                    "--preserve_ascii_control_characters=true",
                    destination, source, str(schema_path),
                ])
            job = command(common + ["show", "--job=true", job_id], parse_json=True)
            if job["status"]["state"] != "DONE" or job["status"].get("errorResult"):
                raise ValueError(f"Load job did not succeed: {job_id}")
            load_stats = job["statistics"]["load"]
            if int(load_stats["outputRows"]) != table["rows"] or int(load_stats.get("badRecords", 0)) != 0:
                raise ValueError(f"Load job count or rejected rows differ: {table['table']}")
        metadata = command(common + ["show", destination], parse_json=True)
        if int(metadata["numRows"]) != table["rows"]:
            raise ValueError(f"BigQuery row count differs from source: {table['table']}")
        fields = [{key: field.get(key, "NULLABLE") for key in ("name", "type", "mode")} for field in metadata["schema"]["fields"]]
        if fields != table["schema"]:
            raise ValueError(f"BigQuery schema differs from source contract: {table['table']}")
        report.append({"table": table["table"], "rows": int(metadata["numRows"]), "sourceSha256": table["sha256"], "jobId": job_id})
        print(f"Verified raw.{table['table']}: {table['rows']:,} rows", flush=True)
    return {"projectId": project, "sourceFingerprint": contract["datasetSha256"], "tables": report, "totalRows": sum(table["rows"] for table in report)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    # Settings arrive on stdin, so no credentials/billing config is mounted.
    import sys
    settings = json.load(sys.stdin)
    contract = json.loads(Path(__file__).with_name("bigquery_tables.json").read_text(encoding="utf-8-sig"))
    try:
        result = run(settings, contract, args.verify_only)
    except (ValueError, RuntimeError, KeyError) as error:
        parser.exit(1, f"BigQuery raw load stopped: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
