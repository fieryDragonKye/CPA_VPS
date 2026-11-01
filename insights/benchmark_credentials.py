"""Synthetic SQLite benchmark. Creates and removes only its own temporary database."""
import argparse
import json
import math
import platform
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server import Store
from test_credentials import breakdown, metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=250000)
    args = parser.parse_args()
    if not 1 <= args.rows <= 250000:
        parser.error("rows must be between 1 and 250000")
    with tempfile.TemporaryDirectory(prefix="cpa-credential-benchmark-") as directory:
        store = Store(Path(directory) / "synthetic.sqlite")
        now = datetime.now(timezone.utc)
        store.sync_credentials({"files": [metadata(f"{i:016x}") for i in range(1, 21)]},
                               (now-timedelta(hours=1)).isoformat())
        store.save_price({"model": "synthetic-model", "input": 1, "output": 2, "cache": .1})
        stamp = (now-timedelta(minutes=30)).isoformat()
        base = {"timestamp": stamp, "provider": "codex", "model": "synthetic-model", "stream": True,
                "accounting_version": 2, "token_breakdown": breakdown(),
                "tokens": {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500}}
        started = time.perf_counter()
        for start in range(0, args.rows, 500):
            records = [{**base, "execution_id": f"synthetic-{i}", "auth_index": f"{i%20:016x}",
                        "ttft_ms": 50+i%1000, "latency_ms": 1000+i%3000, "failed": i%7==0}
                       for i in range(start, min(args.rows, start+500))]
            store.ingest(records)
        timings = {"ingest_seconds": time.perf_counter()-started}
        started = time.perf_counter()
        summary = store.summary({})
        timings["summary_ms"] = (time.perf_counter()-started)*1000
        started = time.perf_counter()
        report = store.credential_report({})
        timings["credential_report_ms"] = (time.perf_counter()-started)*1000
        started = time.perf_counter()
        page = store.events({})
        timings["detail_page_ms"] = (time.perf_counter()-started)*1000
        started = time.perf_counter()
        exported = store.events({}, export=True)
        timings["export_10000_rows_ms"] = (time.perf_counter()-started)*1000
        groups = report["credentials"] + [report["unlinked"]]
        assert summary["requests"] == args.rows
        for k in ("requests", "failures", "total_tokens", "priced_requests"):
            assert summary[k] == sum(r[k] for r in groups), k
        assert math.isclose(summary["estimated_cost"], sum(r["estimated_cost"] or 0 for r in groups), rel_tol=1e-8)
        # A writer using WAL must still make progress while the grouped percentile query runs.
        errors = []
        def write():
            try:
                store.ingest([{**base, "execution_id": "concurrent-write", "auth_index": "0000000000000001"}])
            except Exception as error:
                errors.append(type(error).__name__)
        started = time.perf_counter()
        worker = threading.Thread(target=write)
        worker.start()
        store.credential_report({})
        worker.join(timeout=15)
        assert not worker.is_alive() and not errors, errors
        timings["report_with_concurrent_writer_ms"] = (time.perf_counter()-started)*1000
        result = {"platform": platform.platform(), "python": platform.python_version(),
                  "rows": args.rows, "credentials": 20, "unlinked_rows": report["unlinked"]["requests"],
                  "zero_traffic_credentials": sum(c["requests"] == 0 for c in report["credentials"]),
                  "page_rows": len(page["rows"]), "export_rows": len(exported["rows"]),
                  "reconciliation": "passed", "database_main_bytes": store.path.stat().st_size,
                  "timings": {k: round(v, 3) for k, v in timings.items()}}
        with store.connect() as db:
            result["aggregate_query_plan"] = [r[3] for r in db.execute(
                "EXPLAIN QUERY PLAN SELECT SUM(total_tokens) FROM events e INDEXED BY events_time WHERE timestamp>=?", (stamp,))]
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
