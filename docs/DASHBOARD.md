# Commerce dashboard and guided analytics assistant

The application explores verified Olist warehouse aggregates and answers six supported metric questions. It loads the latest published warehouse snapshot on page open, with publication after the Monday 08:00 Taiwan pipeline. This is scheduled historical data, rather than per-question live warehouse queries. The assistant is deterministic and explicitly labeled as guided metric answers; it is not a generative model, forecast, or causal analysis system.

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
node --test dashboard/tests/*.test.mjs
docker compose --profile tools stop dashboard
```

The static server is bound to local loopback; it serves only `dashboard/dist`. No Node dependencies or framework build are needed. Python tests also exercise the exporter against disposable PostgreSQL views, source-provenance mismatch, stale builds, exact cents, and invalid counts. The expanded suites cover cloud export caps, aggregate parity, publication/readback, invalid-feed fallback, and freshness notices: 62 Python tests and 18 dashboard tests passed in GitHub CI.

Browser checks covered state/month filters, matching assistant/KPI totals, rejected causal questions, invalid-range recovery, reset, and a CSV download containing the selected RJ groups. A narrow viewport DOM check found no horizontal page overflow. [Dashboard preview](../reports/dashboard/overview.png).

## Hosting and updates

The buildless application source is under `dashboard/dist`; Sites identity is stored in `dashboard/.openai/hosting.json`. It is published through Sites with owner-private access. Repository visibility and hosted-site access are separate settings: a public GitHub repository does not make the hosted Site public.

The first publication succeeded from Sites source commit `312706e81e7abd9c1a83d4b38a0af1b292f483ca`, saved version `appgprj_6ae9626c01988191828dd9189abe089f~appgver_4be7e5d3b0c4819196703e73219e72d8`. Sites source and the main GitHub repository have separate commit histories; the deployed `dist` files match this repository's dashboard assets.

Sites publication uses an isolated ignored checkout under `data/processed/insightflow-site`. Copy the current `dist` and hosting manifest there, acquire source access for the existing Site ID, then use the Sites source helper to synchronize and package the exact source before private deployment. Never place credentials in the repository. The archive and temporary source checkout are ignored.

The weekly GitHub workflow refreshes warehouse tables, exports verified BigQuery aggregates, and publishes `snapshot.json` to the dedicated `codex/dashboard-data` branch after all checks pass. That branch contains only the snapshot and its history. On page open the dashboard reads that public aggregate file, validates its contract, totals, source fingerprint and SHA-256 checksum, and shows its warehouse build/export time. No Site republishing is needed for routine data refreshes. Reopen or reload an already open dashboard to load a newly published snapshot; CDN caching can delay visibility briefly.

If remote data is unavailable, corrupt, or invalid, the dashboard loads the bundled verified snapshot and displays a fallback notice. If the latest valid remote export is more than nine days old, it warns that the pipeline may need attention. If neither snapshot validates, it shows an error instead of metrics. Export failures leave the data branch unchanged. Publication failures before the branch reference update preserve the prior snapshot; failures in readback or report saving after an update are reported by the job and need investigation.

The browser sends no questions to an external model or warehouse; questions are processed locally with an allowlisted metric resolver. It makes an unauthenticated read of public aggregate data from GitHub. No cloud credentials or GitHub tokens are included in browser code. Pipeline export adds one BigQuery dry run and one bounded read query (maximum 1 GiB billed bytes); opening the dashboard runs no BigQuery jobs or model API calls. Refreshed export timestamps do not imply new commercial activity: the fixed source still contains 2016–2018 records.

See [scheduling and failure recovery](SCHEDULING.md) for the unattended writer, job identity, artifact handoff, and readback verification. The original PostgreSQL bundled snapshot remains the reference: BigQuery's complete month/state aggregate hash must match it before publication.

### End-to-end verification

[Cloud run 41603218894](https://github.com/quyenmcu/insightflow-ai-data-platform/actions/runs/41603218894) completed successfully on November 3, 2026. It built warehouse version `37bc35b1633e44be89efc269aaf21501`, verified all 565 aggregate groups, and published data commit `7172ec9b1b48d9e886f4d0fb8f61ee0ec5cb9201` with byte-for-byte readback. The browser then loaded that exact build ID through the public data feed and displayed the expected GMV. The export dry run estimated 7,180,047 processed bytes under its 1 GiB cap. An early query dry run now catches SQL syntax and budget errors before warehouse rebuilding.

The refresh-capable Site publication uses source commit `c148e3ac33953176443a276980c482d7d1c54b64`, saved version `appgprj_6ae9626c01988191828dd9189abe089f~appgver_c3b1062c01cc81919fd3f755a03ba2b6`. Its deployment succeeded. The hosted access gate requires ChatGPT sign-in in the verification browser session; functional feed and fallback checks were performed on the identical local assets. See the [verification record](../reports/dashboard/refresh-verification.json) and [refresh preview](../reports/dashboard/weekly-refresh.png).

## Remaining application work

This first milestone does not implement a live analytics API or a general natural-language agent. Those require an explicit live-use case, bounded query costs, server-side authentication and authorization, and a constrained metric/query contract. Delivery-delay predictions remain experimental and are not shown as operational recommendations. New live prediction acceptance still requires prospectively reserved outcomes.
