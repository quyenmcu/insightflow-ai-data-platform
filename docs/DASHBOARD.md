# Commerce dashboard and guided analytics assistant

The first application explores verified Olist warehouse aggregates and answers six supported metric questions. It uses a historical snapshot rather than live warehouse queries. The assistant is deterministic and explicitly labeled as guided metric answers; it is not a generative model, forecast, or causal analysis system.

Open the owner-private [InsightFlow Analytics dashboard](https://insightflow-analytics-quyenmcu.funnyvale2.chatgpt.site).

## Features

- Inclusive purchase-month range and customer-state filters shared by every chart, metric, answer, and CSV export.
- Delivered item GMV, delivered order count, late-delivery rate, and average delivered order item value.
- Monthly GMV chart with exact monthly values available in a table, delivery breakdown, and state ranking.
- Six supported assistant questions, with visible filter scope, calculation, source, and export date. Unsupported questions are declined with suggestions. Changing filters clears the previous answer.
- CSV download of the selected month/state groups; monetary columns explicitly use integer BRL cents.
- Responsive layout, labeled controls, keyboard access, accessible chart descriptions, and loading/error/empty states.

The snapshot contains 565 month/state groups, **99,441 orders**, **96,478 delivered orders**, **96,470 labeled deliveries**, **6,534 late deliveries**, and **R$13,221,498.11 delivered item GMV**. It spans September 2016 through October 2018; source boundary months may be partial and some months have no delivered orders. It is not current trading data.

## Metric contract

The source is `analytics.order_summary`, reconciled with `analytics.daily_sales`. All money is exported as exact integer cents and divided by 100 for display. Filters use the source purchase calendar month, not delivery date. Customer state is the destination customer's state, not seller state. The source does not document a timezone, so no conversion is invented.

| Metric | Definition |
| --- | --- |
| Orders | Count of orders across all statuses in the selection. |
| Delivered orders | Count where final status is `delivered`. |
| Item GMV | Sum of item prices for delivered orders; freight excluded. It is not profit or net revenue. |
| Average order value | Delivered item GMV divided by delivered order count. |
| Late delivery rate | Delivered orders with actual calendar date after the estimate, divided by delivered orders with usable actual and estimated dates. Eight missing labels are excluded in the full snapshot. |
| On-time count | Labeled delivered orders minus late delivered orders. Delivery on the estimated day is on time. |
| Delivered payments / freight | Separate sums for delivered orders; payment relationships are aggregated before joining and need not match item GMV. |

All ratios are recomputed from summed counts; state/month averages are not averaged together. Zero denominators show “Not available.” State/month ranking ties use alphabetical order. The chart fills absent calendar months with zero GMV; source rows in the exact-value table and CSV retain the available aggregate groups.

## Provenance and export

`ingestion/batch/export_dashboard.py` runs a **read-only, repeatable-read transaction** (see [PostgreSQL isolation documentation](https://www.postgresql.org/docs/16/transaction-iso.html)). It checks that the latest analytics build uses the latest raw ingestion, compares all nine source hashes against the registered manifest, and aggregates orders by purchase month and customer state. It reconciles those groups against independently queried order-summary totals, daily-sales totals, and the registered PostgreSQL/BigQuery baseline. A failed check prevents snapshot publication.

The JSON contains source and aggregate hashes, warehouse build ID/time, export time, metric totals, and aggregate rows. It contains no order/customer identifiers, review text, credentials, or per-order predictions. Aggregate SHA-256: `284f90b206f0041c5dc7f5420dfd7afed603580d96f354e9271de70a2cabb3c4`.

Re-export after a successful local warehouse build:

```powershell
docker compose build ingestion
docker compose run --rm -v "${PWD}/dashboard:/app/dashboard" -v "${PWD}/infrastructure:/app/infrastructure:ro" ingestion python -m ingestion.batch.export_dashboard
```

This updates `dashboard/dist/snapshot.json` atomically. It does not deploy the website. The registered baseline intentionally makes this exporter specific to the verified Olist snapshot; a different dataset needs a reviewed baseline and documented metric contract.

## Local preview and tests

```powershell
docker compose --profile tools up -d dashboard
# Open http://localhost:8765
node --test dashboard/tests/metrics.test.mjs dashboard/tests/snapshot.test.mjs
docker compose --profile tools stop dashboard
```

The static server is bound to local loopback; it serves only `dashboard/dist`. No Node dependencies or framework build are needed. Python tests also exercise the exporter against disposable PostgreSQL views, source-provenance mismatch, stale builds, exact cents, and invalid counts. The full tracked Python suite passed 50 tests; the dashboard suite passed 12 tests.

Browser checks covered state/month filters, matching assistant/KPI totals, rejected causal questions, invalid-range recovery, reset, and a CSV download containing the selected RJ groups. A narrow viewport DOM check found no horizontal page overflow. [Dashboard preview](../reports/dashboard/overview.png).

## Hosting and updates

The buildless application source is under `dashboard/dist`; Sites identity is stored in `dashboard/.openai/hosting.json`. It is published through Sites with owner-private access. Repository visibility and hosted-site access are separate settings: a public GitHub repository does not make the hosted Site public.

The first publication succeeded from Sites source commit `312706e81e7abd9c1a83d4b38a0af1b292f483ca`, saved version `appgprj_6ae9626c01988191828dd9189abe089f~appgver_4be7e5d3b0c4819196703e73219e72d8`. Sites source and the main GitHub repository have separate commit histories; the deployed `dist` files match this repository's dashboard assets.

Sites publication uses an isolated ignored checkout under `data/processed/insightflow-site`. Copy the current `dist` and hosting manifest there, acquire source access for the existing Site ID, then use the Sites source helper to synchronize and package the exact source before private deployment. Never place credentials in the repository. The archive and temporary source checkout are ignored.

The weekly GitHub workflow refreshes warehouse tables; it **does not automatically refresh or republish this dashboard**. The current fixed Olist snapshot remains unchanged until an explicit re-export and publication. The browser sends no questions to an external model or warehouse; questions are processed locally with an allowlisted metric resolver. No BigQuery jobs or model API calls are issued by this application.

## Remaining application work

This first milestone does not implement a live analytics API or a general natural-language agent. Those require an explicit live-use case, bounded query costs, server-side authentication and authorization, and a constrained metric/query contract. Delivery-delay predictions remain experimental and are not shown as operational recommendations. New live prediction acceptance still requires prospectively reserved outcomes.
