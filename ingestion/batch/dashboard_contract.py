"""Dependency-free contract shared by PostgreSQL and BigQuery dashboard exports."""

from decimal import Decimal
import hashlib
import json
import re

FIELDS = ("orders", "delivered", "labeled", "late", "gmv_cents", "freight_cents", "payments_cents")


def cents(value):
    amount = Decimal(value) * 100
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError("Warehouse monetary total has fractional cents or is not finite")
    return int(amount)


def aggregate_digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_snapshot(snapshot, expected=None):
    rows = snapshot["rows"]
    if not rows or len({(r["month"], r["state"]) for r in rows}) != len(rows):
        raise ValueError("Snapshot needs unique nonempty month/state groups")
    for row in rows:
        if set(row) != {"month", "state", *FIELDS}:
            raise ValueError("Only declared aggregate fields may be published")
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", row["month"]) or not re.fullmatch(r"[A-Z]{2}|Unknown", row["state"]):
            raise ValueError("Invalid month or customer state")
        if any(type(row[field]) is not int or not 0 <= row[field] <= 2**53 - 1 for field in FIELDS):
            raise ValueError("Snapshot values must be nonnegative safe integers")
        if not row["late"] <= row["labeled"] <= row["delivered"] <= row["orders"]:
            raise ValueError("Invalid delivery denominators")
    totals = {field: sum(row[field] for row in rows) for field in FIELDS}
    if totals != snapshot["totals"] or any(value > 2**53 - 1 for value in totals.values()):
        raise ValueError("Aggregate rows differ from warehouse totals or exceed safe integers")
    if expected is not None:
        checks = {"orders": int(expected["order_count"]), "delivered": int(expected["delivered_order_count"]),
                  "labeled": int(expected["labeled_deliveries"]), "late": int(expected["late_deliveries"]),
                  "gmv_cents": cents(expected["delivered_items_gmv_brl"])}
        if any(totals[key] != value for key, value in checks.items()):
            raise ValueError("Dashboard snapshot differs from registered PostgreSQL/BigQuery baseline")
    return totals
