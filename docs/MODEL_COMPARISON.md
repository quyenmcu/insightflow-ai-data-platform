# Historical model comparison

Neither proposed improvement beat the reference logistic regression in any of three historical evaluation months. Keep the original experimental baseline; this comparison does not justify model promotion or deployment.

## Fixed experiment

Run `20261103T041659Z_76c7fb0c` uses only `train.csv` from dataset generation `20261103T032101Z_553ed0bd`. The loader verifies its checksum and the manifest against the original baseline metrics. It does not load the 2018 validation/test CSVs, the original model bundle, or prior prediction files. The existing model and threshold remain unchanged. No operating threshold is selected, and no fitted candidate artifact is promoted.

The candidate list, parameters, folds, and 60-day windows were fixed in code before this run. The hypotheses were informed by the earlier validation analysis, so this is exploratory development evidence, not independent final acceptance. No parameter search or repeated adjustment to these results was performed.

Each fold trains from expanding history with purchase time strictly before origin minus 60 days and label availability strictly before origin. Evaluation purchases fall in the following calendar month; their labels must be available strictly before month end plus 60 days. This grace period gives every evaluation purchase at least 60 days before the cutoff, rather than using labels available immediately at month end. Outcomes still depend on the delivered-only source cohort and label availability; the grace period is not proof that all orders have resolved.

| Evaluation month | Training purchase cutoff (exclusive) | Training orders | Evaluation orders | Late orders | Evaluation label cutoff (exclusive) |
| --- | --- | ---: | ---: | ---: | --- |
| July 2017 | May 2 | 7,630 | 3,872 | 108 | September 30 |
| September 2017 | July 3 | 14,378 | 4,150 | 182 | November 30 |
| October 2017 | August 2 | 18,232 | 4,478 | 187 | December 31 |

All evaluation cutoffs precede the original January 1, 2018 training-label cutoff; the loader rejects protocols that violate this boundary. Fold counts are measured within the original eligible training CSV. Its preexisting exclusions (including unresolved labels at the original cutoff, nondelivered orders, and missing outcomes) remain outside these denominators. Zero additional fold-maturity exclusions does not mean the source population has no excluded orders. These are conditional benchmark results, not population delay rates.

All preprocessing is fitted separately within each fold:

- **Training prior:** constant probability equal to that fold's training prevalence.
- **Linear logistic:** the original preprocessing and unweighted L2 logistic settings, fitted anew on each fold's training rows.
- **Cyclic month logistic:** replaces numeric month with sine/cosine features; all other logistic settings remain the same.
- **Histogram gradient boosting:** 150 iterations, learning rate 0.05, 15 maximum leaves, minimum 50 samples per leaf, L2 regularization 10, seed 42, and early stopping disabled. Numeric missing values remain native missing values; categorical values use training-only ordinal encoding and explicit native categorical splits. Unseen categories become missing rather than acquiring an artificial ordinal ranking.

## Results

These summaries weight the three evaluation months equally. Average precision (AP) is the primary descriptive ranking measure; AP lift divides each fold's AP by its own late prevalence before averaging. Brier score measures probability error and combines discrimination with calibration. There are no significance tests or confidence claims from only three overlapping-history folds.

| Candidate | Mean AP | AP range | Mean AP lift | Mean Brier (lower better) | Folds beating linear AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Training prior | 0.03784 | 0.02789–0.04386 | 1.000 | 0.03648 | 0/3 |
| Linear logistic | **0.07670** | 0.06052–0.10753 | **2.042** | **0.03642** | Reference |
| Cyclic month logistic | 0.07538 | 0.05954–0.10622 | 2.001 | 0.03681 | 0/3 |
| Histogram gradient boosting | 0.06941 | 0.04633–0.10526 | 1.806 | 0.03649 | 0/3 |

The reference model's mean Brier advantage over the training-prior dummy is very small. Mean predicted minus observed risk is -0.35 percentage points for linear logistic, -1.68 for cyclic month logistic, and -0.80 for gradient boosting. An average gap can hide errors within risk bands or individual periods and does not establish calibration.

Changing month encoding alone did not improve this benchmark; nonlinear interactions with these fixed tree settings also did not improve ranking. This does not prove that nonlinear methods cannot help, or that the original model generalizes to current orders. These earlier 2017 periods do not reproduce the pronounced 2018 validation shift, and their scores should not be compared directly with the original 2018 validation AP because both training cohorts and evaluation prevalence differ.

## Reproduce and inspect

```powershell
docker compose --profile tools build comparison
docker compose --profile tools run --rm comparison
```

Generated outputs stay under ignored `data/processed/model_comparison/<run_id>`, with an atomic `LATEST.json` pointer. The committed [report](../reports/model_comparison/report.json), [per-fold metrics](../reports/model_comparison/fold_metrics.csv), [cohort counts](../reports/model_comparison/folds.csv), and [summary](../reports/model_comparison/summary.csv) contain aggregates only. The report records source/input/code hashes, parameters, dates, and runtime versions. This experiment runs locally without Google Cloud queries.

The tests cover strict training/evaluation time boundaries, delayed label availability, missing/unseen features for each candidate, cyclic calendar encoding, probability validity, and a loader that only requests the training split. The full tracked suite passed 46 tests.

## Next decision

Preserve the original model as the reference. Before further model search, settle the operational objective and a cohort protocol that represents intended live use. A separate time-ordered calibration experiment could assess probability reliability, but this run did not perform one. Historical Olist test results have already been inspected; final deployment acceptance requires genuinely new, prospectively reserved outcomes. The assistant and dashboard can begin with verified warehouse analytics while predictive work remains experimental.

Method references: [scikit-learn temporal cross-validation guidance](https://scikit-learn.org/stable/modules/cross_validation.html) and [histogram gradient boosting parameters](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html).
