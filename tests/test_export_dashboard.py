from copy import deepcopy
from decimal import Decimal

import pytest

from ingestion.batch.export_dashboard import cents, validate_snapshot, export_snapshot
from ingestion.batch.build_analytics import build
from ingestion.batch.load_olist import TABLES, load
from test_build_analytics import analytics_source


def snapshot():
    row = {"month": "2018-01", "state": "SP", "orders": 5, "delivered": 4,
           "labeled": 3, "late": 1, "gmv_cents": 10000, "freight_cents": 500, "payments_cents": 11000}
    return {"rows": [row], "totals": {k: v for k, v in row.items() if k not in ("month", "state")}}


def test_snapshot_reconciles_counts_and_reference():
    data = snapshot()
    expected = dict(order_count=5, delivered_order_count=4, labeled_deliveries=3, late_deliveries=1, delivered_items_gmv_brl="100.00")
    assert validate_snapshot(data, expected)["gmv_cents"] == 10000
    with pytest.raises(ValueError, match="baseline"):
        validate_snapshot(data, {**expected, "order_count": 6})


def test_bad_denominators_duplicate_groups_and_mismatched_totals_fail():
    data = snapshot()
    invalid = deepcopy(data)
    invalid["rows"][0]["late"] = 4
    with pytest.raises(ValueError, match="denominators"):
        validate_snapshot(invalid)
    with pytest.raises(ValueError, match="unique"):
        validate_snapshot({**data, "rows": data["rows"] * 2})
    with pytest.raises(ValueError, match="totals"):
        validate_snapshot({**data, "totals": {}})


def test_money_conversion_preserves_exact_cents():
    assert cents(Decimal("13221498.11")) == 1322149811
    with pytest.raises(ValueError, match="fractional cents"):
        cents(Decimal("1.001"))


def test_export_reconciles_real_views_and_rejects_stale_build(database, analytics_source):
    loaded = load(analytics_source, database)
    build(database)
    manifest = {"datasetSha256": "0" * 64, "files": [dict(file=TABLES[table][0], **record) for table, record in loaded.items()]}
    exported = export_snapshot(database, manifest)
    assert exported["totals"] == dict(orders=3, delivered=1, labeled=1, late=0, gmv_cents=3000, freight_cents=500, payments_cents=3500)
    assert len(exported["rows"]) == 1
    assert exported["rows"][0]["state"] == "SP"
    assert "order_id" not in str(exported)
    bad_manifest = deepcopy(manifest)
    bad_manifest["files"][0]["sha256"] = "bad"
    with pytest.raises(ValueError, match="source"):
        export_snapshot(database, bad_manifest)
    database.set_session(readonly=False)
    load(analytics_source, database)
    with pytest.raises(ValueError, match="behind"):
        export_snapshot(database, manifest)
