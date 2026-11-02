"""Print a BigQuery load contract validated against the exact local snapshot."""

import argparse
import json
from pathlib import Path

from ingestion.batch.load_olist import TABLES, validate_file


def prepare(data_dir, manifest):
    sources = {entry["file"]: entry for entry in manifest["files"]}
    expected = {definition[0] for definition in TABLES.values()}
    if len(manifest["files"]) != len(expected) or set(sources) != expected:
        raise ValueError("Source manifest must contain exactly the nine expected Olist files")
    tables = []
    for name, (filename, column_text, _) in TABLES.items():
        columns = column_text.split()
        source = sources[filename]
        validated = validate_file(data_dir / filename, columns)
        if validated["sha256"] != source["sha256"]:
            raise ValueError(f"{filename}: source checksum differs from uploaded snapshot")
        tables.append({
            "table": name, "file": filename, "rows": validated["rows"],
            "sha256": validated["sha256"], "md5": source["md5"], "bytes": source["bytes"],
            "schema": [{"name": column, "type": "STRING", "mode": "NULLABLE"} for column in columns],
        })
    return {"datasetSha256": manifest["datasetSha256"], "tables": tables}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    print(json.dumps(prepare(args.data_dir, manifest), indent=2))


if __name__ == "__main__":
    main()
