"""Build validated typed staging and analytics tables with atomic publication."""

import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
import uuid

try:
    from .load_bigquery import command, run as verify_raw
except ImportError:  # Running as a file in the Cloud CLI image.
    from load_bigquery import command, run as verify_raw


ROOT = Path(__file__).parent
SUMMARY_FIELDS = {
    **{field: "STRING" for field in "order_id customer_id customer_unique_id customer_city customer_state order_status".split()},
    **{field: "DATETIME" for field in "order_purchase_timestamp order_estimated_delivery_date order_delivered_customer_date".split()},
    "item_count": "INT64", "items_value_brl": "NUMERIC", "freight_value_brl": "NUMERIC",
    "payment_count": "INT64", "payment_value_brl": "NUMERIC", "review_count": "INT64",
    "mean_review_score": "NUMERIC", "is_late_delivery": "BOOL",
}
DAILY_FIELDS = {
    "purchase_date": "DATE", "delivered_order_count": "INT64", "unique_customer_count": "INT64",
    "item_count": "INT64", "items_gmv_brl": "NUMERIC", "freight_value_brl": "NUMERIC",
    "payment_value_brl": "NUMERIC", "average_order_items_value_brl": "NUMERIC",
    "delivery_label_count": "INT64", "late_delivery_count": "INT64",
}
METRICS = {
    "order_count": ("INT64", "(SELECT COUNT(*) FROM tmp_order_summary)"),
    "items_value_brl": ("NUMERIC", "(SELECT SUM(items_value_brl) FROM tmp_order_summary)"),
    "payment_value_brl": ("NUMERIC", "(SELECT SUM(payment_value_brl) FROM tmp_order_summary)"),
    "delivered_order_count": ("INT64", "(SELECT SUM(delivered_order_count) FROM tmp_daily_sales)"),
    "delivered_items_gmv_brl": ("NUMERIC", "(SELECT SUM(items_gmv_brl) FROM tmp_daily_sales)"),
    "labeled_deliveries": ("INT64", "(SELECT SUM(delivery_label_count) FROM tmp_daily_sales)"),
    "late_deliveries": ("INT64", "(SELECT SUM(late_delivery_count) FROM tmp_daily_sales)"),
}


def identifier(value):
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
        raise ValueError(f"Invalid model identifier: {value}")
    return f"`{value}`"


def expression(field):
    name = field["source"]
    value = identifier(name)
    if name in {"review_comment_title", "review_comment_message"}:
        return f"NULLIF({value}, '')"
    value = f"NULLIF(TRIM({value}, ' '), '')"
    if name.endswith("_state"):
        value = f"UPPER({value})"
    elif name.endswith("_city") or name in {"order_status", "payment_type", "product_category_name", "product_category_name_english"}:
        value = f"LOWER({value})"
    return f"CAST({value} AS {field['type']})"


def sql_scripts(project, model, contract):
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise ValueError("Invalid Google Cloud project ID")
    expected = {table["table"]: table["rows"] for table in contract["tables"]}
    if len(expected) != 9 or {table["table"] for table in model["tables"]} != set(expected):
        raise ValueError("Typed models must cover exactly the nine loaded raw tables")
    init, refresh, dry_selects = [], ["BEGIN TRANSACTION;"], []
    targets = []
    for table in model["tables"]:
        name = table["table"]
        identifier(name)
        columns = ", ".join(f"{identifier(field['name'])} {field['type']}" for field in table["fields"])
        target = f"`{project}.staging.{name}`"
        init.append(f"CREATE TABLE IF NOT EXISTS {target} ({columns});")
        selections = ", ".join(f"{expression(field)} AS {identifier(field['name'])}" for field in table["fields"])
        select = f"SELECT {selections} FROM `{project}.raw.{name}`"
        dry_selects.append(f"SELECT TO_JSON_STRING(t) AS parsed_row FROM ({select}) t")
        refresh.append(f"CREATE TEMP TABLE tmp_{name} AS {select};")
        validations = [f"COUNT(*) = {expected[name]}"]
        required = [f"{identifier(field['name'])} IS NULL" for field in table["fields"] if field["required"]]
        if required:
            validations.append(f"COUNTIF({' OR '.join(required)}) = 0")
        if table["keys"]:
            keys = ", ".join(map(identifier, table["keys"]))
            validations.append(f"COUNT(*) = COUNT(DISTINCT TO_JSON_STRING(STRUCT({keys})))")
        if table["checks"]:
            invalid = " OR ".join(f"NOT ({check})" for check in table["checks"])
            validations.append(f"COUNTIF({invalid}) = 0")
        refresh.append(f"ASSERT (SELECT {' AND '.join(validations)} FROM tmp_{name}) AS '{name}: row count, required field, key, or range validation failed';")
        targets.append((target, f"tmp_{name}"))
    references = []
    for table in model["tables"]:
        for field, parent, parent_field in table["foreignKeys"]:
            references.append(f"NOT EXISTS(SELECT 1 FROM tmp_{table['table']} c LEFT JOIN tmp_{parent} p ON c.{identifier(field)} = p.{identifier(parent_field)} WHERE c.{identifier(field)} IS NOT NULL AND p.{identifier(parent_field)} IS NULL)")
    refresh.append(f"ASSERT {' AND '.join(references)} AS 'orphan foreign key';")
    refresh.append(ROOT.joinpath("bigquery_analytics.sql").read_text(encoding="utf-8"))
    for name, fields in (("order_summary", SUMMARY_FIELDS), ("daily_sales", DAILY_FIELDS)):
        columns = ", ".join(f"{identifier(field)} {datatype}" for field, datatype in fields.items())
        target = f"`{project}.analytics.{name}`"
        init.append(f"CREATE TABLE IF NOT EXISTS {target} ({columns});")
        targets.append((target, f"tmp_{name}"))
    init.append(f"CREATE TABLE IF NOT EXISTS `{project}.analytics.build_runs` (build_id STRING, built_at TIMESTAMP, source_fingerprint STRING, row_counts JSON);")
    refresh.append("""ASSERT
        (SELECT COUNT(*) FROM tmp_order_summary) = (SELECT COUNT(*) FROM tmp_orders)
        AND (SELECT COUNT(DISTINCT order_id) FROM tmp_order_summary) = (SELECT COUNT(*) FROM tmp_orders)
        AND (SELECT SUM(items_value_brl) FROM tmp_order_summary) = (SELECT SUM(price) FROM tmp_order_items)
        AND (SELECT SUM(payment_value_brl) FROM tmp_order_summary) = (SELECT SUM(payment_value) FROM tmp_order_payments)
        AS 'order grain or financial totals mismatch';""")
    parity = " AND ".join(f"{value} = @expected_{metric}" for metric, (_, value) in METRICS.items())
    refresh.append(f"ASSERT {parity} AS 'PostgreSQL metrics parity mismatch';")
    # Every assertion runs before publication; all eleven tables change together.
    for target, temporary in targets:
        refresh.extend([f"DELETE FROM {target} WHERE TRUE;", f"INSERT INTO {target} SELECT * FROM {temporary};"])
    row_counts = ", ".join(f"STRUCT('{table}' AS table_name, {rows} AS row_count)" for table, rows in expected.items())
    refresh.append(f"INSERT INTO `{project}.analytics.build_runs` VALUES (@build_id, CURRENT_TIMESTAMP(), @source_fingerprint, TO_JSON([{row_counts}]));")
    refresh.append("COMMIT TRANSACTION;")
    # Remove transaction-local storage once its rows have been published.
    refresh.extend(f"DROP TABLE {temporary};" for _, temporary in targets)
    verification = "SELECT " + ", ".join(f"{value.replace('tmp_order_summary', f'`{project}.analytics.order_summary`').replace('tmp_daily_sales', f'`{project}.analytics.daily_sales`')} AS {metric}" for metric, (_, value) in METRICS.items())
    return "\n".join(init), "\n".join(refresh), "\nUNION ALL\n".join(dry_selects), verification


def build(settings, contract, model, baseline, *, dry_run_only=False, maximum_bytes_billed=1073741824):
    # Validate the baseline before creating or mutating cloud objects.
    parameters = []
    for metric, (datatype, _) in METRICS.items():
        value = Decimal(str(baseline[metric]))
        if not value.is_finite() or value < 0 or (datatype == "INT64" and value != value.to_integral_value()):
            raise ValueError(f"Invalid PostgreSQL baseline: {metric}")
        parameters.append(f"--parameter=expected_{metric}:{datatype}:{value}")
    if not 0 < maximum_bytes_billed <= 1073741824:
        raise ValueError("Maximum billed bytes must be between 1 and 1 GiB")
    init, refresh, dry_selects, verification = sql_scripts(settings["projectId"], model, contract)
    verify_raw(settings, contract, verify_only=True)
    common = ["bq", f"--project_id={settings['projectId']}", f"--location={settings['location']}", "--format=json"]
    query = ["query", "--use_legacy_sql=false", f"--maximum_bytes_billed={maximum_bytes_billed}"]
    # Dry-run every source projection in a UNION; script dry runs stop at temp DDL.
    dry_job = command(common + query + ["--dry_run=true"], input_text=dry_selects, parse_json=True)
    source_bytes = int(dry_job["statistics"]["totalBytesProcessed"])
    if source_bytes > maximum_bytes_billed:
        raise ValueError("Source projection exceeds the configured byte limit")
    print(f"Dry run validated {source_bytes:,} source bytes; cap {maximum_bytes_billed:,} bytes.", flush=True)
    if dry_run_only:
        return {"dryRunOnly": True, "estimatedSourceBytes": source_bytes, "maximumBytesBilled": maximum_bytes_billed}
    fixture = ROOT.joinpath("test_bigquery_analytics.sql").read_text().replace(
        "-- ANALYTICS_MODELS", ROOT.joinpath("bigquery_analytics.sql").read_text()
    )
    print("Checking analytics definitions with synthetic BigQuery fixtures...", flush=True)
    command(common + query, input_text=fixture)
    print("Initializing model schemas...", flush=True)
    command(common + query, input_text=init)
    build_id = uuid.uuid4().hex
    job_id = f"insightflow_models_{build_id}"
    print(f"Building and validating models: {job_id}", flush=True)
    command(common + [f"--job_id={job_id}"] + query + parameters + [f"--parameter=build_id:STRING:{build_id}", f"--parameter=source_fingerprint:STRING:{contract['datasetSha256']}"], input_text=refresh)
    result = command(common + query, input_text=verification, parse_json=True)[0]
    for metric in METRICS:
        if Decimal(str(result[metric])) != Decimal(str(baseline[metric])):
            raise ValueError(f"Published analytics parity mismatch: {metric}")
    job = command(common + ["show", "--job=true", job_id], parse_json=True)
    return {"buildId": build_id, "jobId": job_id, "sourceFingerprint": contract["datasetSha256"], "metrics": result, "bytesBilled": job["statistics"]["query"].get("totalBytesBilled"), "maximumBytesBilled": maximum_bytes_billed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    settings = json.load(sys.stdin)
    contract = json.loads(ROOT.joinpath("bigquery_tables.json").read_text())
    model = json.loads(ROOT.joinpath("bigquery_models.json").read_text())
    baseline = json.loads(ROOT.joinpath("postgres_baseline.json").read_text())
    try:
        print(json.dumps(build(settings, contract, model, baseline, dry_run_only=args.dry_run), indent=2))
    except (ValueError, RuntimeError, KeyError) as error:
        parser.exit(1, f"BigQuery model build stopped: {error}\n")


if __name__ == "__main__":
    main()
