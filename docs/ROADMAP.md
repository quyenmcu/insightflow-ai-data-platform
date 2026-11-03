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

- [x] Add an independent local streaming replay, durable inbox, deduplicating consumer, and event-day metrics with recovery tests.
- [ ] Select a real event source and evaluate a cloud broker/consumer within an agreed budget before cloud streaming deployment.

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
4. **Business assistant:** a guided assistant now answers six approved metric questions from the verified snapshot, with calculations and scope. General language understanding and generated-query validation remain future work.
5. **Application:** a responsive historical analytics dashboard now includes shared filters, charts, state ranking, and CSV export. Live API integration and deployment-ready predictions remain future work.
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

Application milestone progress:

- [x] Export aggregate-only warehouse metrics with source and reconciliation checks.
- [x] Build a responsive historical analytics dashboard with filters and CSV export.
- [x] Answer supported metric questions with scope, definitions, and source evidence.
- [x] Connect weekly warehouse builds to validated aggregate publication and dashboard loading, with fallback and freshness notices.
- [x] Prepare and test read-only calculation tools for conversational comparisons, rankings, trends, and definitions.
- [x] Implement a bounded authenticated analytics chat API over verified historical aggregates.
- [x] Add and evaluate natural-language comparisons and follow-up questions beyond guided questions.
- [ ] Replace the owner's temporary 24-hour API key for durable hosted availability.

Each milestone should have tests or recorded validation and documentation. See the analytics-agent guide for model-call limits, accounting, evidence, and temporary credential lifetime. Predictive deployment remains ahead.
