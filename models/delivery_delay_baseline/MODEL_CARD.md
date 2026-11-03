# Delivery-delay logistic regression baseline

This is an experimental historical benchmark, not a production decision system.
It predicts late delivery at checkout, conditional on eventual delivery.

## Protocol

The model uses 21 checkout candidate inputs with numeric median imputation and
standardization, constant categorical missing-value handling, and one-hot
encoding. All preprocessing and classifier parameters are fitted on training
rows only. Unseen validation/test categories are ignored by the encoder.
The fixed model is unweighted L2 logistic regression, C=1, lbfgs, max_iter=2000.
There is no hyperparameter search or refit on validation/test data.

The operating threshold **0.037003** maximizes validation F1,
with ties favoring the higher threshold. F1 is a demonstration objective; no
business cost matrix or production alert budget has been defined.

| Metric | Validation | Held-out test |
| --- | ---: | ---: |
| Late prevalence | 0.1097 | 0.0440 |
| Average precision | 0.1998 | 0.0528 |
| ROC-AUC | 0.6591 | 0.5591 |
| Precision | 0.2294 | 0.0546 |
| Recall | 0.4279 | 0.4637 |
| F1 | 0.2987 | 0.0977 |

Average precision is the non-interpolated precision-recall summary from
scikit-learn, not trapezoidal PR area. A constant-score no-skill ranking has AP
equal to the evaluated split's prevalence. The report also includes default
0.5-threshold metrics, a training-prior dummy classifier, Brier score, accuracy,
and confusion matrices ordered [[TN, FP], [FN, TP]].

## Limitations and provenance

Catalogue/cart availability at checkout is an assumption in the unversioned
Olist snapshot. Final delivered-order selection excludes cancellations and
unresolved deliveries. Label maturity exclusions change the sample near split
boundaries. The markedly different class rates across periods indicate drift.
This baseline does not establish calibrated probabilities, business utility,
causal effects, or performance for current live orders. Coefficients are not
causal feature effects. The test set has now been evaluated; later comparisons
must disclose reuse and avoid tuning choices to these test results.

Dataset run: `20261103T032101Z_553ed0bd`.
Source snapshot: `09b5148b3a846d400c6c303505b23439cc111b07321abcf203c84894db512afa`.
Training code SHA-256: `6da1951e267f1527f0c3f526367399a8e17268a9b4b09172598b3c1c6f758279`.
Runtime versions and input/output file digests are recorded in metrics.json.
The local joblib bundle contains the fitted preprocessing, classifier,
validation-selected threshold, feature allowlist, and dummy baseline. Load only
trusted bundles in a compatible runtime; joblib loading can execute Python code.
