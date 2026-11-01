"""Isolated credential/accounting regressions; no production endpoints or data."""
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from credential_analytics import CollectorLease, accounting, utc_stamp
from server import API, QUEUE, Keeper, Store, make_handler
from test_server import event


def breakdown(uncached=600, read=400, write=0, ordinary=300, reasoning=200):
    inp, out = uncached + read + write, ordinary + reasoning
    return {"schema_version": 2, "quality": "complete", "total_tokens": inp + out,
            "unclassified_tokens": 0,
            "input": {"total_tokens": inp, "uncached_tokens": uncached,
                      "cache_read_tokens": read, "cache_write_tokens": write},
            "output": {"total_tokens": out, "non_reasoning_tokens": ordinary,
                       "reasoning_tokens": reasoning}}


def metadata(index="0000000000000001", email="private-person@example.invalid", provider="codex"):
    return {"provider": provider, "type": provider, "auth_index": index,
            "id": "/private/auths/account.json", "name": "account.json", "email": email}


class CredentialFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "usage.sqlite"
        self.store = Store(self.path)
        self.start = datetime.now(timezone.utc) - timedelta(hours=1)

    def tearDown(self):
        self.temp.cleanup()

    def at(self, minutes):
        return utc_stamp((self.start + timedelta(minutes=minutes)).isoformat())

    def sync(self, files=None, minute=0):
        return self.store.sync_credentials({"files": [metadata()] if files is None else files}, self.at(minute))

    def record(self, execution="attempt-1", minute=1, **overrides):
        data = dict(timestamp=self.at(minute), auth_index="0000000000000001",
                    execution_id=execution, stream=True, accounting_version=2,
                    token_breakdown=breakdown())
        data.update(overrides)
        return event(**data)


class CredentialTests(CredentialFixture):
    def test_real_legacy_schema_and_prior_cost_survive_repeated_migration(self):
        path = Path(self.temp.name) / "legacy.sqlite"
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE events (
                id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, model TEXT, alias TEXT,
                provider TEXT, source TEXT, client TEXT, failed INTEGER, latency_ms INTEGER,
                input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER,
                cached_tokens INTEGER, endpoint TEXT, total_tokens INTEGER)""")
            db.execute("""INSERT INTO events(id,timestamp,model,provider,failed,input_tokens,
                output_tokens,reasoning_tokens,cached_tokens,total_tokens)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", ("legacy-id", self.at(1), "test-model", "freetier", 0, 100, 50, 10, 20, 150))
        db.close()
        for _ in range(2):
            store = Store(path)
            store.save_price({"model": "test-model", "input": 1, "output": 1, "cache": 1})
            self.assertAlmostEqual(store.summary({})["estimated_cost"], 150/1e6)
            with store.connect() as db:
                row = dict(db.execute("SELECT * FROM events").fetchone())
                self.assertEqual((row["id"], row["event_schema"], row["association_state"]), ("legacy-id", 1, "legacy"))
                self.assertIsNone(row["credential_id"])
            self.assertEqual(store.credential_report({})["unlinked"]["legacy_requests"], 1)


    def test_instance_survives_restart_and_legacy_history_is_immutable(self):
        record = event(timestamp=self.at(1))
        self.store.ingest([record])
        with self.store.connect() as db:
            before = tuple(db.execute("SELECT id,timestamp,source,total_tokens FROM events").fetchone())
        instance = self.store.instance_id
        for _ in range(2):
            self.store = Store(self.path)
            self.assertEqual(self.store.instance_id, instance)
        self.sync()
        with self.store.connect() as db:
            self.assertEqual(tuple(db.execute("SELECT id,timestamp,source,total_tokens FROM events").fetchone()), before)
            self.assertIsNone(db.execute("SELECT credential_id FROM events").fetchone()[0])
        self.assertEqual(self.store.credential_report({})["unlinked"]["requests"], 1)

    def test_execution_identity_dedups_replay_without_collapsing_two_attempts(self):
        self.sync()
        a, b = self.record(), self.record("attempt-2")
        self.assertEqual(self.store.ingest([a, a, b]), 2)
        self.assertEqual(self.store.ingest([a, b]), 0)
        report = self.store.credential_report({})
        self.assertEqual(report["credentials"][0]["requests"], 2)
        self.assertEqual(report["unlinked"]["requests"], 0)

    def test_same_domain_keys_remain_separate_and_unknown_index_is_unlinked(self):
        other = metadata("0000000000000002")
        self.sync([metadata(), other])
        a = self.record(source="https://example.invalid/first")
        b = self.record("attempt-2", source="https://example.invalid/second")
        b["auth_index"] = other["auth_index"]
        c = self.record("attempt-3")
        c["auth_index"] = "unknown-index"
        self.store.ingest([a, b, c])
        report = self.store.credential_report({})
        self.assertEqual(sorted(r["requests"] for r in report["credentials"]), [1, 1])
        self.assertEqual(report["unlinked"]["requests"], 1)
        self.assertEqual(self.store.summary({})["requests"], 3)

    def test_replace_same_path_marks_observation_gap_and_keeps_known_history(self):
        self.sync(minute=0)
        old = self.store.credentials()[0]["id"]
        self.sync(minute=10)
        self.store.ingest([self.record("known-old", minute=5), self.record("uncertain", minute=15)])
        self.sync([metadata(email="replacement@example.invalid")], minute=20)
        self.store.ingest([self.record("new", minute=21)])
        records = {r["timestamp"]: r for r in self.store.events({})["rows"]}
        self.assertEqual(records[self.at(5)]["credential_id"], old)
        self.assertEqual(records[self.at(15)]["association_state"], "ambiguous")
        self.assertIsNone(records[self.at(15)]["credential_id"])
        self.assertNotEqual(records[self.at(21)]["credential_id"], old)
        self.assertEqual(len(self.store.credentials()), 2)
        # A delayed event in the gap must remain ambiguous too.
        self.store.ingest([self.record("delayed-gap", minute=18)])
        self.assertEqual(self.store.credential_report({})["unlinked"]["ambiguous_requests"], 2)

    def test_no_backfill_before_first_observation_or_after_rename(self):
        self.store.ingest([self.record(minute=1)])
        self.sync(minute=2)
        self.assertEqual(self.store.credential_report({})["unlinked"]["requests"], 1)
        renamed = metadata()
        renamed.update(id="/new/path/account.json", name="renamed.json", auth_index="0000000000000002")
        self.sync([renamed], minute=5)
        self.assertEqual(len(self.store.credentials()), 2)

    def test_alias_group_archive_do_not_change_binding_or_event_attribution(self):
        self.sync()
        cid = self.store.credentials()[0]["id"]
        self.store.ingest([self.record()])
        self.store.edit_credential({"id": cid, "alias": "Main Plus", "group_name": "Work", "archived": True})
        self.sync(minute=2)
        c = self.store.credentials()[0]
        self.assertEqual((c["alias"], c["group_name"], c["archived"]), ("Main Plus", "Work", 1))
        self.assertEqual(self.store.summary({"group_name": "Work"})["requests"], 1)
        self.assertEqual(self.store.summary({"credential_id": cid})["requests"], 1)
        self.assertEqual(self.store.summary({"group_name": "Other"})["requests"], 0)
        with self.assertRaises(ValueError):
            self.store.edit_credential({"id": cid, "auth_index": "other"})

    def test_metadata_is_sanitized_in_database_and_public_responses(self):
        self.sync()
        self.store.ingest([self.record(response_headers={"secret": "private-response-header"}, prompt="private-prompt")])
        with self.store.connect() as db:
            dump = "\n".join(db.iterdump())
        for forbidden in ("private-person", "/private/auths", "private-response-header", "private-prompt",
                          "THISISATESTSECRET", "ANOTHERTESTCLIENTSECRET"):
            self.assertNotIn(forbidden, dump)
        response = json.dumps(self.store.credential_report({}))
        self.assertNotIn("fingerprint", response)
        self.assertNotIn("auth_index", response)

    def test_incomplete_or_stale_metadata_does_not_remove_known_credentials(self):
        self.sync()
        self.sync([{"provider": "freetier", "name": "no-index"}], minute=2)
        self.assertEqual(self.store.credentials()[0]["configured"], 1)
        self.assertTrue(self.sync([], minute=1)["stale"])
        with self.assertRaises(ValueError):
            self.sync([metadata(), metadata()], minute=3)
        self.assertEqual(len(self.store.credentials()), 1)
        self.sync([], minute=4)
        self.assertEqual(self.store.credentials()[0]["configured"], 0)

    def test_failure_then_success_conserves_tokens_cost_and_execution_counts(self):
        self.sync([metadata(), metadata("0000000000000002")])
        a = self.record("failed-a", failed=True)
        b = self.record("success-b")
        b["auth_index"] = "0000000000000002"
        self.store.ingest([a, b, event(timestamp=self.at(1))])
        self.store.save_price({"model": "test-model", "input": 10, "output": 20, "cache": 2})
        summary = self.store.summary({})
        report = self.store.credential_report({})
        rows = report["credentials"] + [report["unlinked"]]
        for key in ("requests", "failures", "total_tokens", "priced_requests"):
            self.assertEqual(sum(r[key] for r in rows), summary[key])
        self.assertAlmostEqual(sum(r["estimated_cost"] or 0 for r in rows), summary["estimated_cost"])
        self.assertEqual(summary["requests"], 3)
        self.assertEqual(summary["failures"], 1)

    def test_zero_traffic_and_successful_streaming_percentiles(self):
        self.sync([metadata(), metadata("0000000000000002")])
        for i, value in enumerate([10, 20, 30, 40, 50]):
            self.store.ingest([self.record(f"sample-{i}", ttft_ms=value, latency_ms=value*2)])
        invalid = self.record("nonstream", ttft_ms=1)
        invalid["stream"] = False
        self.store.ingest([invalid, self.record("failed", ttft_ms=2, failed=True), self.record("missing", ttft_ms=0)])
        rows = sorted(self.store.credential_report({})["credentials"], key=lambda x: x["requests"])
        self.assertEqual(rows[0]["requests"], 0)
        self.assertIsNone(rows[0]["ttft_p50_ms"])
        self.assertEqual((rows[1]["ttft_samples"], rows[1]["ttft_p50_ms"], rows[1]["ttft_p95_ms"]), (5, 30, 50))

    def test_canonical_independent_input_and_reasoning_are_not_double_counted(self):
        self.sync()
        record = self.record(token_breakdown=breakdown(uncached=100, read=40, write=0, ordinary=20, reasoning=10),
                             tokens={"input_tokens": 100, "output_tokens": 30, "reasoning_tokens": 10,
                                     "cached_tokens": 40, "total_tokens": 170})
        self.store.save_price({"model": "test-model", "input": 10, "output": 20, "cache": 2})
        self.store.ingest([record])
        row = self.store.events({})["rows"][0]
        self.assertEqual((row["input_tokens"], row["output_tokens"], row["total_tokens"]), (140, 30, 170))
        self.assertAlmostEqual(row["estimated_cost"], (100*10+40*2+30*20)/1e6)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT input_tokens FROM events").fetchone()[0], 100)

    def test_unpriced_cache_write_and_special_tier_are_unknown_not_free(self):
        self.store.save_price({"model": "test-model", "input": 1, "output": 1, "cache": 0})
        self.store.ingest([self.record("write", token_breakdown=breakdown(write=20)),
                           self.record("priority", response_service_tier="priority"),
                           self.record("different-model", response_model="other-model")])
        self.assertEqual(self.store.summary({})["priced_requests"], 0)
        self.assertIsNone(self.store.summary({})["estimated_cost"])

    def test_invalid_canonical_data_does_not_fall_back_to_legacy_pricing(self):
        raw = breakdown()
        raw["input"]["total_tokens"] += 1
        self.store.ingest([self.record(token_breakdown=raw)])
        self.store.save_price({"model": "test-model", "input": 1, "output": 1, "cache": 1})
        self.assertEqual(self.store.events({})["rows"][0]["token_quality"], "inconsistent")
        self.assertIsNone(self.store.summary({})["estimated_cost"])
        raw = breakdown()
        raw["input"]["cache_read_tokens"] = True
        self.assertEqual(accounting({"accounting_version": 2, "token_breakdown": raw})["token_quality"], "inconsistent")

    def test_unclassified_total_is_preserved_and_missing_usage_is_not_free(self):
        raw = {"schema_version": 2, "quality": "unclassified", "total_tokens": 90,
               "unclassified_tokens": 90,
               "input": {"total_tokens": 0, "uncached_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0},
               "output": {"total_tokens": 0, "non_reasoning_tokens": 0, "reasoning_tokens": 0}}
        self.store.ingest([self.record(tokens={}, token_breakdown=raw),
                           event(timestamp=self.at(1), tokens={}, request_id="missing-usage")])
        self.store.save_price({"model": "test-model", "input": 1, "output": 1, "cache": 1})
        self.assertEqual(self.store.summary({})["total_tokens"], 90)
        self.assertEqual(self.store.summary({})["priced_requests"], 0)
        self.assertIsNone(self.store.summary({})["estimated_cost"])


class CollectorReliabilityTests(CredentialFixture):
    def test_wal_writer_commits_while_read_snapshot_remains_open(self):
        errors = []
        def write():
            try:
                self.store.ingest([self.record()])
            except Exception as error:
                errors.append(type(error).__name__)
        with self.store.connect() as reader:
            reader.execute("BEGIN")
            self.assertEqual(reader.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
            worker = threading.Thread(target=write)
            worker.start()
            worker.join(timeout=3)
            finished_during_snapshot = not worker.is_alive()
            self.assertEqual(reader.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        worker.join(timeout=3)
        self.assertTrue(finished_during_snapshot)
        self.assertFalse(errors)
        self.assertEqual(self.store.summary({})["requests"], 1)

    def test_writer_failure_retries_same_batch_without_second_queue_pop(self):
        keeper = Keeper(self.store, "test-key", "http://127.0.0.1:1")
        record = self.record()
        calls, writes = [], []
        ingest = self.store.ingest
        def transport(path):
            calls.append(path)
            if path.endswith("/config"):
                return {"observability": {"usage": {"usage-statistics-enabled": True}}}
            if path.endswith("/credentials"):
                return {"files": [metadata()]}
            return [record]
        def writer(batch):
            writes.append(batch)
            if len(writes) == 1:
                raise sqlite3.OperationalError("simulated disk failure")
            count = ingest(batch)
            keeper.stop.set()
            return count
        keeper.request = transport
        self.store.ingest = writer
        keeper.stop.wait = lambda _: None
        keeper.run()
        self.assertEqual(calls.count(QUEUE), 1)
        self.assertIs(writes[0], writes[1])
        self.assertEqual((keeper.collected, keeper.pending_count), (1, 0))
        self.assertIsNotNone(keeper.last_poll)

    def test_same_database_collector_lock_rejects_second_owner(self):
        keeper = Keeper(self.store, "test-key", "http://127.0.0.1:1")
        with CollectorLease(self.path):
            keeper.run()
            self.assertEqual(keeper.last_error, "collector_already_running")
        with CollectorLease(self.path):
            pass

    def test_empty_successful_poll_is_distinct_from_last_event_time(self):
        keeper = Keeper(self.store, "test-key", "http://127.0.0.1:1")
        def transport(path):
            if path.endswith("/config"):
                return {"observability": {"usage": {"usage-statistics-enabled": True}}}
            if path.endswith("/credentials"):
                return {"files": []}
            keeper.stop.set()
            return []
        keeper.request = transport
        keeper.run()
        self.assertEqual(keeper.state, "running")
        self.assertIsNotNone(keeper.last_poll)
        self.assertIsNone(keeper.last_received)
        self.assertIsNone(keeper.last_collected)


class CredentialHttpTests(CredentialFixture):
    def test_authenticated_read_edit_and_export_share_filters(self):
        self.sync()
        cid = self.store.credentials()[0]["id"]
        self.store.ingest([self.record(), event(timestamp=self.at(1))])
        page = Path(self.temp.name) / "index.html"
        page.write_text("test")
        http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Keeper(self.store, "test-key", "http://127.0.0.1:1"), page))
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{http.server_port}{API}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def call(route, data=None, key="test-key"):
            return opener.open(urllib.request.Request(base+route, data=None if data is None else json.dumps(data).encode(),
                headers={"Authorization": "Bearer "+key, "Content-Type": "application/json"}), timeout=3)
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                call("credentials", key="invalid")
            self.assertEqual(error.exception.code, 401)
            with call("credentials/edit", {"id": cid, "alias": "Private Main", "group_name": "Work"}) as r:
                self.assertTrue(json.load(r)["saved"])
            with call("credentials/summary?group_name=Work") as r:
                self.assertEqual(json.load(r)["credentials"][0]["requests"], 1)
            with call("export?credential_id="+cid) as r:
                csv = r.read().decode("utf-8-sig")
                self.assertEqual(len(csv.splitlines()), 2)
                self.assertIn("association_state", csv)
            with self.assertRaises(urllib.error.HTTPError) as error:
                call("credentials/edit", {"id": cid, "alias": ""})
            self.assertEqual(error.exception.code, 400)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
