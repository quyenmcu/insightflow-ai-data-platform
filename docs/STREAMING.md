# Local streaming demo

`streaming/` is independent of the weekly batch pipeline. It replays Olist purchases as **simulated historical events**, consumes them incrementally, and updates a separate local SQLite database. It provisions no cloud services and makes no OpenAI calls.

The producer reads the local customers, order items, and orders CSVs, validates them, and orders events by original purchase timestamp with a stable ID tie-break. Replay pacing controls wall-clock arrival; it does not reproduce historical intervals. Source timestamps have no timezone and are retained unchanged. Events include a hashed order identity, purchase timestamp, customer state, and exact item-price cents. They omit customer IDs, addresses, reviews, and final delivery outcomes. Hashed identities remain local and are not a guarantee of anonymization.

Metrics are **all-status purchase counts and item value**, excluding freight. They are not the batch dashboard's delivered-order GMV, payment totals, or profit. Orders without items count as purchases with zero item value. Because Olist is a historical snapshot, this is a replay demonstration rather than a live production feed.

## Run locally

From the repository root with Python 3.11+, no additional packages are needed:

```powershell
# Terminal 1: consumer waits for new events; Ctrl+C stops it.
python -m streaming consume --watch

# Terminal 2: replay 100 purchases at 20 events/second.
python -m streaming replay --limit 100 --rate 20
python -m streaming status
```

Use `--rate 0` for a fast finite replay. The default limit is 100; a larger limit always starts at the beginning, and already-seen events are deduplicated. The producer preloads and validates these three source files before enqueueing any selected events; this implementation is sized for Olist, not unbounded source files.

An independent Compose file is also provided; the batch Compose configuration stays unchanged:

```powershell
docker compose -p insightflow-streaming -f streaming/compose.yml up -d consumer
docker compose -p insightflow-streaming -f streaming/compose.yml run --rm replay --limit 100 --rate 20
docker compose -p insightflow-streaming -f streaming/compose.yml exec consumer python -m streaming status
docker compose -p insightflow-streaming -f streaming/compose.yml down
```

Both processes use ignored `data/processed/streaming/events.sqlite`. WAL and SQLite locking support concurrent local producer/consumer processes on one machine. Do not put this database on a network filesystem. `down` stops the containers and preserves the bind-mounted database. For an isolated fresh run, place a new `--db` path **before** the subcommand and use that same path for producer, consumer, and status:

```powershell
python -m streaming --db data/processed/streaming/another-demo.sqlite replay --limit 100 --rate 0
python -m streaming --db data/processed/streaming/another-demo.sqlite consume
python -m streaming --db data/processed/streaming/another-demo.sqlite status
```

## Delivery and recovery

The durable inbox separates event creation from processing. Duplicate event IDs with identical payloads are ignored, including after restart. Conflicting payloads for an existing ID fail rather than silently changing totals. The consumer commits each aggregate update and inbox acknowledgment in one transaction; a failed transaction leaves the event pending for retry. This provides idempotent local processing, not an end-to-end exactly-once guarantee for future external brokers.

Invalid queued events move to `rejected` with a generic reason and remain available for local inspection; subsequent valid events can proceed. Storage/SQL failures stop processing and roll back, rather than marking an unprocessed event as complete. Out-of-order events update their original purchase-day aggregate; windows are not closed and there are no watermarks or correction events. Changing an accepted event requires a new contract and correction strategy, not overwriting the inbox.

No stream data is exported to the verified batch snapshot or hosted AI assistant. The queue and daily aggregates persist and grow until the owner archives or removes a demo database. This first module has no retention service, external broker, distributed workers, public ingest API, cloud consumer, or dashboard integration.

## Verification

```powershell
python -m unittest discover -s streaming/tests -v
```

Checks cover restart/deduplication, conflicting duplicates, atomic rollback after an injected database failure, invalid-event quarantine, late-arriving event-day updates, exact cents, and deterministic replay without final outcomes. CI runs this suite separately from the batch image and database tests.

The local two-process smoke run consumed 100 purchases with 1,525,891 BRL cents of item value. Replaying the same 100 events produced 100 duplicates and no extra counts. The verified batch snapshot file hash stayed unchanged. See the [verification record](../reports/streaming-verification.json). Demo containers were stopped after verification; the local demo database remains available for `status`.
