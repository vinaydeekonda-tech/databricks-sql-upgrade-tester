-- Sample query. Replace this folder with your own SQL Git checkout.
SELECT
    customer_id,
    row_number() OVER (PARTITION BY customer_id ORDER BY order_ts DESC) AS rn,
    from_json(payload, 'sku STRING, qty INT') AS item
FROM orders
QUALIFY rn = 1
