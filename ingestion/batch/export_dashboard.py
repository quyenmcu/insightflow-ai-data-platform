"""Export an aggregate-only dashboard snapshot from one verified warehouse build."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from ingestion.batch.load_olist import connect
from ingestion.batch.dashboard_contract import FIELDS, aggregate_digest, cents, validate_snapshot


def export_snapshot(connection, source_manifest, expected=None):
    connection.set_session(isolation_level="REPEATABLE READ", readonly=True)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT b.build_id, b.built_at, b.raw_run_id, r.manifest,
                              (SELECT max(run_id) FROM raw.ingestion_runs)
                              FROM analytics.build_runs b JOIN raw.ingestion_runs r ON r.run_id=b.raw_run_id
                              ORDER BY b.build_id DESC LIMIT 1""")
            audit = cursor.fetchone()
            if not audit or audit[2] != audit[4]:
                raise ValueError("Analytics build is missing or behind the latest raw ingestion")
            for table, record in audit[3].items():
                filename = {"customers": "olist_customers_dataset.csv", "orders": "olist_orders_dataset.csv",
                            "order_items": "olist_order_items_dataset.csv", "order_payments": "olist_order_payments_dataset.csv",
                            "order_reviews": "olist_order_reviews_dataset.csv", "products": "olist_products_dataset.csv",
                            "sellers": "olist_sellers_dataset.csv", "geolocation": "olist_geolocation_dataset.csv",
                            "product_category_name_translation": "product_category_name_translation.csv"}[table]
                registered = next((r for r in source_manifest["files"] if r["file"] == filename), None)
                if registered is None or registered["sha256"] != record["sha256"]:
                    raise ValueError("Warehouse source differs from registered source snapshot")
            if len(audit[3]) != len(source_manifest["files"]):
                raise ValueError("Incomplete source provenance")
            cursor.execute("""SELECT to_char(order_purchase_timestamp, 'YYYY-MM'), coalesce(customer_state, 'Unknown'),
                count(*), count(*) FILTER (WHERE order_status='delivered'),
                count(is_late_delivery), count(*) FILTER (WHERE is_late_delivery),
                coalesce(sum(items_value_brl) FILTER (WHERE order_status='delivered'),0),
                coalesce(sum(freight_value_brl) FILTER (WHERE order_status='delivered'),0),
                coalesce(sum(payment_value_brl) FILTER (WHERE order_status='delivered'),0)
                FROM analytics.order_summary GROUP BY 1,2 ORDER BY 1,2""")
            rows = [{"month": row[0], "state": row[1], **dict(zip(FIELDS, [int(x) for x in row[2:6]] + [cents(x) for x in row[6:]]))}
                    for row in cursor.fetchall()]
            cursor.execute("""SELECT count(*), count(*) FILTER (WHERE order_status='delivered'), count(is_late_delivery),
                count(*) FILTER (WHERE is_late_delivery),
                coalesce(sum(items_value_brl) FILTER (WHERE order_status='delivered'),0),
                coalesce(sum(freight_value_brl) FILTER (WHERE order_status='delivered'),0),
                coalesce(sum(payment_value_brl) FILTER (WHERE order_status='delivered'),0)
                FROM analytics.order_summary""")
            total = cursor.fetchone()
            totals = dict(zip(FIELDS, [int(x) for x in total[:4]] + [cents(x) for x in total[4:]]))
            cursor.execute("""SELECT sum(delivered_order_count), sum(delivery_label_count), sum(late_delivery_count),
                              sum(items_gmv_brl) FROM analytics.daily_sales""")
            daily = cursor.fetchone()
            if tuple(totals[k] for k in ("delivered", "labeled", "late", "gmv_cents")) != (int(daily[0]), int(daily[1]), int(daily[2]), cents(daily[3])):
                raise ValueError("Daily sales totals differ from order summary")
    snapshot = {"schema_version": 1, "exported_at": datetime.now(timezone.utc).isoformat(),
                "source": "Olist Brazilian E-Commerce Public Dataset",
                "source_url": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
                "source_fingerprint": source_manifest["datasetSha256"],
                "warehouse": "PostgreSQL analytics.order_summary + analytics.daily_sales",
                "warehouse_built_at": audit[1].isoformat(), "warehouse_build_id": audit[0],
                "source_period": {"from": min(r["month"] for r in rows), "to": max(r["month"] for r in rows)},
                "currency": "BRL", "grain": "purchase calendar month × customer state",
                "totals": totals, "rows": rows}
    validate_snapshot(snapshot, expected)
    snapshot["aggregate_sha256"] = aggregate_digest(rows)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dashboard/dist/snapshot.json"))
    parser.add_argument("--source-manifest", type=Path, default=Path("infrastructure/source_manifest.json"))
    parser.add_argument("--baseline", type=Path, default=Path("infrastructure/postgres_baseline.json"))
    args = parser.parse_args()
    connection = connect()
    try:
        snapshot = export_snapshot(connection, json.loads(args.source_manifest.read_text(encoding="utf-8-sig")),
                                   json.loads(args.baseline.read_text()))
    finally:
        connection.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), "groups": len(snapshot["rows"]), "totals": snapshot["totals"],
                      "aggregate_sha256": snapshot["aggregate_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
