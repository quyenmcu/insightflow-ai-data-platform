"""Exercise types, join grain, business definitions, and refresh rollback."""

import csv
from decimal import Decimal

import psycopg2
import pytest

from ingestion.batch.build_analytics import build, column_type
from ingestion.batch.load_olist import TABLES, load


@pytest.fixture
def analytics_source(tmp_path):
    def row(table, **overrides):
        values = {}
        for field in TABLES[table][1].split():
            datatype = column_type(field)
            values[field] = "2020-01-01 10:00:00" if datatype.startswith("TIMESTAMP") else "1" if datatype in {"INTEGER", "NUMERIC"} else "id"
        values.update(overrides)
        return [values[field] for field in TABLES[table][1].split()]

    rows = {table: [row(table)] for table in TABLES}
    rows["customers"] = [row("customers", customer_zip_code_prefix="00123", customer_city=" São Paulo ", customer_state=" sp ")]
    rows["orders"] = [
        row("orders", order_status=" Delivered ", order_estimated_delivery_date="2020-01-03 00:00:00", order_delivered_customer_date="2020-01-03 23:59:00"),
        row("orders", order_id="canceled", order_status="canceled"),
        row("orders", order_id="pending", order_status="shipped", order_delivered_customer_date=""),
    ]
    rows["order_items"] = [
        row("order_items", price="10.00", freight_value="2.00"),
        row("order_items", order_item_id="2", price="20.00", freight_value="3.00"),
        row("order_items", order_id="canceled", price="100.00", freight_value="0.00"),
    ]
    rows["order_payments"] = [
        row("order_payments", payment_value="7.00"),
        row("order_payments", payment_sequential="2", payment_value="28.00"),
        row("order_payments", order_id="canceled", payment_value="100.00"),
    ]
    rows["order_reviews"] = [row("order_reviews", review_score="1"), row("order_reviews", review_score="5")]
    for table, (filename, fields, _) in TABLES.items():
        with (tmp_path / filename).open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(fields.split())
            writer.writerows(rows[table])
    return tmp_path


def test_types_and_aggregates_do_not_multiply(database, analytics_source):
    load(analytics_source, database)
    first = build(database)
    assert build(database) == first
    with database.cursor() as cursor:
        cursor.execute("SELECT customer_zip_code_prefix, customer_city, customer_state FROM staging.customers")
        assert cursor.fetchone() == ("00123", "são paulo", "SP")
        cursor.execute("SELECT item_count, items_value_brl, freight_value_brl, payment_count, payment_value_brl, review_count, mean_review_score, is_late_delivery FROM analytics.order_summary WHERE order_id = 'id'")
        assert cursor.fetchone() == (2, Decimal("30"), Decimal("5"), 2, Decimal("35"), 2, Decimal("3"), False)
        cursor.execute("SELECT delivered_order_count, items_gmv_brl, payment_value_brl, late_delivery_count FROM analytics.daily_sales")
        assert cursor.fetchall() == [(1, Decimal("30"), Decimal("35"), 0)]
        cursor.execute("SELECT is_late_delivery FROM analytics.order_summary WHERE order_id = 'pending'")
        assert cursor.fetchone() == (None,)
        cursor.execute("SELECT pg_typeof(order_purchase_timestamp)::text FROM staging.orders LIMIT 1")
        assert cursor.fetchone()[0] == "timestamp without time zone"
        cursor.execute("SELECT product_name_length FROM staging.products")
        assert cursor.fetchone() == (1,)
        cursor.execute("SELECT count(*) FROM analytics.build_runs")
        assert cursor.fetchone()[0] == 2


@pytest.mark.parametrize("bad_update", [
    "UPDATE raw.products SET product_weight_g = 'invalid'",
    "UPDATE raw.order_items SET seller_id = 'missing'",
    "UPDATE raw.order_reviews SET review_score = '6'",
    "UPDATE raw.order_items SET price = '-1'",
])
def test_invalid_source_rolls_back_build(database, analytics_source, bad_update):
    load(analytics_source, database)
    build(database)
    with database:
        with database.cursor() as cursor:
            cursor.execute("UPDATE raw.customers SET customer_city = 'Changed'")
            cursor.execute(bad_update)
    with pytest.raises(psycopg2.Error):
        build(database)
    with database.cursor() as cursor:
        cursor.execute("SELECT customer_city FROM staging.customers")
        assert cursor.fetchone() == ("são paulo",)
        cursor.execute("SELECT count(*) FROM analytics.build_runs")
        assert cursor.fetchone()[0] == 1
