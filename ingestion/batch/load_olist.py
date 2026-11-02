"""Validate and atomically refresh Olist's nine raw PostgreSQL tables."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv


# Raw columns intentionally use text, including Olist's original spelling.
# Types and business transformations belong in the next modeling layer.
TABLES = {
    "customers": ("olist_customers_dataset.csv", "customer_id customer_unique_id customer_zip_code_prefix customer_city customer_state", "customer_id"),
    "geolocation": ("olist_geolocation_dataset.csv", "geolocation_zip_code_prefix geolocation_lat geolocation_lng geolocation_city geolocation_state", ""),
    "order_items": ("olist_order_items_dataset.csv", "order_id order_item_id product_id seller_id shipping_limit_date price freight_value", "order_id order_item_id"),
    "order_payments": ("olist_order_payments_dataset.csv", "order_id payment_sequential payment_type payment_installments payment_value", "order_id payment_sequential"),
    "order_reviews": ("olist_order_reviews_dataset.csv", "review_id order_id review_score review_comment_title review_comment_message review_creation_date review_answer_timestamp", ""),
    "orders": ("olist_orders_dataset.csv", "order_id customer_id order_status order_purchase_timestamp order_approved_at order_delivered_carrier_date order_delivered_customer_date order_estimated_delivery_date", "order_id"),
    "products": ("olist_products_dataset.csv", "product_id product_category_name product_name_lenght product_description_lenght product_photos_qty product_weight_g product_length_cm product_height_cm product_width_cm", "product_id"),
    "sellers": ("olist_sellers_dataset.csv", "seller_id seller_zip_code_prefix seller_city seller_state", "seller_id"),
    "product_category_name_translation": ("product_category_name_translation.csv", "product_category_name product_category_name_english", "product_category_name"),
}


def validate_file(path, columns):
    """Return record count and digest; reject changed headers and malformed rows."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source, strict=True)
        if next(reader, None) != columns:
            raise ValueError(f"{path.name}: header does not match the expected schema")
        count = 0
        for count, row in enumerate(reader, start=1):
            if len(row) != len(columns):
                raise ValueError(f"{path.name}: record {count} has {len(row)} fields; expected {len(columns)}")
        if count == 0:
            raise ValueError(f"{path.name}: file contains no data records")
    return {"rows": count, "sha256": digest.hexdigest()}


def connect():
    load_dotenv()
    for name in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        if not os.environ.get(name):
            raise ValueError(f"Missing required environment variable: {name}")
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=os.getenv("POSTGRES_PORT", "5433"),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=10,
        application_name="insightflow_olist_ingestion",
    )


def load(data_dir, connection):
    # Preflight all files before changing the database.
    report = {
        table: validate_file(data_dir / filename, columns.split())
        for table, (filename, columns, _) in TABLES.items()
    }
    with connection:
        with connection.cursor() as cursor:
            # Serialize runs so concurrent refreshes cannot interleave.
            cursor.execute("SELECT pg_advisory_xact_lock(470011)")
            cursor.execute("CREATE SCHEMA IF NOT EXISTS raw")
            for table, (filename, columns, keys) in TABLES.items():
                target = sql.Identifier("raw", table)
                fields = columns.split()
                definitions = sql.SQL(", ").join(
                    sql.SQL("{} TEXT").format(sql.Identifier(field)) for field in fields
                )
                cursor.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(target, definitions))
                cursor.execute(sql.SQL("TRUNCATE TABLE {}").format(target))
                # COPY handles embedded commas, quotes, and multiline review text.
                with (data_dir / filename).open(encoding="utf-8-sig", newline="") as source:
                    cursor.copy_expert(
                        sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')").format(
                            target, sql.SQL(", ").join(map(sql.Identifier, fields))
                        ).as_string(connection), source
                    )
                cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(target))
                if cursor.fetchone()[0] != report[table]["rows"]:
                    raise ValueError(f"{table}: loaded row count does not match the source")
                # Reviews and geolocation intentionally retain source duplicates.
                if keys:
                    key_fields = keys.split()
                    missing = sql.SQL(" OR ").join(
                        sql.SQL("{} IS NULL OR {} = ''").format(sql.Identifier(key), sql.Identifier(key))
                        for key in key_fields
                    )
                    cursor.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {} WHERE {})").format(target, missing))
                    if cursor.fetchone()[0]:
                        raise ValueError(f"{table}: missing key values")
                    cursor.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {} GROUP BY {} HAVING COUNT(*) > 1)").format(
                        target, sql.SQL(", ").join(map(sql.Identifier, key_fields))
                    ))
                    if cursor.fetchone()[0]:
                        raise ValueError(f"{table}: duplicate key values")
                # Catch modifications to a CSV between preflight and COPY.
                if validate_file(data_dir / filename, fields) != report[table]:
                    raise ValueError(f"{filename}: source changed during ingestion")
            cursor.execute("""CREATE TABLE IF NOT EXISTS raw.ingestion_runs (
                run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source TEXT NOT NULL,
                manifest JSONB NOT NULL
            )""")
            cursor.execute(
                "INSERT INTO raw.ingestion_runs (source, manifest) VALUES (%s, %s)",
                ("https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce", json.dumps(report)),
            )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw/olist"))
    args = parser.parse_args()
    connection = None
    try:
        connection = connect()
        report = load(args.data_dir, connection)
    except (ValueError, OSError, csv.Error) as error:
        parser.exit(1, f"Ingestion failed: {error}\n")
    except psycopg2.Error:
        # Database error details can contain source records or connection secrets.
        parser.exit(1, "Database operation failed; the load was rolled back. Check database availability, credentials, and raw table schema.\n")
    finally:
        if connection is not None:
            connection.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
