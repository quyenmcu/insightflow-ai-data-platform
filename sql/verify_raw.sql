-- PowerShell: Get-Content sql/verify_raw.sql -Raw | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U insightflow -d insightflow
SELECT 'customers' AS table_name, count(*) AS row_count FROM raw.customers
UNION ALL SELECT 'geolocation', count(*) FROM raw.geolocation
UNION ALL SELECT 'order_items', count(*) FROM raw.order_items
UNION ALL SELECT 'order_payments', count(*) FROM raw.order_payments
UNION ALL SELECT 'order_reviews', count(*) FROM raw.order_reviews
UNION ALL SELECT 'orders', count(*) FROM raw.orders
UNION ALL SELECT 'products', count(*) FROM raw.products
UNION ALL SELECT 'sellers', count(*) FROM raw.sellers
UNION ALL SELECT 'product_category_name_translation', count(*) FROM raw.product_category_name_translation
ORDER BY table_name;

SELECT run_id, loaded_at, source FROM raw.ingestion_runs ORDER BY run_id DESC LIMIT 5;

SELECT count(*) AS orders_without_customer
FROM raw.orders o LEFT JOIN raw.customers c USING (customer_id)
WHERE c.customer_id IS NULL;
