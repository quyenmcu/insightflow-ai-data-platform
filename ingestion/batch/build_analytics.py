"""Atomically refresh typed staging tables and e-commerce analytics views."""

import argparse
import json
from pathlib import Path

import psycopg2
from psycopg2 import sql

from ingestion.batch.load_olist import TABLES, connect


ORDER = (
    "customers", "sellers", "product_category_name_translation", "products",
    "orders", "order_items", "order_payments", "order_reviews", "geolocation",
)
INTEGERS = set("order_item_id payment_sequential payment_installments review_score product_name_lenght product_description_lenght product_photos_qty product_weight_g product_length_cm product_height_cm product_width_cm".split())
DECIMALS = set("price freight_value payment_value geolocation_lat geolocation_lng".split())
TIMESTAMPS = set("order_purchase_timestamp order_approved_at order_delivered_carrier_date order_delivered_customer_date order_estimated_delivery_date shipping_limit_date review_creation_date review_answer_timestamp".split())
RENAMES = {"product_name_lenght": "product_name_length", "product_description_lenght": "product_description_length"}
REQUIRED = {
    "orders": {"customer_id", "order_status", "order_purchase_timestamp"},
    "order_items": {"product_id", "seller_id", "price", "freight_value"},
    "order_payments": {"payment_type", "payment_installments", "payment_value"},
    "order_reviews": {"review_id", "order_id", "review_score"},
}
FOREIGN_KEYS = {
    "orders": [("customer_id", "customers", "customer_id")],
    "order_items": [("order_id", "orders", "order_id"), ("product_id", "products", "product_id"), ("seller_id", "sellers", "seller_id")],
    "order_payments": [("order_id", "orders", "order_id")],
    "order_reviews": [("order_id", "orders", "order_id")],
}
CHECKS = {
    "order_items": ["order_item_id > 0", "price >= 0", "freight_value >= 0"],
    "order_payments": ["payment_sequential > 0", "payment_installments >= 0", "payment_value >= 0"],
    "order_reviews": ["review_score BETWEEN 1 AND 5"],
    "products": [f"{RENAMES.get(field, field)} >= 0" for field in INTEGERS if field.startswith("product_")],
    "geolocation": ["geolocation_lat BETWEEN -90 AND 90", "geolocation_lng BETWEEN -180 AND 180"],
}


def column_type(field):
    if field in INTEGERS:
        return "INTEGER"
    if field in DECIMALS:
        return "NUMERIC"
    if field in TIMESTAMPS:
        # Source timestamps have no documented timezone; do not invent one.
        return "TIMESTAMP WITHOUT TIME ZONE"
    return "TEXT"


def expression(field):
    value = sql.Identifier(field)
    if field in {"review_comment_title", "review_comment_message"}:
        return sql.SQL("NULLIF({}, '')").format(value)
    value = sql.SQL("NULLIF(BTRIM({}), '')").format(value)
    if field.endswith("_state"):
        value = sql.SQL("UPPER({})").format(value)
    elif field.endswith("_city") or field in {"order_status", "payment_type", "product_category_name", "product_category_name_english"}:
        value = sql.SQL("LOWER({})").format(value)
    return sql.SQL("({})::{}").format(value, sql.SQL(column_type(field)))


def build(connection):
    report = {}
    with connection:
        with connection.cursor() as cursor:
            # Share the ingestion lock to read one complete raw snapshot.
            cursor.execute("SELECT pg_advisory_xact_lock(470011)")
            cursor.execute("SELECT MAX(run_id) FROM raw.ingestion_runs")
            source_run = cursor.fetchone()[0]
            if source_run is None:
                raise ValueError("Load the Olist raw data before building analytics")
            cursor.execute("CREATE SCHEMA IF NOT EXISTS staging")
            cursor.execute("CREATE SCHEMA IF NOT EXISTS analytics")
            for table in ORDER:
                _, columns, key_text = TABLES[table]
                keys = key_text.split()
                required = set(keys) | REQUIRED.get(table, set())
                definitions = [
                    sql.SQL("{} {} {}").format(
                        sql.Identifier(RENAMES.get(field, field)),
                        sql.SQL(column_type(field)),
                        sql.SQL("NOT NULL" if field in required else ""),
                    ) for field in columns.split()
                ]
                if keys:
                    definitions.append(sql.SQL("PRIMARY KEY ({})").format(sql.SQL(", ").join(map(sql.Identifier, keys))))
                for field, parent, parent_key in FOREIGN_KEYS.get(table, []):
                    definitions.append(sql.SQL("FOREIGN KEY ({}) REFERENCES {} ({})").format(
                        sql.Identifier(field), sql.Identifier("staging", parent), sql.Identifier(parent_key)
                    ))
                definitions.extend(sql.SQL("CHECK ({})").format(sql.SQL(check)) for check in CHECKS.get(table, []))
                cursor.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
                    sql.Identifier("staging", table), sql.SQL(", ").join(definitions)
                ))
            # Truncate all related tables together; no CASCADE into other objects.
            cursor.execute(sql.SQL("TRUNCATE TABLE {}").format(
                sql.SQL(", ").join(sql.Identifier("staging", table) for table in ORDER)
            ))
            for table in ORDER:
                fields = TABLES[table][1].split()
                cursor.execute(sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
                    sql.Identifier("staging", table),
                    sql.SQL(", ").join(sql.Identifier(RENAMES.get(field, field)) for field in fields),
                    sql.SQL(", ").join(expression(field) for field in fields),
                    sql.Identifier("raw", table),
                ))
                report[table] = cursor.rowcount
                if report[table] == 0:
                    raise ValueError(f"{table}: raw table is empty")
            cursor.execute(Path(__file__).with_name("analytics_views.sql").read_text(encoding="utf-8"))
            cursor.execute("SELECT count(*) FROM analytics.order_summary")
            if cursor.fetchone()[0] != report["orders"]:
                raise ValueError("Order summary must contain exactly one row per order")
            cursor.execute("""CREATE TABLE IF NOT EXISTS analytics.build_runs (
                build_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                built_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                raw_run_id BIGINT NOT NULL REFERENCES raw.ingestion_runs(run_id),
                row_counts JSONB NOT NULL
            )""")
            cursor.execute("INSERT INTO analytics.build_runs (raw_run_id, row_counts) VALUES (%s, %s)",
                           (source_run, json.dumps(report)))
    return {"raw_run_id": source_run, "staging_rows": report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    connection = None
    try:
        connection = connect()
        report = build(connection)
    except ValueError as error:
        parser.exit(1, f"Analytics build failed: {error}\n")
    except psycopg2.Error:
        parser.exit(1, "Analytics build failed; changes were rolled back. Check source types, keys, value ranges, and database availability.\n")
    finally:
        if connection is not None:
            connection.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
