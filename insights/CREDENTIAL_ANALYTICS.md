# Credential analytics: phase 1

This document covers the credential registry, accounting, collection reliability,
and `/credential-analytics` React page, which consumes these APIs
for details, comparison, and statistical metadata editing. It does not deploy
services, change routing, or start another queue consumer. Python's standard
library is the only backend dependency.

## Data and identity

Opening a database adds nullable event fields, credential/binding tables, indexes,
and a persistent instance ID. Existing event IDs, source labels, token values and
prices are retained; existing rows stay `event_schema=1`, unassociated. The
migration is repeatable. Use SQLite's backup API before upgrading a running WAL
database; do not copy just the main file.

New executions with an upstream `execution_id` use an instance-scoped v2 identity.
When it is missing, the collector falls back to the old event fingerprint plus
auth index (if available). That fallback cannot distinguish identical attempts
with missing IDs. Do not replay previously consumed historical events across the
old/v2 cutover: no cross-version reconciliation of such replays is implemented.

The existing collector reads `/v8/management/credentials` at most once every 30
seconds and filters its metadata in memory. Only an opaque auth index and an HMAC
of identity evidence are retained, alongside generated labels. Emails, paths,
account IDs, authentication contents and raw credential names are not copied into
the new registry. Existing event source sanitization is unchanged. Only this
credentials endpoint is mapped in phase 1; API-provider configuration adapters
are a separate follow-up and must filter secrets before storage/output.

Bindings have observation intervals. If the same index presents changed identity
evidence, create a new credential and mark events between the last matching and
new observation as ambiguous. Do not map old history using current labels or
email similarity. If a provider replaces an account without changing any exposed
identity evidence, this change cannot detect it. A missing/invalid metadata
snapshot never causes inferred credential removal. Complete empty snapshots can
mark previous credentials as no longer configured. Removed/reintroduced indexes
are separate objects by default. No automatic merge/backfill API is exposed.

Aliases, current primary groups, and statistical archive flags never modify
authentication files, account availability or routing. Historical group queries
use the current primary group, not a group-at-execution snapshot. Configured
zero-traffic credentials remain visible with zero counts and null timings.

## Accounting and comparison

Validated `accounting_version=2` / `token_breakdown` values supply mutually
exclusive input/output buckets. The original raw numeric fields remain in the
database. Unknown/inconsistent accounting remains labelled; a structurally valid
unclassified total is preserved without inventing categories. An upstream queue
can already represent absent usage as numeric zeros; field presence alone cannot
prove that the upstream actually measured zero.

All aggregate/detail/export paths use the same token and cost expressions. Old
rows retain their prior price semantics. New rows with canonical complete
accounting and no cache writes can use current model tariffs; missing accounting
has a limited Codex/OpenAI fallback. Missing usage fields, unsupported service
tiers, an unmatched response model, inconsistent/unclassified accounting, and
cache writes without a supported tariff remain unpriced. Unknown is null, not
free. Credential-specific prices, cache-write tariffs and price snapshots are
not implemented. Prices remain current-rule estimates, not supplier invoices.

The count is upstream executions, not user requests. TTFT percentiles use only
successful streaming executions with a positive measurement. Values still have
CPA's possible first-packet fallback; they are not guaranteed visible-text TTFT.
Latency percentiles use positive durations under the chosen result/model filter.
P50/P95 use nearest rank and include sample counts. Never average per-account
percentiles into a global percentile. Each report uses one SQLite read snapshot.

## Authenticated endpoints

All routes are under `/v8/management/extensions/insights/` and retain the existing
management-key/origin checks:

- `GET credentials`: safe registry metadata, including zero-traffic entries.
- `GET credentials/summary`: one grouped execution/cost aggregation and two
  grouped percentile queries; returns credentials and an explicit `unlinked`
  bucket. It includes field-coverage counts for future runtime verification.
- `POST credentials/edit`: `{id, alias?, group_name?, archived?}`; no routing or
  index fields accepted.
- Existing `summary`, `events` and `export` also accept `credential_id` (including
  `unlinked`), `group_name`, and alias `search`, in addition to existing filters.

Details stay paginated at 25; CSV retains the existing 10,000-row cap. The new
endpoints do not expose auth indexes, evidence fingerprints or raw identifiers.

## Collection reliability

A nonblocking OS file lock prevents duplicate collectors targeting the same
resolved database path. It cannot prevent another program using a different
database or a live subscriber against the same CPA instance. Keep one collection
owner; do not connect Easy's real-time subscriber alongside this HTTP collector.

After a SQLite write failure the collector retains and retries the same received
batch before popping another queue batch. This buffer is in memory, not a durable
inbox. The upstream HTTP pop has no acknowledgement/replay guarantee, so a crash
or a lost HTTP response can still lose events. Shutdown during a failed write is
also not guaranteed to persist the pending batch. Status distinguishes successful
poll, received event, stored event, metadata failure, rejected records, duplicate
records and pending batch size. Counters cover the current process only.

## Local verification

Run from the repository root with the existing Python installation:

```powershell
python -B -m unittest discover -s insights -p 'test_*.py' -v
python -B insights/benchmark_credentials.py --rows 250000
```

Tests and the benchmark use their own temporary directories and synthetic
events. They do not open production credentials/SQLite or contact any upstream
model. The benchmark checks additive reconciliation and a concurrent writer; it
is a Windows/local-storage observation, not a VPS performance guarantee. No
browser validation or container image build is claimed by these checks.

The frontend's `bun run verify` and the separately recorded headless Edge checks
cover the page. Browser fixtures use a real loopback insights server with
synthetic records; they do not prove production compatibility or VPS performance.
The page defaults to manual refresh. Optional refresh skips hidden documents and
in-flight work; only the active detail view requests its data. Query replacements
abort their HTTP requests and hide prior-query results. Aborting a browser request
does not guarantee cancellation of SQL already running on the server.

## Summary query performance

Summary totals, hourly buckets and the top models share one filtered numeric
projection in the same read snapshot. SQLite 3.35+ gets a MATERIALIZED CTE; older
versions use the ordinary CTE syntax. The installed-engine fallback is unit
tested, not a claim of testing every older SQLite release. When the time range
includes every retained row, unkeyed summaries scan in storage order. Exact
credential/model filters use their corresponding indexes.

`event_options` is a small derived reference-count table for model/provider/
source/client choices. Transactional AFTER INSERT/UPDATE/DELETE triggers keep it
consistent, including ignored duplicates, pruning and rollback. It preserves
legacy NULL values and the existing globally sorted 500-value limit. No expiry
cache, new service or price snapshot is introduced. A trial per-event covering
index was rejected after measuring its write and space overhead.

The collector counts direct event inserts through cursor.rowcount because
Connection.total_changes also includes trigger maintenance. Supported event
writers use INSERT OR IGNORE, ordinary INSERT, UPDATE and DELETE. Do not bypass
the triggers or import events with arbitrary INSERT OR REPLACE/changed recursive
trigger settings. Historical replays remain subject to the identity limitations
described above.

Before rolling back to collector code that uses total_changes, stop collection
and remove only this derived table and its triggers in one transaction:

```sql
BEGIN IMMEDIATE;
DROP TRIGGER IF EXISTS event_options_insert;
DROP TRIGGER IF EXISTS event_options_update;
DROP TRIGGER IF EXISTS event_options_delete;
DROP TABLE IF EXISTS event_options;
COMMIT;
```

Then use the previous application code while keeping events, credentials,
bindings and prices. A later upgrade rebuilds event_options from the retained
events. This avoids inflating the old collector's counters with trigger writes.
The drop/rebuild/legacy-write path is regression tested on synthetic data; it has
not been executed on production.

Rollback keeps the extended event database and returns to the previous
application code, with the derived-table cleanup above if rolling back beyond
the trigger-aware collector. Old code tolerates the added nullable/defaulted
event columns. Restoring a pre-upgrade database would discard events collected
after the backup and is not the rollback strategy.
