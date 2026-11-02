-- Small synthetic data exercises actual GoogleSQL without touching raw/staging.
CREATE TEMP TABLE tmp_customers AS
SELECT 'c' AS customer_id, 'unique' AS customer_unique_id, 'city' AS customer_city, 'SP' AS customer_state;
CREATE TEMP TABLE tmp_orders AS
SELECT 'delivered' AS order_id, 'c' AS customer_id, 'delivered' AS order_status,
       DATETIME '2020-01-01 10:00:00' AS order_purchase_timestamp,
       DATETIME '2020-01-03 00:00:00' AS order_estimated_delivery_date,
       DATETIME '2020-01-03 23:59:00' AS order_delivered_customer_date
UNION ALL SELECT 'canceled', 'c', 'canceled', DATETIME '2020-01-01 10:00:00', DATETIME '2020-01-03 00:00:00', NULL
UNION ALL SELECT 'pending', 'c', 'shipped', DATETIME '2020-01-01 10:00:00', DATETIME '2020-01-03 00:00:00', NULL;
CREATE TEMP TABLE tmp_order_items AS
SELECT 'delivered' AS order_id, NUMERIC '10.00' AS price, NUMERIC '2.00' AS freight_value
UNION ALL SELECT 'delivered', NUMERIC '20.00', NUMERIC '3.00'
UNION ALL SELECT 'canceled', NUMERIC '100.00', NUMERIC '0.00';
CREATE TEMP TABLE tmp_order_payments AS
SELECT 'delivered' AS order_id, NUMERIC '7.00' AS payment_value
UNION ALL SELECT 'delivered', NUMERIC '28.00'
UNION ALL SELECT 'canceled', NUMERIC '100.00';
CREATE TEMP TABLE tmp_order_reviews AS
SELECT 'delivered' AS order_id, 1 AS review_score
UNION ALL SELECT 'delivered', 5;

-- The runner inserts bigquery_analytics.sql here.
-- ANALYTICS_MODELS

ASSERT (SELECT COUNT(*) FROM tmp_order_summary) = 3 AS 'one row per order';
ASSERT (SELECT items_value_brl FROM tmp_order_summary WHERE order_id = 'delivered') = NUMERIC '30' AS 'items must not multiply';
ASSERT (SELECT payment_value_brl FROM tmp_order_summary WHERE order_id = 'delivered') = NUMERIC '35' AS 'payments must not multiply';
ASSERT (SELECT mean_review_score FROM tmp_order_summary WHERE order_id = 'delivered') = NUMERIC '3' AS 'multiple reviews must aggregate';
ASSERT (SELECT is_late_delivery FROM tmp_order_summary WHERE order_id = 'delivered') = FALSE AS 'same-day delivery is on time';
ASSERT (SELECT is_late_delivery FROM tmp_order_summary WHERE order_id = 'pending') IS NULL AS 'pending delivery is unlabeled';
ASSERT (SELECT SUM(delivered_order_count) FROM tmp_daily_sales) = 1 AS 'canceled and pending orders excluded';
ASSERT (SELECT SUM(items_gmv_brl) FROM tmp_daily_sales) = NUMERIC '30' AS 'GMV excludes freight';
SELECT 'passed' AS analytics_fixture_checks;
