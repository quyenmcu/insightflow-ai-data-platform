# Delivery-delay baseline

The first model is a fixed L2 logistic regression trained locally on 41,528
orders, using the [checkout dataset definition](DELIVERY_PREDICTION.md). It is an
experimental benchmark with weak held-out performance, not a production model.

## Evaluation protocol

Numeric medians, scaling, category handling, and one-hot vocabulary are fitted
on training rows only. The model receives only the 21 declared inputs. IDs,
prediction/label timestamps, and target fields are excluded. No hyperparameter
search was performed. The classifier uses C=1, lbfgs, max_iter=2000, and no class
weighting; it converged in 61 iterations with 141 transformed features.

The decision threshold, 0.037002995, maximizes F1 on the 24,861 validation orders;
ties favor fewer alerts. The threshold is fixed before loading the 25,352 test
orders. The estimator is not refitted on validation or test data. F1 is a
demonstration objective because business costs and alert capacity are undefined.

| Metric | Validation | Held-out test |
| --- | ---: | ---: |
| Late prevalence / no-skill average precision | 0.1097 | 0.0440 |
| Model average precision | 0.1998 | 0.0528 |
| ROC-AUC | 0.6591 | 0.5591 |
| Precision at selected threshold | 22.94% | 5.46% |
| Recall at selected threshold | 42.79% | 46.37% |
| F1 at selected threshold | 0.2987 | 0.0977 |
| Brier score, lower is better | 0.1027 | 0.0424 |

Average precision is scikit-learn's non-interpolated precision-recall summary,
not trapezoidal PR area. On test data the selected threshold flags 9,468 orders:
517 true positives and 8,951 false positives, while missing 598 late orders.
The confusion matrix is `[[15286, 8951], [598, 517]]`, ordered
`[[TN, FP], [FN, TP]]`. The default 0.5 threshold flags no late orders.

Ranking is only slightly better than the constant-score baseline on the test
period, and the Brier score is slightly worse than the training-prior dummy's
0.0421. The validation/test gap and different class prevalence warrant further
analysis. These observations do not isolate a cause or establish business value.
The false-positive burden is too high to describe this as deployment-ready.

The test set has now been evaluated. Subsequent feature/model choices should
use validation or rolling historical windows, disclose benchmark test reuse,
and reserve a fresh final holdout before making deployment claims.

## Artifacts and reproduction

The [versioned baseline bundle](../models/delivery_delay_baseline/) contains the
fitted pipeline, dummy comparator, selected threshold, feature allowlist,
metrics, coefficients, model card, and exact training environment versions.
Detailed prediction CSVs stay local under ignored processed-data directories.

```powershell
# Build features if this is a fresh checkout.
docker compose build features training
docker compose run --rm features
docker compose run --rm training
```

Model generations are written under `data/processed/delivery_delay_models`.
`LATEST.json` is updated only after evaluation, serialization, and a saved-model
prediction roundtrip check succeed. The report records source/data/code hashes,
split digests, library versions, solver iterations, and metrics at both thresholds.
Training performs no Google Cloud queries or cloud model deployment. The weekly
cloud workflow continues to maintain the warehouse; it does not retrain this model.

The unversioned catalogue/cart assumptions, delivered-only cohort selection,
label reconstruction, and temporal exclusions from the dataset definition still
apply. Coefficients describe this regularized model, not causal business effects.
The artifact uses joblib and requires a compatible runtime; load trusted bundles
only. Serialization/loading can execute Python code.

References: [threshold tuning](https://scikit-learn.org/stable/modules/classification_threshold.html),
[average precision](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html).
