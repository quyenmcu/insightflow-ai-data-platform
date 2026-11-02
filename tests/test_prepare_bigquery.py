import csv
import hashlib

import pytest

from ingestion.batch.load_olist import TABLES
from ingestion.batch.prepare_bigquery import prepare


@pytest.fixture
def snapshot(tmp_path):
    manifest = {"datasetSha256": "snapshot", "files": []}
    for filename, columns, _ in TABLES.values():
        path = tmp_path / filename
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns.split())
            writer.writerow(["00123"] * len(columns.split()))
        data = path.read_bytes()
        manifest["files"].append({"file": filename, "sha256": hashlib.sha256(data).hexdigest(), "md5": hashlib.md5(data).hexdigest(), "bytes": len(data)})
    return tmp_path, manifest


def test_contract_preserves_text_columns_and_counts(snapshot):
    path, manifest = snapshot
    contract = prepare(path, manifest)
    assert len(contract["tables"]) == 9
    assert all(table["rows"] == 1 for table in contract["tables"])
    customers = next(table for table in contract["tables"] if table["table"] == "customers")
    assert {"name": "customer_zip_code_prefix", "type": "STRING", "mode": "NULLABLE"} in customers["schema"]


def test_contract_rejects_changed_source(snapshot):
    path, manifest = snapshot
    target = path / "olist_customers_dataset.csv"
    target.write_bytes(target.read_bytes().replace(b"00123", b"00999"))
    with pytest.raises(ValueError, match="checksum"):
        prepare(path, manifest)


def test_contract_rejects_missing_manifest_entry(snapshot):
    path, manifest = snapshot
    manifest["files"].pop()
    with pytest.raises(ValueError, match="nine expected"):
        prepare(path, manifest)
