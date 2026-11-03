"""Read a bounded BigQuery snapshot after a verified build; export aggregates only."""

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import re

from ingestion.batch.dashboard_contract import FIELDS, aggregate_digest, cents, validate_snapshot
from .load_bigquery import command


def snapshot_sql(project):
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise ValueError("Invalid Google Cloud project ID")
    measures = """COUNT(*) AS orders, COUNTIF(order_status='delivered') AS delivered,
      COUNT(is_late_delivery) AS labeled, COUNTIF(is_late_delivery) AS late,
      COALESCE(SUM(IF(order_status='delivered',items_value_brl,0)),0) AS gmv_brl,
      COALESCE(SUM(IF(order_status='delivered',freight_value_brl,0)),0) AS freight_brl,
      COALESCE(SUM(IF(order_status='delivered',payment_value_brl,0)),0) AS payments_brl"""
    return f"""WITH grouped AS (
      SELECT FORMAT_DATETIME('%Y-%m',order_purchase_timestamp) AS month,
        COALESCE(customer_state,'Unknown') AS state, {measures}
      FROM `{project}.analytics.order_summary` GROUP BY 1,2
    ), totals AS (SELECT {measures} FROM `{project}.analytics.order_summary`),
    audit AS (SELECT build_id, built_at, source_fingerprint FROM `{project}.analytics.build_runs`
      ORDER BY built_at DESC, build_id DESC LIMIT 1),
    daily AS (SELECT SUM(delivered_order_count) AS delivered, SUM(delivery_label_count) AS labeled,
      SUM(late_delivery_count) AS late, SUM(items_gmv_brl) AS gmv_brl FROM `{project}.analytics.daily_sales`)
    SELECT TO_JSON_STRING(STRUCT(
      (SELECT AS STRUCT * FROM audit) AS audit,
      ARRAY(SELECT AS STRUCT * FROM grouped ORDER BY month,state) AS rows,
      (SELECT AS STRUCT * FROM totals) AS totals,
      (SELECT AS STRUCT * FROM daily) AS daily)) AS payload"""


def normalize(record, *, grouped=False):
    counts = {field: int(record[field]) for field in FIELDS[:4]}
    amounts = {f"{field}_cents": cents(str(record[f"{field}_brl"])) for field in ("gmv", "freight", "payments")}
    return ({"month": record["month"], "state": record["state"]} if grouped else {}) | counts | amounts


def export(settings, contract, baseline, build_id, output, *, maximum_bytes_billed=1073741824, expected_digest=None):
    if not 0 < maximum_bytes_billed <= 1073741824:
        raise ValueError("Dashboard export cap must be between 1 byte and 1 GiB")
    query = snapshot_sql(settings["projectId"])
    common = ["bq", f"--project_id={settings['projectId']}", f"--location={settings['location']}", "--format=json"]
    args = ["query", "--use_legacy_sql=false", f"--maximum_bytes_billed={maximum_bytes_billed}"]
    dry = command(common + args + ["--dry_run=true"], input_text=query, parse_json=True)
    estimated = int(dry["statistics"]["totalBytesProcessed"])
    if estimated > maximum_bytes_billed:
        raise ValueError("Dashboard export exceeds billed-byte cap")
    result = command(common + args + ["--max_rows=1"], input_text=query, parse_json=True)
    if len(result) != 1:
        raise ValueError("Expected one dashboard export payload")
    data = json.loads(result[0]["payload"], parse_float=Decimal)
    audit = data["audit"]
    if audit is None or audit["build_id"] != build_id or audit["source_fingerprint"] != contract["datasetSha256"]:
        raise ValueError("Dashboard build/source differs from the verified pipeline build")
    rows = [normalize(row, grouped=True) for row in data["rows"]]
    totals = normalize(data["totals"])
    daily = data["daily"]
    if any(totals[field] != int(daily[field]) for field in ("delivered", "labeled", "late")) or totals["gmv_cents"] != cents(str(daily["gmv_brl"])):
        raise ValueError("Dashboard daily sales reconciliation failed")
    snapshot = {"schema_version": 1, "exported_at": datetime.now(timezone.utc).isoformat(),
      "source": "Olist Brazilian E-Commerce Public Dataset", "source_url": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
      "source_fingerprint": contract["datasetSha256"], "warehouse": "BigQuery analytics.order_summary + analytics.daily_sales",
      "warehouse_build_id": audit["build_id"], "warehouse_built_at": audit["built_at"],
      "currency": "BRL", "grain": "purchase calendar month × customer state", "totals": totals, "rows": rows,
      "source_period": {"from": min(row["month"] for row in rows), "to": max(row["month"] for row in rows)}}
    validate_snapshot(snapshot, baseline)
    snapshot["aggregate_sha256"] = aggregate_digest(rows)
    if expected_digest is not None and snapshot["aggregate_sha256"] != expected_digest:
        raise ValueError("BigQuery month/state groups differ from the verified PostgreSQL reference")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(output)
    return {"buildId": build_id, "groups": len(rows), "aggregateSha256": snapshot["aggregate_sha256"],
            "estimatedBytes": estimated, "maximumBytesBilled": maximum_bytes_billed, "output": str(output)}
