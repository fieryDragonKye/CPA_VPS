"""Local CPA usage keeper. Python standard library only; no inference interception."""
from __future__ import annotations

import csv
from contextlib import contextmanager
import hashlib
import hmac
import io
import json
import math
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from credential_analytics import CredentialStore, CollectorAlreadyRunning, CollectorLease, event_metadata, now_stamp

ROOT = Path(__file__).resolve().parent.parent
API = "/v8/management/extensions/insights/"
QUEUE = "/v8/management/observability/usage/queue?count=500"
SAFE_ORIGINS = {f"http://{host}:{port}" for host in ("127.0.0.1", "localhost")
                for port in (8317, 8320, 5173)}
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def safe_label(value: object, maximum: int = 120) -> str:
    text = str(value or "unknown")[:maximum]
    text = re.sub(r"(?i)(?:bearer\s+|sk-|cpa-)[A-Za-z0-9_.-]{8,}", "[redacted]", text)
    if len(text) > 24 and re.fullmatch(r"[A-Za-z0-9_-]+", text) and not re.search(r"gpt|claude|gemini|codex|unknown", text, re.I):
        return "source-" + hashlib.sha256(text.encode()).hexdigest()[:8]
    return text


def positive(value: object) -> int:
    try:
        number = float(value)
        return min(10**12, max(0, int(number))) if math.isfinite(number) else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def nullable_ttft(value: object) -> float | None:
    # Zero is also the upstream sentinel for unavailable measurement.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if 0 < value <= 10**12 and math.isfinite(value) else None


def normalize(record: object) -> dict | None:
    if not isinstance(record, dict):
        return None
    try:
        instant = datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return None
        stamp = instant.astimezone(timezone.utc).isoformat(timespec="milliseconds")
    except (KeyError, TypeError, ValueError):
        return None
    tokens = record.get("tokens") or {}
    if not isinstance(tokens, dict):
        return None
    client = str(record.get("api_key") or "")
    source = str(record.get("source") or record.get("auth_index") or "unknown")
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", source):
        local, domain = source.rsplit("@", 1)
        source = local[:2] + "•••@" + domain
    elif source.startswith(("https://", "http://")):
        source = urllib.parse.urlsplit(source).hostname or "unknown"
    elif source.lower().endswith(".json"):
        source = re.split(r"[/\\]", source)[-1]
    else:
        source = "source-" + hashlib.sha256(source.encode()).hexdigest()[:8]
    item = {
        "timestamp": stamp,
        "model": safe_label(record.get("model")),
        "alias": safe_label(record.get("alias") or record.get("model")),
        "provider": safe_label(record.get("provider")),
        "source": safe_label(source),
        "client": "key-" + hashlib.sha256(client.encode()).hexdigest()[:8] if client else "unknown",
        "failed": int(bool(record.get("failed"))),
        "latency_ms": positive(record.get("latency_ms")),
        "input_tokens": positive(tokens.get("input_tokens")),
        "output_tokens": positive(tokens.get("output_tokens")),
        "reasoning_tokens": positive(tokens.get("reasoning_tokens")),
        "cached_tokens": positive(tokens.get("cached_tokens")),
        "endpoint": safe_label(str(record.get("endpoint") or "unknown").split("?", 1)[0]),
    }
    item["total_tokens"] = positive(tokens.get("total_tokens")) or item["input_tokens"] + item["output_tokens"]
    # Raw keys, upstream headers, prompts, responses and failure bodies are never persisted.
    identity = {**item, "request_id": str(record.get("request_id") or "")}
    item["id"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    # Keep the pre-migration event identity stable; timing is optional metadata.
    item["ttft_ms"] = nullable_ttft(record.get("ttft_ms"))
    item.update(event_metadata(record))
    return item


PRICE_PRESET = json.loads(
    Path(__file__).with_name("pricing.json").read_text(encoding="utf-8")
)


class Store(CredentialStore):
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS events (
                  id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, model TEXT, alias TEXT,
                  provider TEXT, source TEXT, client TEXT, failed INTEGER, latency_ms INTEGER,
                  input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER,
                  cached_tokens INTEGER, endpoint TEXT, total_tokens INTEGER);
                CREATE INDEX IF NOT EXISTS events_time ON events(timestamp);
                CREATE INDEX IF NOT EXISTS events_model_time ON events(model,timestamp);
                CREATE TABLE IF NOT EXISTS prices (
                  model TEXT PRIMARY KEY, input REAL NOT NULL, output REAL NOT NULL,
                  cache REAL NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS price_rules (
                  model TEXT PRIMARY KEY, basis TEXT NOT NULL,
                  input REAL NOT NULL, output REAL NOT NULL, cache REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            if "ttft_ms" not in columns:
                db.execute("ALTER TABLE events ADD COLUMN ttft_ms REAL")
            self.migrate_credentials(db)
            self.migrate_event_options(db)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, records: list) -> int:
        items = [item for record in records if (item := normalize(record))]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            inserted = 0
            for item in items:
                item["legacy_id"] = item["id"]
                self.associate(db, item)
                if item["execution_id"]:
                    identity = [self.instance_id, item["execution_id"]]
                    item["id"] = "v2-" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
                elif item["auth_index"]:
                    identity = [self.instance_id, item["legacy_id"], item["auth_index"]]
                    item["id"] = "v2-" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
                names = list(item)
                cursor = db.execute(f"INSERT OR IGNORE INTO events ({','.join(names)}) VALUES ({','.join('?' for _ in names)})", list(item.values()))
                # total_changes also counts the option-maintenance triggers.
                inserted += cursor.rowcount
            return inserted

    @staticmethod
    def migrate_event_options(db):
        fields = ("model", "provider", "source", "client")
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_options'").fetchone()
        db.execute("""CREATE TABLE IF NOT EXISTS event_options (
            field TEXT NOT NULL,is_null INTEGER NOT NULL,value TEXT NOT NULL,refs INTEGER NOT NULL CHECK(refs>=0),
            PRIMARY KEY(field,is_null,value)) WITHOUT ROWID""")
        if not exists:
            for field in fields:
                db.execute(f"""INSERT INTO event_options(field,is_null,value,refs)
                    SELECT ?,{field} IS NULL,COALESCE({field},''),COUNT(*)
                    FROM events GROUP BY {field}""", (field,))
        add = "\n".join(f"""INSERT INTO event_options(field,is_null,value,refs)
            VALUES('{f}',NEW.{f} IS NULL,COALESCE(NEW.{f},''),1)
            ON CONFLICT(field,is_null,value) DO UPDATE SET refs=refs+1;""" for f in fields)
        remove = "\n".join(f"""UPDATE event_options SET refs=refs-1
            WHERE field='{f}' AND is_null=(OLD.{f} IS NULL) AND value=COALESCE(OLD.{f},'');
            DELETE FROM event_options WHERE field='{f}' AND is_null=(OLD.{f} IS NULL)
              AND value=COALESCE(OLD.{f},'') AND refs=0;""" for f in fields)
        for name, event, body in (("insert", "INSERT", add), ("delete", "DELETE", remove),
                                  ("update", "UPDATE OF model,provider,source,client", remove+'\n'+add)):
            db.execute(f"CREATE TRIGGER IF NOT EXISTS event_options_{name} AFTER {event} ON events BEGIN {body} END")

    def where(self, query: dict) -> tuple[str, list]:
        hours = {"1h": 1, "5h": 5, "24h": 24, "7d": 168, "30d": 720}.get(query.get("range"), 24)
        start = datetime.fromtimestamp(time.time() - hours * 3600, timezone.utc).isoformat(timespec="milliseconds")
        clauses, args = ["e.timestamp >= ?"], [start]
        for field in ("model", "provider", "source", "client"):
            if value := query.get(field):
                clauses.append(f"e.{field} = ?")
                args.append(value[:160])
        if value := query.get("credential_id"):
            if value == "unlinked":
                clauses.append("e.credential_id IS NULL")
            else:
                clauses.append("e.credential_id=?")
                args.append(str(value)[:128])
        if value := query.get("group_name"):
            clauses.append("EXISTS (SELECT 1 FROM credentials c WHERE c.id=e.credential_id AND c.group_name=?)")
            args.append(str(value)[:80])
        if value := query.get("search"):
            clauses.append("EXISTS (SELECT 1 FROM credentials c WHERE c.id=e.credential_id AND instr(lower(c.alias),lower(?))>0)")
            args.append(str(value)[:120])
        if query.get("result") in ("success", "failed"):
            clauses.append("e.failed = ?")
            args.append(int(query["result"] == "failed"))
        return " AND ".join(clauses), args

    @staticmethod
    def price_rule_join() -> str:
        # Legacy writers can still use the original five-column prices table. If their
        # prices change, stale reference metadata must not keep applying a surcharge.
        return (
            "LEFT JOIN price_rules r ON r.model=p.model "
            "AND r.input=p.input AND r.output=p.output AND r.cache=p.cache"
        )

    @staticmethod
    def aggregate_index(query: dict) -> str:
        # The pagination index orders tied timestamps by hash, causing random table
        # reads on full aggregates. Keep aggregate scans on the smaller time index.
        if query.get("credential_id"):
            return "events_credential_time"
        if query.get("model"):
            return "events_model_time"
        return "events_time"

    @classmethod
    def aggregate_source(cls, db, query: dict, args: list) -> str:
        index = cls.aggregate_index(query)
        if index == "events_time":
            oldest = db.execute("SELECT MIN(timestamp) FROM events").fetchone()[0]
            # If the time predicate excludes nothing, a time-index traversal
            # just adds rowid lookups. Scan the table once in storage order.
            if oldest is not None and oldest >= args[0]:
                return "NOT INDEXED"
        return f"INDEXED BY {index}"

    @staticmethod
    def token_sql(field: str) -> str:
        canonical = {"input_tokens": "accounted_input_tokens", "output_tokens": "accounted_output_tokens",
                     "total_tokens": "accounted_total_tokens", "reasoning_tokens": "accounted_reasoning_tokens",
                     "cached_tokens": "cache_read_tokens"}[field]
        condition = "e.token_quality='complete'"
        if field == "total_tokens":
            condition = "e.accounting_version=2 AND e.token_breakdown IS NOT NULL"
        return f"(CASE WHEN {condition} THEN e.{canonical} ELSE e.{field} END)"

    @staticmethod
    def priceable_sql() -> str:
        return """(p.model IS NOT NULL AND (e.event_schema=1 OR (
            (e.response_model IS NULL OR e.response_model=e.model)
            AND e.service_tier IN ('default','standard') AND (
              (e.token_quality='legacy' AND e.tokens_present=1 AND e.provider IN ('codex','openai','openai-compatibility'))
              OR (e.token_quality='complete' AND e.cache_write_tokens=0)))))"""

    @staticmethod
    def long_context_sql() -> str:
        return f"({Store.priceable_sql()} AND r.basis='{PRICE_PRESET['id']}' AND {Store.token_sql('input_tokens')}>{PRICE_PRESET['long_context_threshold']})"

    @staticmethod
    def cost_sql() -> str:
        long = Store.long_context_sql()
        input_factor = f"(CASE WHEN {long} THEN {PRICE_PRESET['long_input_multiplier']} ELSE 1 END)"
        output_factor = f"(CASE WHEN {long} THEN {PRICE_PRESET['long_output_multiplier']} ELSE 1 END)"
        inp, out = Store.token_sql("input_tokens"), Store.token_sql("output_tokens")
        uncached = f"(CASE WHEN e.token_quality='complete' THEN e.uncached_tokens ELSE MAX({inp}-MIN(e.cached_tokens,{inp}),0) END)"
        cache = f"(CASE WHEN e.token_quality='complete' THEN e.cache_read_tokens ELSE MIN(e.cached_tokens,{inp}) END)"
        return f"(CASE WHEN {Store.priceable_sql()} THEN (({uncached}*p.input + {cache}*p.cache)*{input_factor} + {out}*p.output*{output_factor})/1000000.0 END)"

    def summary(self, query: dict) -> dict:
        where, args = self.where(query)
        with self.connect() as db:
            db.execute("BEGIN")
            source = self.aggregate_source(db, query, args)
            # Materialize only the numeric/model/hour projection for this read
            # snapshot. Prices remain query-time estimates, never a stale cache.
            hint = "MATERIALIZED " if sqlite3.sqlite_version_info >= (3, 35, 0) else ""
            grouped = [dict(r) for r in db.execute(f"""WITH filtered AS {hint}(
                SELECT e.model,substr(e.timestamp,1,13)||':00:00+00:00' hour,e.failed,e.latency_ms,
                  {self.token_sql('input_tokens')} input_tokens,{self.token_sql('output_tokens')} output_tokens,
                  {self.token_sql('reasoning_tokens')} reasoning_tokens,{self.token_sql('cached_tokens')} cached_tokens,
                  {self.token_sql('total_tokens')} total_tokens,{self.cost_sql()} estimated_cost,
                  {self.priceable_sql()} priced
                FROM events e {source} LEFT JOIN prices p ON p.model=e.model
                  {self.price_rule_join()} WHERE {where}),
              top_models AS (
                SELECT model,COUNT(*) requests,SUM(failed) failures,SUM(total_tokens) total_tokens
                FROM filtered GROUP BY model ORDER BY total_tokens DESC LIMIT 12)
              SELECT 'total' kind,NULL bucket,COUNT(*) requests,COALESCE(SUM(failed),0) failures,
                COALESCE(SUM(input_tokens),0) input_tokens,COALESCE(SUM(output_tokens),0) output_tokens,
                COALESCE(SUM(reasoning_tokens),0) reasoning_tokens,COALESCE(SUM(cached_tokens),0) cached_tokens,
                COALESCE(SUM(total_tokens),0) total_tokens,AVG(latency_ms) latency_ms,
                SUM(estimated_cost) estimated_cost,COALESCE(SUM(priced),0) priced_requests
              FROM filtered
              UNION ALL SELECT 'trend',hour,COUNT(*),SUM(failed),NULL,NULL,NULL,NULL,
                SUM(total_tokens),NULL,NULL,NULL FROM filtered GROUP BY hour
              UNION ALL SELECT 'model',model,requests,failures,NULL,NULL,NULL,NULL,
                total_tokens,NULL,NULL,NULL FROM top_models""", args)]
            row = {k: v for k, v in grouped[0].items() if k not in ("kind", "bucket")}
            row["success_rate"] = (row["requests"] - row["failures"]) / row["requests"] * 100 if row["requests"] else None
            # Local date grouping is done by the browser; buckets are UTC and unambiguous.
            row["trend"] = sorted([{"timestamp": r["bucket"], "requests": r["requests"],
                "failures": r["failures"], "total_tokens": r["total_tokens"]}
                for r in grouped if r["kind"] == "trend"], key=lambda r: r["timestamp"])
            row["models"] = [{"model": r["bucket"], "requests": r["requests"],
                "total_tokens": r["total_tokens"], "failures": r["failures"]}
                for r in grouped if r["kind"] == "model"]
            row["options"] = {field: [r[0] for r in db.execute("""SELECT CASE WHEN is_null THEN NULL ELSE value END
                                FROM event_options WHERE field=? ORDER BY is_null DESC,value LIMIT 500""", (field,))]
                              for field in ("model", "provider", "source", "client")}
            row["stored_records"] = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            row["first_record"] = db.execute("SELECT MIN(timestamp) FROM events").fetchone()[0]
        row["database_bytes"] = self.path.stat().st_size
        return row

    def events(self, query: dict, export: bool = False) -> dict:
        where, args = self.where(query)
        page = max(1, min(positive(query.get("page", 1)), 100000))
        size = 10000 if export else 25
        with self.connect() as db:
            db.execute("BEGIN")
            count = db.execute(f"SELECT COUNT(*) FROM events e WHERE {where}", args).fetchone()[0]
            rows = [dict(r) for r in db.execute(f"""SELECT e.timestamp,e.model,e.alias,e.provider,e.source,e.client,e.failed,
              e.latency_ms,e.ttft_ms,{self.token_sql('input_tokens')} input_tokens,{self.token_sql('output_tokens')} output_tokens,
              {self.token_sql('reasoning_tokens')} reasoning_tokens,{self.token_sql('cached_tokens')} cached_tokens,
              {self.token_sql('total_tokens')} total_tokens,e.endpoint,
              e.credential_id,e.association_state,e.event_schema,e.stream,e.token_quality,
              e.cache_write_tokens,e.unclassified_tokens,e.service_tier,e.response_model,
              {self.cost_sql()} estimated_cost, CASE WHEN {self.priceable_sql()} THEN COALESCE(r.basis,'manual') END pricing_basis,
              CASE WHEN {self.long_context_sql()} THEN 1 ELSE 0 END long_context_applied
              FROM events e LEFT JOIN prices p ON p.model=e.model {self.price_rule_join()}
              WHERE {where} ORDER BY e.timestamp DESC,e.id DESC LIMIT ? OFFSET ?""", [*args, size, 0 if export else (page - 1) * size])]
        return {"rows": rows, "total": count, "page": page, "page_size": size}

    def prices(self) -> list:
        with self.connect() as db:
            rows = [
                dict(r) for r in db.execute(
                    f"SELECT p.*,COALESCE(r.basis,'manual') basis FROM prices p {self.price_rule_join()} ORDER BY p.model"
                )
            ]
        sources = {p["model"]: p for p in PRICE_PRESET["models"]}
        for row in rows:
            if row["basis"] == PRICE_PRESET["id"] and row["model"] in sources:
                row.update(
                    source_url=sources[row["model"]]["source_url"],
                    verified_at=PRICE_PRESET["verified_at"],
                )
        return rows

    def import_price_preset(self, preset: str) -> int:
        if preset != PRICE_PRESET["id"]:
            raise ValueError("unknown preset")
        with self.connect() as db:
            imported = 0
            for row in PRICE_PRESET["models"]:
                cursor = db.execute(
                    "INSERT OR IGNORE INTO prices(model,input,output,cache,updated) VALUES(?,?,?,?,?)",
                    [
                        row["model"], row["input"], row["output"], row["cache"],
                        datetime.now(timezone.utc).isoformat(),
                    ],
                )
                if cursor.rowcount:
                    db.execute(
                        "INSERT OR REPLACE INTO price_rules VALUES(?,?,?,?,?)",
                        [row["model"], preset, row["input"], row["output"], row["cache"]],
                    )
                    imported += 1
            return imported

    def save_price(self, data: dict):
        model = str(data.get("model") or "").strip()
        if not model or len(model) > 120 or not re.fullmatch(r"[A-Za-z0-9_./:()-]+", model):
            raise ValueError("invalid model")
        prices = [float(data[k]) for k in ("input", "output", "cache")]
        if any(not math.isfinite(p) or p < 0 or p > 100000 for p in prices):
            raise ValueError("invalid price")
        basis = data.get("basis") or "manual"
        if basis not in ("manual", PRICE_PRESET["id"]):
            raise ValueError("invalid pricing basis")
        if basis == PRICE_PRESET["id"]:
            official = next((p for p in PRICE_PRESET["models"] if p["model"] == model), None)
            if not official or prices != [official[k] for k in ("input", "output", "cache")]:
                raise ValueError("official rates changed; save as manual")
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO prices(model,input,output,cache,updated) VALUES (?,?,?,?,?)",
                [model, *prices, datetime.now(timezone.utc).isoformat()],
            )
            db.execute("DELETE FROM price_rules WHERE model=?", [model])
            if basis == PRICE_PRESET["id"]:
                db.execute("INSERT INTO price_rules VALUES(?,?,?,?,?)", [model, basis, *prices])

    def prune(self):
        with self.connect() as db:
            db.execute("DELETE FROM events WHERE timestamp < ?", [datetime.fromtimestamp(time.time()-90*86400, timezone.utc).isoformat()])
            count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            if count > 250000:
                db.execute("DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY timestamp LIMIT ?)", [count - 250000])


class Keeper:
    def __init__(self, store: Store, key: str, cpa_url: str):
        self.store, self.key, self.cpa_url = store, key, cpa_url
        self.state = "connecting"
        self.last_collected = None
        self.last_error = None
        self.collected = 0
        self.last_poll = None
        self.last_received = None
        self.metadata_error = None
        self.metadata_coverage = None
        self.rejected = 0
        self.duplicates = 0
        self.pending_count = 0
        self.stop = threading.Event()

    def request(self, path: str):
        req = urllib.request.Request(self.cpa_url + path, headers={"Authorization": "Bearer " + self.key})
        with NO_PROXY.open(req, timeout=12) as response:
            return json.load(response)

    def run(self):
        lease = CollectorLease(self.store.path)
        try:
            lease.__enter__()
        except CollectorAlreadyRunning:
            self.state, self.last_error = "waiting", "collector_already_running"
            return
        except OSError:
            self.state, self.last_error = "waiting", "storage_unavailable"
            return
        try:
            self._run()
        finally:
            lease.__exit__()

    def _run(self):
        housekeeping = 0.0
        last_config_check = 0.0
        last_metadata_check = 0.0
        pending = None
        while not self.stop.is_set():
            try:
                if pending is None:
                    config = self.request("/v8/management/config") if self.state != "running" or time.time() - last_config_check > 30 else None
                    if config is not None:
                        last_config_check = time.time()
                    if config is not None and not config.get("observability", {}).get("usage", {}).get("usage-statistics-enabled", False):
                        self.state, self.last_error = "disabled", "statistics_disabled"
                        self.stop.wait(10)
                        continue
                    if time.time() - last_metadata_check > 30:
                        try:
                            metadata = self.request("/v8/management/credentials")
                            self.metadata_coverage = self.store.sync_credentials(metadata)
                            self.metadata_error = None
                        except urllib.error.HTTPError as error:
                            if error.code in (401, 403):
                                raise
                            self.metadata_error = f"http_{error.code}"
                        except (ValueError, TypeError):
                            self.metadata_error = "invalid_metadata"
                        except urllib.error.URLError:
                            self.metadata_error = "metadata_unavailable"
                        last_metadata_check = time.time()
                    records = self.request(QUEUE)
                    if not isinstance(records, list):
                        raise ValueError("invalid usage queue")
                    self.last_poll = now_stamp()
                    if records:
                        self.last_received = self.last_poll
                    pending = records
                    self.pending_count = len(pending)
                count = self.store.ingest(pending)
                accepted = sum(normalize(record) is not None for record in pending)
                self.rejected += len(pending) - accepted
                self.duplicates += accepted - count
                pending = None
                self.pending_count = 0
                self.collected += count
                if count:
                    self.last_collected = datetime.now(timezone.utc).isoformat()
                self.state, self.last_error = "running", None
                if time.time() - housekeeping > 3600:
                    self.store.prune()
                    housekeeping = time.time()
                self.stop.wait(3)
            except urllib.error.HTTPError as error:
                self.state, self.last_error = "waiting", f"http_{error.code}"
                # A rejected management key must not repeatedly trigger CPA's IP ban.
                if error.code in (401, 403):
                    return
                self.stop.wait(10)
            except sqlite3.Error:
                self.state, self.last_error = "waiting", "storage_unavailable"
                self.stop.wait(10)
            except ValueError:
                self.state, self.last_error = "waiting", "invalid_queue_payload"
                self.stop.wait(10)
            except Exception:
                self.state, self.last_error = "waiting", "cpa_unavailable"
                self.stop.wait(10)

    def status(self) -> dict:
        return {"state": self.state, "last_collected": self.last_collected,
                "last_error": self.last_error, "collected_this_run": self.collected,
                "last_poll": self.last_poll, "last_received": self.last_received,
                "metadata_error": self.metadata_error, "metadata_coverage": self.metadata_coverage,
                "rejected_this_run": self.rejected, "duplicates_this_run": self.duplicates,
                "pending_count": self.pending_count,
                "retention_days": 90, "record_limit": 250000, "mode": "http_queue"}


def make_handler(keeper: Keeper, page: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CPAInsights/1.0"

        def log_message(self, *_args):
            pass  # Do not log URLs, bearer headers or request payloads.

        def origin_ok(self):
            origin = self.headers.get("Origin")
            return not origin or origin in SAFE_ORIGINS

        def headers_for(self, code: int, content_type="application/json; charset=utf-8", length=0):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            if (origin := self.headers.get("Origin")) in SAFE_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()

        def respond(self, data, code=200):
            body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            self.headers_for(code, length=len(body))
            self.wfile.write(body)

        def authorized(self):
            supplied = self.headers.get("Authorization", "")
            return hmac.compare_digest(supplied.encode(), ("Bearer " + keeper.key).encode())

        def do_OPTIONS(self):
            if not self.origin_ok():
                return self.respond({"error": "origin_not_allowed"}, 403)
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "http://127.0.0.1:8320"))
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if not self.origin_ok():
                return self.respond({"error": "origin_not_allowed"}, 403)
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path in ("/", "/management.html", "/index.html", "/preview.html"):
                selected_page = ROOT / "web/dist/index.html" if parsed.path == "/preview.html" else page
                if not selected_page.is_file():
                    return self.respond({"error": "build_frontend_first"}, 503)
                body = selected_page.read_bytes()
                self.headers_for(200, "text/html; charset=utf-8", len(body))
                return self.wfile.write(body)
            if parsed.path.startswith(API):
                if not self.authorized():
                    return self.respond({"error": "unauthorized"}, 401)
                route = parsed.path.removeprefix(API)
                query = dict(urllib.parse.parse_qsl(parsed.query))
                if route == "status":
                    return self.respond(keeper.status())
                if route == "summary":
                    return self.respond(keeper.store.summary(query))
                if route == "events":
                    return self.respond(keeper.store.events(query))
                if route == "credentials":
                    return self.respond(keeper.store.credentials(query))
                if route == "credentials/summary":
                    return self.respond(keeper.store.credential_report(query))
                if route == "prices":
                    return self.respond(keeper.store.prices())
                if route == "pricing-preset":
                    return self.respond(PRICE_PRESET)
                if route == "export":
                    records = keeper.store.events(query, export=True)
                    output = io.StringIO()
                    fields = ["timestamp", "model", "provider", "source", "client", "failed", "latency_ms", "ttft_ms", "input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens", "total_tokens", "estimated_cost", "pricing_basis", "long_context_applied", "credential_id", "association_state", "event_schema", "stream", "token_quality", "cache_write_tokens", "unclassified_tokens"]
                    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
                    writer.writeheader()
                    for row in records["rows"]:
                        writer.writerow({k: ("'" + str(v) if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v) for k, v in row.items()})
                    body = output.getvalue().encode("utf-8-sig")
                    self.headers_for(200, "text/csv; charset=utf-8", len(body))
                    return self.wfile.write(body)
                return self.respond({"error": "not_found"}, 404)
            if parsed.path.startswith("/v8/management/") or parsed.path == "/v1/models":
                return self.proxy()
            return self.respond({"error": "not_found"}, 404)

        def do_POST(self):
            if not self.origin_ok():
                return self.respond({"error": "origin_not_allowed"}, 403)
            if self.path in (API + "prices", API + "prices/import", API + "credentials/edit"):
                if not self.authorized():
                    return self.respond({"error": "unauthorized"}, 401)
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size > 4096 or size <= 0:
                        raise ValueError("invalid size")
                    data = json.loads(self.rfile.read(size))
                    if not isinstance(data, dict):
                        raise ValueError('expected object')
                    if self.path == API + 'credentials/edit':
                        keeper.store.edit_credential(data)
                        return self.respond({"saved": True})
                    if self.path == API + 'prices/import':
                        return self.respond({'saved': True, 'imported': keeper.store.import_price_preset(data.get('preset'))})
                    keeper.store.save_price(data)
                    return self.respond({"saved": True})
                except (ValueError, KeyError, TypeError):
                    return self.respond({"error": "invalid_credential" if self.path == API + 'credentials/edit' else "invalid_price"}, 400)
            return self.proxy()

        def do_PUT(self):
            self.proxy()

        def do_PATCH(self):
            self.proxy()

        def do_DELETE(self):
            self.proxy()

        def proxy(self):
            if not self.origin_ok():
                return self.respond({"error": "origin_not_allowed"}, 403)
            path = urllib.parse.urlsplit(self.path).path
            if not path.startswith("/v8/management/") and path != "/v1/models":
                return self.respond({"error": "not_found"}, 404)
            if path.startswith(API):
                return self.respond({"error": "method_not_allowed"}, 405)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size > 16 * 1024 * 1024:
                    return self.respond({"error": "body_too_large"}, 413)
                body = self.rfile.read(size) if size else None
                headers = {k: v for k, v in self.headers.items() if k.lower() in ("authorization", "content-type", "accept")}
                req = urllib.request.Request(keeper.cpa_url + self.path, data=body, headers=headers, method=self.command)
                try:
                    response = NO_PROXY.open(req, timeout=60)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    payload = response.read()
                    self.send_response(response.status)
                    for key, value in response.headers.items():
                        if key.lower() not in ("connection", "transfer-encoding", "content-length", "access-control-allow-origin", "content-encoding"):
                            self.send_header(key, value)
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(payload)
            except Exception:
                self.respond({"error": "cpa_unavailable"}, 502)

    return Handler
