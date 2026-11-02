"""Integration checks run against an isolated, disposable PostgreSQL database."""

import csv

import pytest
from psycopg2 import sql

from ingestion.batch.load_olist import TABLES, load, validate_file


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(columns)
        writer.writerows(rows)


@pytest.fixture
def source(tmp_path):
    for filename, columns, _ in TABLES.values():
        fields = columns.split()
        write_csv(tmp_path / filename, fields, [["value" for _ in fields]])
    fields = TABLES["customers"][1].split()
    write_csv(tmp_path / TABLES["customers"][0], fields, [["c1", "u1", "00123", 'São Paulo, "Centro"\nCity', "SP"]])
    # The actual Kaggle translation file includes a UTF-8 byte-order mark.
    translation = tmp_path / TABLES["product_category_name_translation"][0]
    translation.write_bytes(b"\xef\xbb\xbf" + translation.read_bytes())
    return tmp_path


def test_repeat_load_preserves_source_and_counts(database, source):
    first = load(source, database)
    assert load(source, database) == first
    with database.cursor() as cursor:
        cursor.execute("SELECT customer_zip_code_prefix, customer_city FROM raw.customers")
        assert cursor.fetchall() == [("00123", 'São Paulo, "Centro"\nCity')]
        cursor.execute("SELECT count(*) FROM raw.ingestion_runs")
        assert cursor.fetchone()[0] == 2
        for table in TABLES:
            cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("raw", table)))
            assert cursor.fetchone()[0] == 1


def test_late_duplicate_rolls_back_entire_refresh(database, source):
    load(source, database)
    filename, columns, _ = TABLES["customers"]
    write_csv(source / filename, columns.split(), [["changed"] * len(columns.split())])
    filename, columns, _ = TABLES["sellers"]
    row = ["duplicate"] * len(columns.split())
    write_csv(source / filename, columns.split(), [row, row])
    with pytest.raises(ValueError, match="duplicate key"):
        load(source, database)
    with database.cursor() as cursor:
        cursor.execute("SELECT customer_id FROM raw.customers")
        assert cursor.fetchall() == [("c1",)]
        cursor.execute("SELECT count(*) FROM raw.ingestion_runs")
        assert cursor.fetchone()[0] == 1


def test_bad_header_leaves_database_unchanged(database, source):
    load(source, database)
    filename = TABLES["orders"][0]
    write_csv(source / filename, ["wrong_header"], [["wrong_value"]])
    with pytest.raises(ValueError, match="header"):
        load(source, database)
    with database.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM raw.orders")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT count(*) FROM raw.ingestion_runs")
        assert cursor.fetchone()[0] == 1


def test_reject_empty_and_ragged_files(tmp_path):
    path = tmp_path / "invalid.csv"
    write_csv(path, ["a", "b"], [])
    with pytest.raises(ValueError, match="no data"):
        validate_file(path, ["a", "b"])
    write_csv(path, ["a", "b"], [["one"]])
    with pytest.raises(ValueError, match="fields"):
        validate_file(path, ["a", "b"])
