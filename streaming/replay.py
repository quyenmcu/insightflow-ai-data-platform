"""Construct deterministic purchase events; no final delivery outcomes are used."""

import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from .store import event_id, validate


def rows(directory, filename):
    with (directory / filename).open(encoding='utf-8-sig', newline='') as source:
        yield from csv.DictReader(source, strict=True)


def events(directory):
    customers = {}
    for row in rows(directory, 'olist_customers_dataset.csv'):
        customer = row['customer_id']
        if not customer or customer in customers:
            raise ValueError('Missing or duplicate customer ID')
        customers[customer] = row['customer_state']
    values, item_ids = defaultdict(int), set()
    for row in rows(directory, 'olist_order_items_dataset.csv'):
        item = (row['order_id'], row['order_item_id'])
        if not all(item) or item in item_ids:
            raise ValueError('Missing or duplicate order item ID')
        item_ids.add(item)
        try:
            price = Decimal(row['price']) * 100
            if not price.is_finite() or price < 0 or price != price.to_integral_value():
                raise ValueError('Item price must be nonnegative BRL cents')
            values[row['order_id']] += int(price)
        except InvalidOperation as error:
            raise ValueError('Invalid item price') from error
    purchases, order_ids = [], set()
    for row in rows(directory, 'olist_orders_dataset.csv'):
        order = row['order_id']
        if not order or order in order_ids:
            raise ValueError('Missing or duplicate order ID')
        order_ids.add(order)
        purchases.append(validate({
            'version': 1, 'event_id': event_id(order), 'kind': 'historical_order_purchase',
            'event_time': row['order_purchase_timestamp'], 'state': customers[row['customer_id']],
            'item_value_cents': values[order], 'simulated': True,
        }))
    if not purchases or set(values) - order_ids:
        raise ValueError('Empty orders or orphan order items')
    return sorted(purchases, key=lambda event: (event['event_time'], event['event_id']))
