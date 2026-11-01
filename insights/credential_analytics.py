"""Credential metadata and accounting for the existing single usage collector."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from pathlib import Path
from datetime import datetime, timezone


class CollectorAlreadyRunning(OSError):
    pass


class CollectorLease:
    """Prevent two processes from consuming into the same local database."""
    def __init__(self, database: Path):
        self.path = Path(str(database) + ".collector.lock")
        self.file = None

    def __enter__(self):
        self.file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0, 2)
                if not self.file.tell():
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            self.file = None
            raise CollectorAlreadyRunning("collector lock unavailable") from error
        return self

    def __exit__(self, *_):
        if self.file is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.file.seek(0)
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self.file.close()
                self.file = None


def utc_stamp(value: object) -> str:
    instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("timezone required")
    return instant.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def now_stamp() -> str:
    return utc_stamp(datetime.now(timezone.utc).isoformat())


def opaque_id(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        return None
    if re.search(r"(?i)(?:sk-|cpa-|bearer)", value):
        return None
    return value


def provider_name(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", value):
        return "unknown"
    if re.search(r"(?i)(sk-|cpa-|bearer)", value):
        return "unknown"
    return value.lower()


def strict_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10**12:
        raise ValueError("invalid token count")
    return value


def accounting(record: dict) -> dict:
    """Persist only a validated whitelist, never arbitrary upstream JSON."""
    result = {"token_quality": "legacy", "accounting_version": None,
              "token_breakdown": None, "accounted_input_tokens": None,
              "accounted_output_tokens": None, "accounted_total_tokens": None,
              "uncached_tokens": None, "cache_read_tokens": None,
              "cache_write_tokens": None, "non_reasoning_tokens": None,
              "accounted_reasoning_tokens": None, "unclassified_tokens": None}
    raw = record.get("token_breakdown")
    if raw is None and record.get("accounting_version") is None:
        return result
    result["token_quality"] = "inconsistent"
    if type(record.get("accounting_version")) is not int or record["accounting_version"] != 2 or not isinstance(raw, dict):
        return result
    try:
        if type(raw.get("schema_version")) is not int or raw["schema_version"] != 2 or raw.get("quality") not in (
                "complete", "inconsistent", "unclassified"):
            return result
        inp, out = raw["input"], raw["output"]
        clean = {"schema_version": 2, "quality": raw["quality"],
                 "total_tokens": strict_count(raw["total_tokens"]),
                 "unclassified_tokens": strict_count(raw["unclassified_tokens"]),
                 "input": {k: strict_count(inp[k]) for k in
                           ("total_tokens", "uncached_tokens", "cache_read_tokens", "cache_write_tokens")},
                 "output": {k: strict_count(out[k]) for k in
                            ("total_tokens", "non_reasoning_tokens", "reasoning_tokens")}}
        i, o = clean["input"], clean["output"]
        if (i["total_tokens"] != i["uncached_tokens"] + i["cache_read_tokens"] + i["cache_write_tokens"]
                or o["total_tokens"] != o["non_reasoning_tokens"] + o["reasoning_tokens"]
                or clean["total_tokens"] != i["total_tokens"] + o["total_tokens"] + clean["unclassified_tokens"]
                or (clean["quality"] == "complete" and clean["unclassified_tokens"] != 0)):
            return result
        result.update(token_quality=clean["quality"], accounting_version=2,
                      token_breakdown=json.dumps(clean, sort_keys=True, separators=(",", ":")),
                      accounted_input_tokens=i["total_tokens"], accounted_output_tokens=o["total_tokens"],
                      accounted_total_tokens=clean["total_tokens"], uncached_tokens=i["uncached_tokens"],
                      cache_read_tokens=i["cache_read_tokens"], cache_write_tokens=i["cache_write_tokens"],
                      non_reasoning_tokens=o["non_reasoning_tokens"],
                      accounted_reasoning_tokens=o["reasoning_tokens"],
                      unclassified_tokens=clean["unclassified_tokens"])
    except (KeyError, TypeError, ValueError):
        pass
    return result


def event_metadata(record: dict) -> dict:
    result = {"auth_index": opaque_id(record.get("auth_index")),
              "execution_id": opaque_id(record.get("execution_id")),
              "trace_id": opaque_id(record.get("trace_id")),
              "auth_type": provider_name(record.get("auth_type")),
              "stream": int(record["stream"]) if type(record.get("stream")) is bool else None,
              "executor_type": provider_name(record.get("executor_type")),
              "service_tier": provider_name(record.get("response_service_tier") or
                                            record.get("effective_service_tier") or
                                            record.get("service_tier") or "default"),
              "response_model": None, "event_schema": 2,
              "tokens_present": int(isinstance(record.get("tokens"), dict) and any(
                  type(record["tokens"].get(k)) is int and 0 <= record["tokens"][k] <= 10**12
                  for k in ("input_tokens", "output_tokens", "total_tokens")))}
    model = record.get("response_model")
    if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9_./:()-]{1,120}", model):
        result["response_model"] = model
    result.update(accounting(record))
    return result


EVENT_COLUMNS = {
    "instance_id": "TEXT", "credential_id": "TEXT", "binding_id": "TEXT",
    "association_state": "TEXT NOT NULL DEFAULT 'legacy'", "legacy_id": "TEXT",
    "event_schema": "INTEGER NOT NULL DEFAULT 1", "auth_index": "TEXT",
    "execution_id": "TEXT", "trace_id": "TEXT", "auth_type": "TEXT", "stream": "INTEGER",
    "executor_type": "TEXT", "service_tier": "TEXT", "response_model": "TEXT",
    "tokens_present": "INTEGER", "token_quality": "TEXT NOT NULL DEFAULT 'legacy'",
    "accounting_version": "INTEGER", "token_breakdown": "TEXT",
    **{k: "INTEGER" for k in ("accounted_input_tokens", "accounted_output_tokens", "accounted_total_tokens",
                             "uncached_tokens", "cache_read_tokens", "cache_write_tokens",
                             "non_reasoning_tokens", "accounted_reasoning_tokens", "unclassified_tokens")},
}


class CredentialStore:
    def migrate_credentials(self, db):
        columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
        for name, declaration in EVENT_COLUMNS.items():
            if name not in columns:
                db.execute(f"ALTER TABLE events ADD COLUMN {name} {declaration}")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS credentials (
              id TEXT PRIMARY KEY, instance_id TEXT NOT NULL, provider TEXT NOT NULL,
              auth_type TEXT NOT NULL, alias TEXT NOT NULL, group_name TEXT NOT NULL DEFAULT '',
              archived INTEGER NOT NULL DEFAULT 0, configured INTEGER NOT NULL DEFAULT 1,
              first_seen TEXT NOT NULL, last_seen TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS credential_bindings (
              id TEXT PRIMARY KEY, credential_id TEXT NOT NULL, instance_id TEXT NOT NULL,
              provider TEXT NOT NULL, auth_index TEXT NOT NULL, fingerprint TEXT NOT NULL,
              valid_from TEXT NOT NULL, valid_to TEXT, last_seen TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS binding_current
              ON credential_bindings(instance_id,provider,auth_index) WHERE valid_to IS NULL;
            CREATE INDEX IF NOT EXISTS binding_history
              ON credential_bindings(instance_id,provider,auth_index,valid_from);
            CREATE INDEX IF NOT EXISTS events_credential_time ON events(credential_id,timestamp);
            CREATE INDEX IF NOT EXISTS events_page ON events(timestamp DESC,id DESC);
            CREATE INDEX IF NOT EXISTS events_ttft ON events(credential_id,ttft_ms,timestamp)
              WHERE failed=0 AND stream=1 AND ttft_ms>0;
            CREATE INDEX IF NOT EXISTS events_latency ON events(credential_id,latency_ms,timestamp)
              WHERE latency_ms>0;
            CREATE UNIQUE INDEX IF NOT EXISTS events_execution
              ON events(instance_id,execution_id) WHERE execution_id IS NOT NULL;
        """)
        for key in ("instance_id", "credential_fingerprint_secret"):
            db.execute("INSERT OR IGNORE INTO meta(key,value) VALUES(?,?)", (key, str(uuid.uuid4())))
        self.instance_id = db.execute("SELECT value FROM meta WHERE key='instance_id'").fetchone()[0]

    def sync_credentials(self, payload: object, observed_at: str | None = None) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
            raise ValueError("invalid credential metadata")
        stamp = utc_stamp(observed_at) if observed_at is not None else now_stamp()
        files = payload["files"]
        if len(files) > 10000 or any(not isinstance(f, dict) for f in files):
            raise ValueError("invalid credential metadata")
        seen, prepared, missing = set(), [], 0
        for f in files:
            provider = provider_name(f.get("provider") or f.get("type"))
            index = opaque_id(f.get("auth_index") or f.get("auth-index"))
            if not index or provider == "unknown":
                missing += 1
                continue
            if (provider, index) in seen:
                raise ValueError("duplicate credential index")
            seen.add((provider, index))
            # Identity evidence is HMACed locally; paths, emails and tokens never leave this method.
            evidence = {k: str(f.get(k) or "")[:2048] for k in ("id", "name", "email", "account_id")}
            if not any(evidence.values()):
                missing += 1
                continue
            prepared.append((provider, index, provider_name(f.get("type")), evidence))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT value FROM meta WHERE key='credentials_observed_at'").fetchone()
            if previous and stamp <= previous[0]:
                return {"mapped": 0, "missing": missing, "stale": True}
            secret = db.execute("SELECT value FROM meta WHERE key='credential_fingerprint_secret'").fetchone()[0]
            # An incomplete metadata snapshot cannot safely mark absent credentials as removed.
            complete = missing == 0
            active_ids = []
            for provider, index, auth_type, evidence in prepared:
                fingerprint = hmac.new(secret.encode(), json.dumps(evidence, sort_keys=True).encode(), hashlib.sha256).hexdigest()
                binding = db.execute("""SELECT * FROM credential_bindings
                    WHERE instance_id=? AND provider=? AND auth_index=? AND valid_to IS NULL""",
                                     (self.instance_id, provider, index)).fetchone()
                if binding and binding["fingerprint"] != fingerprint:
                    # The replacement time is unknown between observations. Clear only that interval.
                    db.execute("UPDATE credential_bindings SET valid_to=? WHERE id=?", (binding["last_seen"], binding["id"]))
                    db.execute("""UPDATE events SET credential_id=NULL,binding_id=NULL,association_state='ambiguous'
                        WHERE binding_id=? AND timestamp>=?""", (binding["id"], binding["last_seen"]))
                    db.execute("UPDATE credentials SET configured=0 WHERE id=?", (binding["credential_id"],))
                    binding = None
                if binding:
                    cid = binding["credential_id"]
                    db.execute("UPDATE credential_bindings SET last_seen=? WHERE id=?", (stamp, binding["id"]))
                    db.execute("UPDATE credentials SET last_seen=?,configured=1 WHERE id=?", (stamp, cid))
                else:
                    cid, bid = str(uuid.uuid4()), str(uuid.uuid4())
                    ordinal = db.execute("SELECT COUNT(*) FROM credentials WHERE provider=?", (provider,)).fetchone()[0] + 1
                    db.execute("""INSERT INTO credentials(id,instance_id,provider,auth_type,alias,first_seen,last_seen)
                        VALUES(?,?,?,?,?,?,?)""", (cid, self.instance_id, provider, auth_type, f"{provider} {ordinal}", stamp, stamp))
                    db.execute("INSERT INTO credential_bindings VALUES(?,?,?,?,?,?,?,?,?)",
                               (bid, cid, self.instance_id, provider, index, fingerprint, stamp, None, stamp))
                active_ids.append(cid)
            if complete:
                current = db.execute("SELECT id,credential_id FROM credential_bindings WHERE valid_to IS NULL").fetchall()
                for b in current:
                    if b["credential_id"] not in active_ids:
                        db.execute("UPDATE credential_bindings SET valid_to=? WHERE id=?", (stamp, b["id"]))
                        db.execute("UPDATE credentials SET configured=0 WHERE id=?", (b["credential_id"],))
            db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('credentials_observed_at',?)", (stamp,))
        return {"mapped": len(prepared), "missing": missing, "stale": False}

    def associate(self, db, item: dict):
        item.update(instance_id=self.instance_id, credential_id=None, binding_id=None, association_state="unlinked")
        if not item["auth_index"]:
            return
        binding = db.execute("""SELECT id,credential_id FROM credential_bindings
            WHERE instance_id=? AND provider=? AND auth_index=? AND valid_from<=?
              AND (valid_to IS NULL OR ?<valid_to) ORDER BY valid_from DESC LIMIT 1""",
                             (self.instance_id, item["provider"], item["auth_index"], item["timestamp"], item["timestamp"])).fetchone()
        if binding:
            item.update(credential_id=binding["credential_id"], binding_id=binding["id"], association_state="observed")
        elif db.execute("""SELECT 1 FROM credential_bindings WHERE instance_id=? AND provider=?
            AND auth_index=? AND valid_to IS NOT NULL AND valid_to<=? LIMIT 1""",
                        (self.instance_id, item["provider"], item["auth_index"], item["timestamp"])).fetchone():
            item["association_state"] = "ambiguous"

    def _credential_rows(self, db, query: dict | None = None) -> list:
        query = query or {}
        clauses, args = ["instance_id=?"], [self.instance_id]
        for field in ("provider", "group_name"):
            if value := query.get(field):
                clauses.append(f"{field}=?")
                args.append(str(value)[:120])
        if query.get("search"):
            clauses.append("instr(lower(alias),lower(?))>0")
            args.append(str(query["search"])[:120])
        return [dict(r) for r in db.execute(f"""SELECT id,provider,auth_type,alias,group_name,
            archived,configured,first_seen,last_seen FROM credentials
            WHERE {' AND '.join(clauses)} ORDER BY archived,alias,id""", args)]

    def credentials(self, query: dict | None = None) -> list:
        with self.connect() as db:
            return self._credential_rows(db, query)

    def edit_credential(self, data: dict):
        if set(data) - {"id", "alias", "group_name", "archived"} or not opaque_id(data.get("id")):
            raise ValueError("invalid credential edit")
        fields = {}
        for k in ("alias", "group_name"):
            if k in data:
                value = data[k]
                if (not isinstance(value, str) or len(value) > 80 or (k == "alias" and not value.strip())
                        or any(ord(c) < 32 for c in value) or re.search(r"(?i)(sk-|cpa-|bearer\s)", value)):
                    raise ValueError("invalid credential label")
                fields[k] = value.strip()
        if "archived" in data:
            if type(data["archived"]) is not bool:
                raise ValueError("invalid archive flag")
            fields["archived"] = int(data["archived"])
        if not fields:
            raise ValueError("empty edit")
        with self.connect() as db:
            cursor = db.execute(f"UPDATE credentials SET {','.join(k+'=?' for k in fields)} WHERE id=? AND instance_id=?",
                                [*fields.values(), data["id"], self.instance_id])
            if not cursor.rowcount:
                raise ValueError("unknown credential")

    def credential_report(self, query: dict) -> dict:
        where, args = self.where(query)
        with self.connect() as db:
            db.execute("BEGIN")
            source = self.aggregate_source(db, query, args)
            credentials = self._credential_rows(db, query)
            rows = [dict(r) for r in db.execute(f"""SELECT e.credential_id, COUNT(*) requests,
                SUM(e.failed) failures, SUM({self.token_sql('total_tokens')}) total_tokens,
                SUM({self.cost_sql()}) estimated_cost, SUM({self.priceable_sql()}) priced_requests,
                SUM(e.token_quality='complete') accounted_requests,
                SUM(e.execution_id IS NOT NULL) execution_identified_requests,
                SUM(e.auth_index IS NOT NULL) indexed_requests,
                SUM(e.stream IS NOT NULL) stream_known_requests,
                SUM(e.event_schema=1) legacy_requests,
                SUM(e.association_state='ambiguous') ambiguous_requests,
                MAX(e.timestamp) last_used FROM events e {source}
                LEFT JOIN prices p ON p.model=e.model {self.price_rule_join()}
                WHERE {where} GROUP BY e.credential_id""", args)]
            metrics = {}
            for field, extra, prefix in (("ttft_ms", "AND e.failed=0 AND e.stream=1", "ttft"),
                                          ("latency_ms", "", "latency")):
                for r in db.execute(f"""WITH ranked AS (
                    SELECT e.credential_id,e.{field} value,
                      ROW_NUMBER() OVER (PARTITION BY e.credential_id ORDER BY e.{field}) rn,
                      COUNT(*) OVER (PARTITION BY e.credential_id ORDER BY e.{field}
                        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) n
                    FROM events e INDEXED BY events_{prefix} WHERE {where} AND e.{field}>0 {extra})
                    SELECT credential_id,MAX(n) samples,
                      MAX(CASE WHEN rn=CAST((n*50+99)/100 AS INTEGER) THEN value END) p50,
                      MAX(CASE WHEN rn=CAST((n*95+99)/100 AS INTEGER) THEN value END) p95
                    FROM ranked GROUP BY credential_id""", args):
                    metrics.setdefault(r["credential_id"], {}).update({prefix+"_samples": r["samples"],
                        prefix+"_p50_ms": r["p50"], prefix+"_p95_ms": r["p95"]})
        totals = {r["credential_id"]: r for r in rows}
        def stats(cid):
            result = {"requests": 0, "failures": 0, "total_tokens": 0, "estimated_cost": None,
                      "priced_requests": 0, "accounted_requests": 0, "ambiguous_requests": 0,
                      "execution_identified_requests": 0, "indexed_requests": 0,
                      "stream_known_requests": 0, "legacy_requests": 0,
                      "last_used": None, "ttft_samples": 0, "ttft_p50_ms": None, "ttft_p95_ms": None,
                      "latency_samples": 0, "latency_p50_ms": None, "latency_p95_ms": None}
            result.update(totals.get(cid, {}))
            result.pop("credential_id", None)
            result.update(metrics.get(cid, {}))
            result["success_rate"] = (result["requests"]-result["failures"])/result["requests"]*100 if result["requests"] else None
            return result
        if query.get("credential_id"):
            credentials = [c for c in credentials if c["id"] == query["credential_id"]]
        return {"credentials": [{**c, **stats(c["id"])} for c in credentials], "unlinked": stats(None),
                "count_basis": "upstream_executions", "ttft_basis": "cpa_with_first_packet_fallback",
                "price_basis": "current_rules_estimate"}
