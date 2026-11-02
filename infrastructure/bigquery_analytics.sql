-- Inputs are transaction-local typed tables, one table per source.
CREATE TEMP TABLE tmp_order_summary AS
WITH items AS (
  SELECT order_id, COUNT(*) AS item_count,
         SUM(price) AS items_value_brl, SUM(freight_value) AS freight_value_brl
  FROM tmp_order_items GROUP BY order_id
), payments AS (
  SELECT order_id, COUNT(*) AS payment_count, SUM(payment_value) AS payment_value_brl
  FROM tmp_order_payments GROUP BY order_id
), reviews AS (
  SELECT order_id, COUNT(*) AS review_count,
         AVG(CAST(review_score AS NUMERIC)) AS mean_review_score
  FROM tmp_order_reviews GROUP BY order_id
)
SELECT o.order_id, o.customer_id, c.customer_unique_id,
       c.customer_city, c.customer_state, o.order_status,
       o.order_purchase_timestamp, o.order_estimated_delivery_date,
       o.order_delivered_customer_date,
       COALESCE(i.item_count, 0) AS item_count,
       COALESCE(i.items_value_brl, 0) AS items_value_brl,
       COALESCE(i.freight_value_brl, 0) AS freight_value_brl,
       COALESCE(p.payment_count, 0) AS payment_count,
       COALESCE(p.payment_value_brl, 0) AS payment_value_brl,
       COALESCE(r.review_count, 0) AS review_count, r.mean_review_score,
       CASE WHEN o.order_status = 'delivered'
                  AND o.order_delivered_customer_date IS NOT NULL
                  AND o.order_estimated_delivery_date IS NOT NULL
            THEN DATE(o.order_delivered_customer_date) > DATE(o.order_estimated_delivery_date)
       END AS is_late_delivery
FROM tmp_orders o
JOIN tmp_customers c USING (customer_id)
LEFT JOIN items i USING (order_id)
LEFT JOIN payments p USING (order_id)
LEFT JOIN reviews r USING (order_id);

CREATE TEMP TABLE tmp_daily_sales AS
SELECT DATE(order_purchase_timestamp) AS purchase_date,
       COUNT(*) AS delivered_order_count,
       COUNT(DISTINCT customer_unique_id) AS unique_customer_count,
       SUM(item_count) AS item_count,
       SUM(items_value_brl) AS items_gmv_brl,
       SUM(freight_value_brl) AS freight_value_brl,
       SUM(payment_value_brl) AS payment_value_brl,
       AVG(items_value_brl) AS average_order_items_value_brl,
       COUNTIF(is_late_delivery IS NOT NULL) AS delivery_label_count,
       COUNTIF(is_late_delivery) AS late_delivery_count
FROM tmp_order_summary
WHERE order_status = 'delivered'
GROUP BY purchase_date;
