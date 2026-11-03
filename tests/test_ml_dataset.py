import pandas as pd
import pytest

from ml.build_dataset import assign_splits, build_features, labels


@pytest.fixture
def cart():
    orders = pd.DataFrame([{
        "order_id": "o1", "customer_id": "c1", "order_purchase_timestamp": "2017-12-01 09:00:00",
        "order_status": "delivered", "order_delivered_customer_date": "2017-12-10 12:00:00",
        "order_estimated_delivery_date": "2017-12-09 00:00:00",
    }], dtype="string")
    customers = pd.DataFrame([{"customer_id": "c1", "customer_state": "SP"}], dtype="string")
    items = pd.DataFrame([
        {"order_id": "o1", "order_item_id": "1", "product_id": "p1", "seller_id": "s1", "price": "10", "freight_value": "2"},
        {"order_id": "o1", "order_item_id": "2", "product_id": "p2", "seller_id": "s2", "price": "20", "freight_value": "3"},
    ], dtype="string")
    products = pd.DataFrame([
        {"product_id": "p1", "product_category_name": "books", "product_weight_g": "10", "product_length_cm": "2", "product_height_cm": "3", "product_width_cm": "4"},
        {"product_id": "p2", "product_category_name": "toys", "product_weight_g": pd.NA, "product_length_cm": "2", "product_height_cm": pd.NA, "product_width_cm": "4"},
    ], dtype="string")
    sellers = pd.DataFrame([{"seller_id": "s1", "seller_state": "SP"}, {"seller_id": "s2", "seller_state": "RJ"}], dtype="string")
    return {"orders": orders, "customers": customers, "order_items": items, "products": products, "sellers": sellers}


def test_future_outcomes_cannot_change_features(cart):
    original = build_features(**cart)
    cart["orders"]["order_status"] = "canceled"
    cart["orders"]["order_delivered_customer_date"] = "2099-01-01 00:00:00"
    cart["orders"]["order_estimated_delivery_date"] = "2099-01-02 00:00:00"
    cart["orders"]["order_approved_at"] = "2099-01-03 00:00:00"
    cart["orders"]["review_score"] = "1"
    cart["order_items"]["shipping_limit_date"] = "2099-01-04 00:00:00"
    pd.testing.assert_frame_equal(original, build_features(**cart))


def test_cart_grain_and_missing_catalog_attributes(cart):
    row = build_features(**cart).iloc[0]
    assert row["item_count"] == 2
    assert row["seller_count"] == 2
    assert row["items_value_brl"] == 30
    assert row["freight_value_brl"] == 5
    assert row["interstate_item_fraction"] == 0.5
    assert row["total_weight_g"] == 10
    assert row["weight_missing_fraction"] == 0.5
    assert row["dimensions_missing_fraction"] == 0.5
    assert row["mean_volume_cm3"] == 24
    assert row["primary_seller_state"] == "RJ"  # deterministic tie break


def test_orphan_seller_is_rejected(cart):
    cart["order_items"].loc[0, "seller_id"] = "unknown"
    with pytest.raises(ValueError, match="no seller"):
        build_features(**cart)


def test_entirely_missing_catalog_and_states_remain_missing(cart):
    for column in ("product_category_name", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"):
        cart["products"][column] = pd.NA
    cart["sellers"]["seller_state"] = pd.NA
    row = build_features(**cart).iloc[0]
    assert pd.isna(row["primary_product_category"])
    assert pd.isna(row["primary_seller_state"])
    assert pd.isna(row["total_weight_g"])
    assert pd.isna(row["interstate_item_fraction"])
    assert row["weight_missing_fraction"] == 1
    assert row["state_missing_fraction"] == 1


def test_calendar_label_and_knowledge_time():
    orders = pd.DataFrame([
        {"order_id": "late", "order_status": "delivered", "order_purchase_timestamp": "2017-12-01 00:00:00", "order_estimated_delivery_date": "2017-12-09 00:00:00", "order_delivered_customer_date": "2017-12-12 10:00:00"},
        {"order_id": "same_day", "order_status": "delivered", "order_purchase_timestamp": "2017-12-01 00:00:00", "order_estimated_delivery_date": "2017-12-09 00:00:00", "order_delivered_customer_date": "2017-12-09 23:59:00"},
        {"order_id": "pending", "order_status": "shipped", "order_purchase_timestamp": "2017-12-01 00:00:00", "order_estimated_delivery_date": "2017-12-09 00:00:00", "order_delivered_customer_date": pd.NA},
    ], dtype="string")
    result = labels(orders).set_index("order_id")
    assert result.loc["late", "late_delivery"] == 1
    assert result.loc["late", "label_available_at"] == pd.Timestamp("2017-12-10")
    assert result.loc["same_day", "late_delivery"] == 0
    assert result.loc["same_day", "label_available_at"] == pd.Timestamp("2017-12-09 23:59:00")
    assert result.loc["pending", "eligibility"] == "not_delivered_cohort"


def test_future_labels_are_purged_at_each_split_boundary():
    frame = pd.DataFrame({
        "order_id": ["train", "train_unknown", "validation", "validation_unknown", "test", "test_unknown"],
        "prediction_at": pd.to_datetime(["2017-12-01", "2017-12-30", "2018-01-04", "2018-04-29", "2018-05-10", "2018-08-29"]),
        "label_available_at": pd.to_datetime(["2017-12-02", "2018-01-04", "2018-01-05", "2018-05-05", "2018-05-20", "2018-11-02"]),
        "eligibility": "eligible", "item_count": 1,
    })
    result = assign_splits(frame).set_index("order_id")
    assert result["split"].to_dict() == {"train": "train", "train_unknown": "excluded", "validation": "validation", "validation_unknown": "excluded", "test": "test", "test_unknown": "excluded"}
    assert result.loc["train_unknown", "exclusion_reason"] == "label_unavailable_at_cutoff"
    assert result.loc["validation_unknown", "exclusion_reason"] == "label_unavailable_at_cutoff"
