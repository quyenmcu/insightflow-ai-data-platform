"""Export the local staging contract for the BigQuery model builder."""

import json

from ingestion.batch.build_analytics import (
    CHECKS, FOREIGN_KEYS, ORDER, RENAMES, REQUIRED, column_type,
)
from ingestion.batch.load_olist import TABLES


def prepare():
    types = {"TEXT": "STRING", "INTEGER": "INT64", "NUMERIC": "NUMERIC", "TIMESTAMP WITHOUT TIME ZONE": "DATETIME"}
    tables = []
    for table in ORDER:
        _, columns, key_text = TABLES[table]
        keys = key_text.split()
        required = set(keys) | REQUIRED.get(table, set())
        tables.append({
            "table": table,
            "fields": [{"source": field, "name": RENAMES.get(field, field), "type": types[column_type(field)], "required": field in required} for field in columns.split()],
            "keys": keys,
            "foreignKeys": FOREIGN_KEYS.get(table, []),
            "checks": sorted(CHECKS.get(table, [])),
        })
    return {"tables": tables}


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
