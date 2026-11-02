-- PowerShell: Get-Content sql/verify_analytics.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U insightflow -d insightflow
SELECT count(*) AS summary_orders,
       count(DISTINCT order_id) AS distinct_orders,
       sum(items_value_brl) AS items_value_brl,
       sum(payment_value_brl) AS payment_value_brl
FROM analytics.order_summary;

-- These differences must all be zero: no loss or multiplication in the joins.
SELECT
    (SELECT count(*) FROM analytics.order_summary) - (SELECT count(*) FROM staging.orders) AS order_count_difference,
    (SELECT sum(items_value_brl) FROM analytics.order_summary) - (SELECT sum(price) FROM staging.order_items) AS items_value_difference,
    (SELECT sum(payment_value_brl) FROM analytics.order_summary) - (SELECT sum(payment_value) FROM staging.order_payments) AS payment_value_difference;

SELECT sum(delivered_order_count) AS delivered_orders,
       sum(items_gmv_brl) AS delivered_items_gmv_brl,
       sum(delivery_label_count) AS labeled_deliveries,
       sum(late_delivery_count) AS late_deliveries
FROM analytics.daily_sales;

SELECT * FROM analytics.daily_sales ORDER BY purchase_date DESC LIMIT 5;

SELECT b.build_id, b.built_at, b.raw_run_id,
       b.raw_run_id = (SELECT max(run_id) FROM raw.ingestion_runs) AS uses_latest_raw_run
FROM analytics.build_runs b ORDER BY b.build_id DESC LIMIT 1;
