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

1. **Cloud landing and warehouse:** choose a Google Cloud project, configure a raw Cloud Storage landing area, model analytics in BigQuery, and document cost controls.
2. **Orchestration:** schedule ingestion and transformations with retries, dependency checks, and useful failure reporting.
3. **Delivery-delay prediction:** define prediction time, build features available then, use chronological train/validation/test splits, and evaluate a baseline before more complex models.
4. **Business assistant:** ground answers in approved analytics and documented metric definitions; validate generated queries and report supporting data.
5. **Application:** expose analytics and predictions through an API and dashboard.
6. **Operations:** add deployment automation, monitoring, and operational documentation.

Each milestone should have an implementation branch, tests or recorded validation, and documentation. Cloud deployment, machine learning, the assistant, and the dashboard have not been implemented yet.
