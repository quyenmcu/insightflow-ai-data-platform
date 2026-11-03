# Delivery-delay prediction: dataset definition

## Prediction and target

Predict at the order's purchase/checkout timestamp, before approval or shipping.
The target is 1 when actual customer delivery **calendar date** is later than the
recorded estimated delivery date; same-day arrival is on time. Timestamp values
and split boundaries retain the dataset's timezone-unspecified source clock.

The labeled cohort contains final-status `delivered` orders with both outcome
dates and a cart. Missing outcomes, delivery before purchase, and estimated dates
before the purchase date are excluded and counted in the dataset manifest.
This estimates lateness **conditional on eventual delivery**, not cancellation
or non-delivery risk for every checkout. Final-status cohort selection creates
selection bias that must be considered before deployment.

For an on-time order, its label becomes observable at delivery. For a late order,
lateness becomes observable at the start of the day after the promised date;
the retrospective timeline shows it had not arrived by then. The actual arrival
can be much later. This label-availability timestamp is metadata, never an input.
The public snapshot does not expose revisions of promised dates, so this timing
is a reconstruction using the recorded deadline, not a versioned event log.

## Candidate input features

| Inputs | Features |
| --- | --- |
| Purchase timestamp | Month, weekday (Monday = 0), hour |
| Cart lines | Item count, distinct product/seller/category/state counts |
| Cart quote | Item value, freight value, freight share of combined value |
| Customer/seller locations | Customer state, most frequent seller state, interstate item fraction, missing-state fraction |
| Product catalogue | Most frequent category, observed total weight, mean item volume, longest dimension, missing-weight/dimension fractions |

Category and seller-state ties resolve alphabetically for reproducibility.
Zero physical dimensions or weight are treated as unavailable; negative values
are rejected. Other missing attributes remain missing. Total weight sums known item weights and is
paired with a missing fraction. Volume requires all three dimensions. Monetary
features use floats rounded to cents; this dataset is not the financial ledger.

The predictor function projects explicit checkout input columns. It cannot use
final order status, actual/estimated delivery timestamps, approval times,
carrier handoff times, shipping deadlines, reviews, or payment records. An
automated test changes future outcome fields and requires identical features.
Anonymized order, product, seller, and customer identifiers are not model inputs.

The Olist catalogue and cart data are static snapshots without effective-date
history. Their availability at checkout is an **assumption** for this baseline.
Final cart contents and prices serve as proxies for checkout state. A deployed
system needs versioned, point-in-time cart and catalogue records to verify this.
Geolocation averages and historical seller performance are excluded for now.

## Chronological split and label maturity

| Split | Purchase window | Labels must be known before |
| --- | --- | --- |
| Training | Before January 1, 2018 | January 1, 2018 |
| Validation | January 1 to April 30, 2018 | May 1, 2018 |
| Test | May 1 to August 31, 2018 | November 1, 2018 |

All upper bounds are exclusive. Training and validation rows whose labels cross
their maturity cutoffs are purged; they are not moved into later splits. The
November observation cutoff allows test outcomes to mature and is explicitly
recorded in the manifest. Purging can change class balance near boundaries.
Repeated customers may appear later chronologically, but identity columns are
excluded from the feature matrix. There is no random train/test split.

No imputer, scaler, category vocabulary, feature selector, or model is fitted
by this step. The next milestone will fit those operations on training data
only, select decisions using validation data, and reserve test data for final
evaluation. These practices follow scikit-learn's guidance on
[data leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage)
and [time-ordered evaluation](https://scikit-learn.org/stable/modules/cross_validation.html#time-series-split).

## Reproduce locally

```powershell
docker compose build features
docker compose run --rm features
```

The builder detects CSVs in `data/raw/olist` or `data/raw`, validates headers and
record widths, and checks the five consumed files against the uploaded source
manifest's SHA-256 digests. It performs no cloud queries and adds no dependencies.
Docker mounts raw source files read-only and permits output only under processed
data. To select a directory explicitly:

```powershell
docker compose run --rm features python -m ml.build_dataset --data-dir data/raw
```

Completed generations are stored under `data/processed/delivery_delay/<run_id>`:

- `features.csv`: one checkout feature row per order, including unlabeled orders.
- `train.csv`, `validation.csv`, `test.csv`: eligible labeled splits.
- `excluded.csv`: order IDs, prediction times, and exclusion reasons for auditing.
- `manifest.json`: feature allowlists, source/code digests, split boundaries,
  row counts, class balance, missingness, and timestamp ranges.

`LATEST.json` is atomically replaced only after all files and the manifest are
written. Previous generations are preserved; a failed generation is not made
current. All generated datasets are ignored by Git. Source code, tests, and
documentation are versioned.

When training, select **only** the manifest's numeric and categorical feature
allowlists. `order_id`, `prediction_at`, `label_available_at`, and the target
column must never be added to the feature matrix automatically.

## Validated snapshot — November 3, 2026

The generated checkout feature table contains 99,441 orders and 21 inputs.
The source fingerprint is
`09b5148b3a846d400c6c303505b23439cc111b07321abcf203c84894db512afa`.

| Split | Orders | Late orders | Late rate |
| --- | ---: | ---: | ---: |
| Training | 41,528 | 2,096 | 5.05% |
| Validation | 24,861 | 2,727 | 10.97% |
| Test | 25,352 | 1,115 | 4.40% |

The 7,700 excluded orders comprise 4,729 with labels unavailable at the cutoff,
2,963 outside the delivered cohort, and 8 missing outcome dates. None were
excluded for invalid timelines or missing cart items in this snapshot.

Generated split files were checked for unique/disjoint order IDs, exact feature
allowlists, finite observed numeric features, and purchase/label timestamp
boundaries. Missing catalogue attributes remain for training-only preprocessing.
The different class rates show a time-period shift; baseline evaluation should
include class prevalence and PR-AUC rather than relying on accuracy alone.
The first [logistic baseline and model card](BASELINE_MODEL.md) are now available.
