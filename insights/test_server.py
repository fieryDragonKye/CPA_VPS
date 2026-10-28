import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from server import API, Keeper, Store, make_handler, normalize


def event(**overrides):
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "model": "test-model",
            "provider": "codex", "source": "sk-THISISATESTSECRETNEVERPERSIST",
            "api_key": "sk-ANOTHERTESTCLIENTSECRET", "request_id": "unit-test-1",
            "tokens": {"input_tokens": 1000, "output_tokens": 500,
                       "reasoning_tokens": 200, "cached_tokens": 400}, **overrides}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "usage.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def test_sensitive_fields_are_dropped(self):
        original = event(response_headers={"Authorization": "Bearer private-test-token"}, prompt="PRIVATE PROMPT")
        normalized = normalize(original)
        text = json.dumps(normalized)
        self.assertNotIn("THISISATESTSECRET", text)
        self.assertNotIn("ANOTHERTESTCLIENTSECRET", text)
        self.assertNotIn("PRIVATE PROMPT", text)
        self.assertNotIn("private-test-token", text)
        self.assertEqual(normalized["total_tokens"], 1500)
        self.assertNotIn("codexSecretKeyWithoutAnyPrefix", json.dumps(normalize(event(source="codexSecretKeyWithoutAnyPrefix"))))
        self.assertNotIn("password", json.dumps(normalize(event(source="https://user:password@example.test/path?key=secret"))))

    def test_deduplication_and_persistence(self):
        record = event()
        self.assertEqual(self.store.ingest([record, record]), 1)
        reopened = Store(self.store.path)
        self.assertEqual(reopened.summary({})["requests"], 1)

    def test_filters_and_reasoning_not_double_billed(self):
        self.store.ingest([event(), event(model="other", failed=True, request_id="other-id")])
        self.store.save_price({"model": "test-model", "input": 10, "output": 20, "cache": 2})
        summary = self.store.summary({"model": "test-model"})
        self.assertEqual(summary["total_tokens"], 1500)
        self.assertAlmostEqual(summary["estimated_cost"], (600*10+500*20+400*2)/1e6)
        self.assertEqual(self.store.summary({"result": "failed"})["requests"], 1)
        self.assertIsNone(self.store.summary({"model": "other"})["estimated_cost"])
        self.assertEqual(self.store.summary({"model": "x' OR 1=1 --"})["requests"], 0)

    def test_invalid_events_and_prices(self):
        self.assertIsNone(normalize({"timestamp": "not a timestamp"}))
        self.assertIsNone(normalize(event(timestamp="2026-01-01")))
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.store.save_price({"model": "test", "input": value, "output": 1, "cache": 1})


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        page = root / "index.html"
        page.write_text("test page")
        self.store = Store(root / "test.sqlite")
        self.store.ingest([event()])
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Keeper(self.store, "test-key", "http://127.0.0.1:1"), page))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, route, headers=None):
        req = urllib.request.Request(self.url + route, headers=headers or {})
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req)

    def test_unauthenticated_access_denied(self):
        with self.assertRaises(urllib.error.HTTPError) as result:
            self.request(API + "summary")
        self.assertEqual(result.exception.code, 401)

    def test_cross_origin_access_denied(self):
        with self.assertRaises(urllib.error.HTTPError) as result:
            self.request(API + "summary", {"Authorization": "Bearer test-key", "Origin": "https://untrusted.invalid"})
        self.assertEqual(result.exception.code, 403)

    def test_authenticated_summary_and_csv(self):
        headers = {"Authorization": "Bearer test-key"}
        with self.request(API + "summary", headers) as response:
            self.assertEqual(json.load(response)["requests"], 1)
        with self.request(API + "export", headers) as response:
            content = response.read().decode("utf-8-sig")
            self.assertIn("test-model", content)
            self.assertNotIn("THISISATESTSECRET", content)
            self.assertNotIn("ANOTHERTESTCLIENTSECRET", content)


class CollectorTests(unittest.TestCase):
    def test_http_queue_to_persistent_database(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "collector.sqlite")
            keeper = Keeper(store, "test-key", "http://127.0.0.1:1")
            calls = []
            record = event()

            def transport(path):
                calls.append(path)
                if path.endswith("/config"):
                    return {"observability": {"usage": {"usage-statistics-enabled": True}}}
                keeper.stop.set()
                return [record]

            keeper.request = transport
            keeper.run()
            self.assertTrue(any("/observability/usage/queue" in path for path in calls))
            self.assertEqual(store.summary({})["requests"], 1)
            self.assertEqual(keeper.collected, 1)
            self.assertIsNotNone(keeper.last_collected)

    def test_rejected_management_key_stops_without_retry_storm(self):
        with tempfile.TemporaryDirectory() as temp:
            keeper = Keeper(Store(Path(temp) / "collector.sqlite"), "wrong-key", "http://127.0.0.1:1")
            calls = []

            def denied(path):
                calls.append(path)
                raise urllib.error.HTTPError(path, 401, "unauthorized", {}, None)

            keeper.request = denied
            started = time.monotonic()
            keeper.run()
            self.assertEqual(len(calls), 1)
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(keeper.last_error, "http_401")


if __name__ == "__main__":
    unittest.main()
