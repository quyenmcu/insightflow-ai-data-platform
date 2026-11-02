-- Aggregate each one-to-many relationship BEFORE joining to the order grain.
CREATE OR REPLACE VIEW analytics.order_summary AS
WITH items AS (
    SELECT order_id, count(*) AS item_count,
           sum(price) AS items_value_brl, sum(freight_value) AS freight_value_brl
    FROM staging.order_items GROUP BY order_id
), payments AS (
    SELECT order_id, count(*) AS payment_count, sum(payment_value) AS payment_value_brl
    FROM staging.order_payments GROUP BY order_id
), reviews AS (
    SELECT order_id, count(*) AS review_count, avg(review_score) AS mean_review_score
    FROM staging.order_reviews GROUP BY order_id
)
SELECT o.order_id, o.customer_id, c.customer_unique_id,
       c.customer_city, c.customer_state, o.order_status,
       o.order_purchase_timestamp, o.order_estimated_delivery_date,
       o.order_delivered_customer_date,
       coalesce(i.item_count, 0) AS item_count,
       coalesce(i.items_value_brl, 0) AS items_value_brl,
       coalesce(i.freight_value_brl, 0) AS freight_value_brl,
       coalesce(p.payment_count, 0) AS payment_count,
       coalesce(p.payment_value_brl, 0) AS payment_value_brl,
       coalesce(r.review_count, 0) AS review_count, r.mean_review_score,
       CASE WHEN o.order_status = 'delivered'
                 AND o.order_delivered_customer_date IS NOT NULL
                 AND o.order_estimated_delivery_date IS NOT NULL
            THEN o.order_delivered_customer_date::date > o.order_estimated_delivery_date::date
       END AS is_late_delivery
FROM staging.orders o
JOIN staging.customers c USING (customer_id)
LEFT JOIN items i USING (order_id)
LEFT JOIN payments p USING (order_id)
LEFT JOIN reviews r USING (order_id);

-- Delivered orders grouped by PURCHASE date, not by delivery or payment date.
-- GMV excludes freight; payment totals are separate and need not equal GMV.
CREATE OR REPLACE VIEW analytics.daily_sales AS
SELECT order_purchase_timestamp::date AS purchase_date,
       count(*) AS delivered_order_count,
       count(DISTINCT customer_unique_id) AS unique_customer_count,
       sum(item_count) AS item_count,
       sum(items_value_brl) AS items_gmv_brl,
       sum(freight_value_brl) AS freight_value_brl,
       sum(payment_value_brl) AS payment_value_brl,
       avg(items_value_brl) AS average_order_items_value_brl,
       count(*) FILTER (WHERE is_late_delivery IS NOT NULL) AS delivery_label_count,
       count(*) FILTER (WHERE is_late_delivery) AS late_delivery_count
FROM analytics.order_summary
WHERE order_status = 'delivered'
GROUP BY order_purchase_timestamp::date;
