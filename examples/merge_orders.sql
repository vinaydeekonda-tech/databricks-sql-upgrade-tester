MERGE INTO main.default.orders AS target
USING main.default.orders_staging AS source
ON target.order_id = source.order_id
WHEN MATCHED THEN UPDATE SET target.qty = source.qty
WHEN NOT MATCHED THEN INSERT (order_id, qty) VALUES (source.order_id, source.qty)
