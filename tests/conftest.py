"""Database fixtures isolate integration checks from the project database."""

import uuid

import pytest
from psycopg2 import sql

from ingestion.batch.load_olist import connect


@pytest.fixture
def database(monkeypatch):
    admin = connect()
    admin.autocommit = True
    name = "insightflow_test_" + uuid.uuid4().hex
    with admin.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    monkeypatch.setenv("POSTGRES_DB", name)
    connection = connect()
    try:
        yield connection
    finally:
        connection.close()
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
        admin.close()
