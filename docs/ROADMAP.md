# InsightFlow AI roadmap

## Working locally

- [x] Dockerized PostgreSQL and Python ingestion service.
- [x] Load all nine Olist CSV files into raw tables with source digests and counts.
- [x] Validate schemas and natural keys; roll back failed loads.
- [x] Build typed staging tables with integrity constraints.
- [x] Produce order summaries and daily delivered-order sales.
- [x] Test repeatability, CSV edge cases, join totals, and rollback in disposable databases.
- [x] Add a GitHub Actions workflow for the integration suite.

## Next milestones

Cloud foundation progress:

- [x] Create a dedicated Google Cloud development project.
- [x] Configure a project-scoped monthly alert budget.
- [x] Create a private Cloud Storage bucket and upload the nine source CSV files with a checksum manifest.
- [x] Create co-located raw, staging, and analytics BigQuery datasets.
- [x] Load and validate all nine BigQuery raw tables against the source snapshot.
- [x] Port typed staging and analytics models to GoogleSQL with transactional refresh and PostgreSQL parity checks.
- [x] Add a weekly GitHub Actions pipeline with keyless authentication, test dependencies, and reports.

1. **Cloud landing and warehouse:** choose a Google Cloud project, configure a raw Cloud Storage landing area, model analytics in BigQuery, and document cost controls.
2. **Orchestration:** a weekly workflow now orders tests, ingestion, and publication with failure reports and manual reruns. Advanced orchestration and transient-error retry policies can follow when needed.
3. **Delivery-delay prediction:** checkout features, chronological splits, and a fixed logistic baseline are implemented. Investigate weak held-out generalization with validation-driven experiments before deployment.
4. **Business assistant:** ground answers in approved analytics and documented metric definitions; validate generated queries and report supporting data.
5. **Application:** expose analytics and predictions through an API and dashboard.
6. **Operations:** add deployment automation, monitoring, and operational documentation.

AI milestone progress:

- [x] Define the checkout prediction point, delivered-order target, and availability assumptions.
- [x] Build 21 candidate features without outcome fields.
- [x] Create chronological splits with label-maturity exclusions and source/code provenance.
- [x] Fit preprocessing on training data and train a logistic regression baseline.
- [x] Evaluate validation/test performance and save the model and model card.
- [x] Analyze the frozen baseline on training/validation inputs, publish aggregate diagnostics, and document cohort-selection limits.
- [x] Compare fixed calendar/nonlinear candidates on historical development folds; retain the reference when neither improves ranking.
- [ ] Investigate weak temporal generalization using validation-driven experiments and define a fresh final holdout.

Each milestone should have tests or recorded validation and documentation. The scheduled warehouse pipeline and experimental baseline are implemented; predictive improvements, the assistant, and the dashboard remain ahead.
