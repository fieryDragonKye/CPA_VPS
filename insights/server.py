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
    return item


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
            if "ttft_ms" not in columns:
                db.execute("ALTER TABLE events ADD COLUMN ttft_ms REAL")

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
            before = db.total_changes
            for item in items:
                names = list(item)
                db.execute(f"INSERT OR IGNORE INTO events ({','.join(names)}) VALUES ({','.join('?' for _ in names)})", list(item.values()))
            return db.total_changes - before

    def where(self, query: dict) -> tuple[str, list]:
        hours = {"1h": 1, "5h": 5, "24h": 24, "7d": 168, "30d": 720}.get(query.get("range"), 24)
        start = datetime.fromtimestamp(time.time() - hours * 3600, timezone.utc).isoformat(timespec="milliseconds")
        clauses, args = ["e.timestamp >= ?"], [start]
        for field in ("model", "provider", "source", "client"):
            if value := query.get(field):
                clauses.append(f"e.{field} = ?")
                args.append(value[:160])
        if query.get("result") in ("success", "failed"):
            clauses.append("e.failed = ?")
            args.append(int(query["result"] == "failed"))
        return " AND ".join(clauses), args

    @staticmethod
    def cost_sql() -> str:
        return "(MAX(e.input_tokens - MIN(e.cached_tokens,e.input_tokens),0)*p.input + e.output_tokens*p.output + MIN(e.cached_tokens,e.input_tokens)*p.cache)/1000000.0"

    def summary(self, query: dict) -> dict:
        where, args = self.where(query)
        with self.connect() as db:
            row = dict(db.execute(f"""SELECT COUNT(*) requests, COALESCE(SUM(e.failed),0) failures,
              COALESCE(SUM(e.input_tokens),0) input_tokens, COALESCE(SUM(e.output_tokens),0) output_tokens,
              COALESCE(SUM(e.reasoning_tokens),0) reasoning_tokens, COALESCE(SUM(e.cached_tokens),0) cached_tokens,
              COALESCE(SUM(e.total_tokens),0) total_tokens, AVG(e.latency_ms) latency_ms,
              SUM({self.cost_sql()}) estimated_cost, COUNT(p.model) priced_requests
              FROM events e LEFT JOIN prices p ON p.model=e.model WHERE {where}""", args).fetchone())
            row["success_rate"] = (row["requests"] - row["failures"]) / row["requests"] * 100 if row["requests"] else None
            # Local date grouping is done by the browser; buckets are UTC and unambiguous.
            row["trend"] = [dict(r) for r in db.execute(f"""SELECT substr(e.timestamp,1,13)||':00:00+00:00' timestamp,
              COUNT(*) requests, SUM(e.failed) failures, SUM(e.total_tokens) total_tokens
              FROM events e WHERE {where} GROUP BY substr(e.timestamp,1,13) ORDER BY timestamp""", args)]
            row["models"] = [dict(r) for r in db.execute(f"""SELECT e.model, COUNT(*) requests,
              SUM(e.total_tokens) total_tokens, SUM(e.failed) failures
              FROM events e WHERE {where} GROUP BY e.model ORDER BY total_tokens DESC LIMIT 12""", args)]
            row["options"] = {field: [r[0] for r in db.execute(f"SELECT DISTINCT {field} FROM events ORDER BY {field} LIMIT 500")]
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
            count = db.execute(f"SELECT COUNT(*) FROM events e WHERE {where}", args).fetchone()[0]
            rows = [dict(r) for r in db.execute(f"""SELECT e.timestamp,e.model,e.alias,e.provider,e.source,e.client,e.failed,
              e.latency_ms,e.ttft_ms,e.input_tokens,e.output_tokens,e.reasoning_tokens,e.cached_tokens,e.total_tokens,e.endpoint,
              {self.cost_sql()} estimated_cost FROM events e LEFT JOIN prices p ON p.model=e.model
              WHERE {where} ORDER BY e.timestamp DESC,e.id DESC LIMIT ? OFFSET ?""", [*args, size, 0 if export else (page - 1) * size])]
        return {"rows": rows, "total": count, "page": page, "page_size": size}

    def prices(self) -> list:
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM prices ORDER BY model")]

    def save_price(self, data: dict):
        model = str(data.get("model") or "").strip()
        if not model or len(model) > 120 or not re.fullmatch(r"[A-Za-z0-9_./:()-]+", model):
            raise ValueError("invalid model")
        prices = [float(data[k]) for k in ("input", "output", "cache")]
        if any(not math.isfinite(p) or p < 0 or p > 100000 for p in prices):
            raise ValueError("invalid price")
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?)", [model, *prices, datetime.now(timezone.utc).isoformat()])

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
        self.stop = threading.Event()

    def request(self, path: str):
        req = urllib.request.Request(self.cpa_url + path, headers={"Authorization": "Bearer " + self.key})
        with NO_PROXY.open(req, timeout=12) as response:
            return json.load(response)

    def run(self):
        housekeeping = 0.0
        last_config_check = 0.0
        while not self.stop.is_set():
            try:
                config = self.request("/v8/management/config") if self.state != "running" or time.time() - last_config_check > 30 else None
                if config is not None:
                    last_config_check = time.time()
                if config is not None and not config.get("observability", {}).get("usage", {}).get("usage-statistics-enabled", False):
                    self.state, self.last_error = "disabled", "statistics_disabled"
                    self.stop.wait(10)
                    continue
                records = self.request(QUEUE)
                if not isinstance(records, list):
                    raise ValueError("invalid usage queue")
                count = self.store.ingest(records)
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
            except Exception:
                self.state, self.last_error = "waiting", "cpa_unavailable"
                self.stop.wait(10)

    def status(self) -> dict:
        return {"state": self.state, "last_collected": self.last_collected,
                "last_error": self.last_error, "collected_this_run": self.collected,
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
                if route == "prices":
                    return self.respond(keeper.store.prices())
                if route == "export":
                    records = keeper.store.events(query, export=True)
                    output = io.StringIO()
                    fields = ["timestamp", "model", "provider", "source", "client", "failed", "latency_ms", "ttft_ms", "input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens", "total_tokens", "estimated_cost"]
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
            if self.path == API + "prices":
                if not self.authorized():
                    return self.respond({"error": "unauthorized"}, 401)
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size > 4096 or size <= 0:
                        raise ValueError("invalid size")
                    keeper.store.save_price(json.loads(self.rfile.read(size)))
                    return self.respond({"saved": True})
                except (ValueError, KeyError, TypeError):
                    return self.respond({"error": "invalid_price"}, 400)
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
