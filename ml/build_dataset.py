"""Build a checkout-time delivery-delay dataset with chronological splits."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

import pandas as pd

from ingestion.batch.load_olist import TABLES, validate_file


NUMERIC_FEATURES = [
    "purchase_month", "purchase_weekday", "purchase_hour", "item_count",
    "unique_product_count", "seller_count", "seller_state_count", "category_count",
    "items_value_brl", "freight_value_brl", "freight_share", "total_weight_g",
    "mean_volume_cm3", "longest_side_cm", "weight_missing_fraction",
    "dimensions_missing_fraction", "interstate_item_fraction", "state_missing_fraction",
]
CATEGORICAL_FEATURES = ["customer_state", "primary_seller_state", "primary_product_category"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
SPLIT_DATES = {"train_end": "2018-01-01", "validation_end": "2018-05-01", "test_end": "2018-09-01", "observation_end": "2018-11-01"}
INPUT_COLUMNS = {
    "orders": ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_delivered_customer_date", "order_estimated_delivery_date"],
    "customers": ["customer_id", "customer_state"],
    "order_items": ["order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value"],
    "products": ["product_id", "product_category_name", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
    "sellers": ["seller_id", "seller_state"],
}


def timestamps(values):
    return pd.to_datetime(values, format="%Y-%m-%d %H:%M:%S", errors="raise")


def require_key(frame, keys, name):
    if frame[keys].isna().any().any() or frame[keys].eq("").any().any() or frame.duplicated(keys).any():
        raise ValueError(f"{name}: missing or duplicate keys")


def dominant_by_order(items, column):
    counts = items.dropna(subset=[column]).groupby(["order_id", column], sort=False).size().rename("count").reset_index()
    ranked = counts.sort_values(["order_id", "count", column], ascending=[True, False, True], kind="stable")
    return ranked.drop_duplicates("order_id").set_index("order_id")[column]


def build_features(orders, customers, order_items, products, sellers):
    # Explicit projections separate predictor construction from outcome data.
    base = orders[["order_id", "customer_id", "order_purchase_timestamp"]].copy()
    customers = customers[INPUT_COLUMNS["customers"]].copy()
    items = order_items[INPUT_COLUMNS["order_items"]].copy()
    products = products[INPUT_COLUMNS["products"]].copy()
    sellers = sellers[INPUT_COLUMNS["sellers"]].copy()
    for frame, keys, name in [
        (base, ["order_id"], "orders"), (customers, ["customer_id"], "customers"),
        (items, ["order_id", "order_item_id"], "items"), (products, ["product_id"], "products"),
        (sellers, ["seller_id"], "sellers"),
    ]:
        require_key(frame, keys, name)
    base = base.merge(customers, on="customer_id", how="left", validate="many_to_one", indicator=True)
    if base["_merge"].ne("both").any():
        raise ValueError("Order has no customer")
    base = base.drop(columns="_merge")
    base["prediction_at"] = timestamps(base["order_purchase_timestamp"])
    if base["prediction_at"].isna().any():
        raise ValueError("Order purchase timestamp is required")
    for frame, state in ((base, "customer_state"), (sellers, "seller_state")):
        frame[state] = frame[state].astype("string").str.strip().str.upper().replace("", pd.NA)
    products["product_category_name"] = products["product_category_name"].astype("string").str.strip().str.lower().replace("", pd.NA)
    measurements = ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"]
    for field in measurements:
        products[field] = pd.to_numeric(products[field], errors="raise").astype("Float64")
        if products[field].lt(0).any():
            raise ValueError(f"Negative product measurement: {field}")
        products[field] = products[field].mask(products[field].eq(0))
    for field in ("price", "freight_value"):
        items[field] = pd.to_numeric(items[field], errors="raise").astype("Float64")
        if items[field].isna().any() or items[field].lt(0).any():
            raise ValueError(f"Invalid cart amount: {field}")
    for parent, key, description in ((products, "product_id", "product"), (sellers, "seller_id", "seller"), (base[["order_id", "customer_state"]], "order_id", "order")):
        items = items.merge(parent, on=key, how="left", validate="many_to_one", indicator=True)
        if items["_merge"].ne("both").any():
            raise ValueError(f"Item has no {description}")
        items = items.drop(columns="_merge")
    dimensions = ["product_length_cm", "product_height_cm", "product_width_cm"]
    items["volume_cm3"] = items[dimensions].prod(axis=1, min_count=3)
    items["longest_side"] = items[dimensions].max(axis=1).mask(items[dimensions].isna().any(axis=1))
    items["weight_missing"] = items["product_weight_g"].isna().astype(float)
    items["dimensions_missing"] = items[dimensions].isna().any(axis=1).astype(float)
    items["state_missing"] = (items["seller_state"].isna() | items["customer_state"].isna()).astype(float)
    items["interstate"] = items["seller_state"].ne(items["customer_state"]).astype("Float64").mask(items["state_missing"].eq(1))
    grouped = items.groupby("order_id", sort=True)
    aggregated = grouped.agg(
        item_count=("order_item_id", "size"), unique_product_count=("product_id", "nunique"),
        seller_count=("seller_id", "nunique"), seller_state_count=("seller_state", "nunique"),
        category_count=("product_category_name", "nunique"), items_value_brl=("price", "sum"),
        freight_value_brl=("freight_value", "sum"),
        mean_volume_cm3=("volume_cm3", "mean"), longest_side_cm=("longest_side", "max"),
        weight_missing_fraction=("weight_missing", "mean"), dimensions_missing_fraction=("dimensions_missing", "mean"),
        interstate_item_fraction=("interstate", "mean"), state_missing_fraction=("state_missing", "mean"),
    )
    aggregated["total_weight_g"] = grouped["product_weight_g"].sum(min_count=1)
    aggregated["primary_seller_state"] = dominant_by_order(items, "seller_state")
    aggregated["primary_product_category"] = dominant_by_order(items, "product_category_name")
    aggregated = aggregated.reset_index()
    result = base.merge(aggregated, on="order_id", how="left", validate="one_to_one")
    for field in ("item_count", "unique_product_count", "seller_count", "seller_state_count", "category_count"):
        result[field] = result[field].fillna(0).astype("int64")
    total = result["items_value_brl"] + result["freight_value_brl"]
    result["freight_share"] = result["freight_value_brl"] / total.mask(total.eq(0))
    result.loc[total.eq(0), "freight_share"] = 0.0
    for field in ("items_value_brl", "freight_value_brl"):
        result[field] = result[field].round(2)
    result["purchase_month"] = result["prediction_at"].dt.month
    result["purchase_weekday"] = result["prediction_at"].dt.weekday
    result["purchase_hour"] = result["prediction_at"].dt.hour
    return result[["order_id", "prediction_at"] + FEATURES].sort_values(["prediction_at", "order_id"]).reset_index(drop=True)


def labels(orders):
    frame = orders[["order_id", "order_status", "order_purchase_timestamp", "order_delivered_customer_date", "order_estimated_delivery_date"]].copy()
    purchase = timestamps(frame["order_purchase_timestamp"])
    delivered = timestamps(frame["order_delivered_customer_date"])
    estimated = timestamps(frame["order_estimated_delivery_date"]).dt.normalize()
    reason = pd.Series("eligible", index=frame.index, dtype="string")
    reason.loc[frame["order_status"].ne("delivered")] = "not_delivered_cohort"
    reason.loc[reason.eq("eligible") & (delivered.isna() | estimated.isna())] = "missing_outcome_dates"
    reason.loc[reason.eq("eligible") & (delivered.lt(purchase) | estimated.lt(purchase.dt.normalize()))] = "invalid_outcome_timeline"
    late = delivered.dt.normalize().gt(estimated)
    available = delivered.where(~late, estimated + pd.Timedelta(days=1))
    output = pd.DataFrame({"order_id": frame["order_id"], "late_delivery": late.astype("int64"), "label_available_at": available, "eligibility": reason})
    return output


def assign_splits(frame, dates=None):
    dates = dates or SPLIT_DATES
    train_end, validation_end, test_end, observation_end = [pd.Timestamp(dates[key]) for key in SPLIT_DATES]
    if not train_end < validation_end < test_end < observation_end:
        raise ValueError("Chronological boundaries must be strictly increasing")
    result = frame.copy()
    result["split"] = "excluded"
    result["exclusion_reason"] = result["eligibility"].where(result["eligibility"].ne("eligible"), "outside_purchase_window")
    eligible = result["eligibility"].eq("eligible") & result["item_count"].gt(0)
    result.loc[result["eligibility"].eq("eligible") & result["item_count"].eq(0), "exclusion_reason"] = "no_cart_items"
    ranges = [("train", None, train_end, train_end), ("validation", train_end, validation_end, validation_end), ("test", validation_end, test_end, observation_end)]
    for name, start, end, label_cutoff in ranges:
        candidate = eligible & result["prediction_at"].lt(end)
        if start is not None:
            candidate &= result["prediction_at"].ge(start)
        known = result["label_available_at"].lt(label_cutoff)
        result.loc[candidate & known, "split"] = name
        result.loc[candidate & known, "exclusion_reason"] = pd.NA
        result.loc[candidate & ~known, "exclusion_reason"] = "label_unavailable_at_cutoff"
    return result


def load_sources(data_dir, manifest):
    records = {entry["file"]: entry for entry in manifest["files"]}
    inputs, provenance = {}, {}
    for table, columns in INPUT_COLUMNS.items():
        filename, all_columns, _ = TABLES[table]
        checked = validate_file(data_dir / filename, all_columns.split())
        if checked["sha256"] != records[filename]["sha256"]:
            raise ValueError(f"{filename}: checksum differs from the recorded source snapshot")
        inputs[table] = pd.read_csv(data_dir / filename, usecols=columns, dtype="string", keep_default_na=False, na_values=[""], encoding="utf-8-sig")
        provenance[table] = checked
    return inputs, provenance


def build(data_dir, output_dir, manifest_path):
    print("Validating the five source files against the snapshot...", file=sys.stderr, flush=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    inputs, provenance = load_sources(data_dir, manifest)
    print("Building checkout features and chronological splits...", file=sys.stderr, flush=True)
    features = build_features(**inputs)
    dataset = assign_splits(features.merge(labels(inputs["orders"]), on="order_id", validate="one_to_one"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    generation = output_dir / run_id
    generation.mkdir(parents=True, exist_ok=False)
    print(f"Writing dataset generation {run_id}...", file=sys.stderr, flush=True)
    features.to_csv(generation / "features.csv", index=False)
    dataset.loc[dataset["split"].eq("excluded"), ["order_id", "prediction_at", "exclusion_reason"]].to_csv(generation / "excluded.csv", index=False)
    split_report = {}
    for name in ("train", "validation", "test"):
        part = dataset.loc[dataset["split"].eq(name), ["order_id", "prediction_at"] + FEATURES + ["late_delivery", "label_available_at"]]
        if part.empty or part["late_delivery"].nunique() != 2:
            raise ValueError(f"{name}: expected nonempty split containing both classes")
        part.to_csv(generation / f"{name}.csv", index=False)
        split_report[name] = {
            "rows": len(part), "late_orders": int(part["late_delivery"].sum()), "late_rate": float(part["late_delivery"].mean()),
            "prediction_min": part["prediction_at"].min().isoformat(), "prediction_max": part["prediction_at"].max().isoformat(),
            "label_available_max": part["label_available_at"].max().isoformat(),
            "missing_features": {field: int(part[field].isna().sum()) for field in FEATURES},
        }
    report = {
        "dataset_version": 1, "run_id": run_id, "source_fingerprint": manifest["datasetSha256"], "source_files": provenance,
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "prediction_point": "order purchase / checkout",
        "numeric_features": NUMERIC_FEATURES, "categorical_features": CATEGORICAL_FEATURES,
        "metadata_not_model_inputs": ["order_id", "prediction_at", "label_available_at"], "target": "late_delivery",
        "split_boundaries": SPLIT_DATES, "total_orders": len(features), "splits": split_report,
        "excluded": {str(reason): int(count) for reason, count in dataset.loc[dataset["split"].eq("excluded"), "exclusion_reason"].value_counts().items()},
    }
    (generation / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pointer = output_dir / f".LATEST-{run_id}.json"
    pointer.write_text(json.dumps({"run_id": run_id, "manifest": f"{run_id}/manifest.json"}) + "\n", encoding="utf-8")
    pointer.replace(output_dir / "LATEST.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/delivery_delay"))
    parser.add_argument("--source-manifest", type=Path, default=Path("infrastructure/source_manifest.json"))
    args = parser.parse_args()
    data_dir = args.data_dir or (Path("data/raw/olist") if Path("data/raw/olist").is_dir() else Path("data/raw"))
    print(json.dumps(build(data_dir, args.output_dir, args.source_manifest), indent=2))


if __name__ == "__main__":
    main()
