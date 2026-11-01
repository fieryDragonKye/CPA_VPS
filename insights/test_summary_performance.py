"""Accounting and snapshot regressions for the consolidated summary query."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import threading
from unittest.mock import patch

from test_credentials import CredentialFixture
from test_server import event


class SummaryQueryTests(CredentialFixture):
    def test_totals_trends_models_and_filters_conserve_the_same_records(self):
        self.sync()
        self.store.save_price({'model': 'priced', 'input': 10, 'output': 20, 'cache': 2})
        self.store.save_price({'model': 'free', 'input': 0, 'output': 0, 'cache': 0})
        self.store.ingest([self.record('a', minute=1, model='priced'),
                           self.record('b', minute=2, model='priced', failed=True),
                           self.record('c', minute=3, model='free'),
                           self.record('d', minute=4, model='unpriced')])
        report = self.store.summary({})
        self.assertEqual((report['requests'], report['failures'], report['total_tokens']), (4, 1, 6000))
        self.assertEqual(report['priced_requests'], 3)
        self.assertAlmostEqual(report['estimated_cost'], 2*(600*10+400*2+500*20)/1e6)
        for name in ('trend', 'models'):
            self.assertEqual(sum(r['requests'] for r in report[name]), 4)
            self.assertEqual(sum(r['total_tokens'] for r in report[name]), 6000)
            self.assertEqual(sum(r['failures'] for r in report[name]), 1)
        self.assertEqual(self.store.summary({'result': 'failed'})['requests'], 1)
        self.assertEqual(self.store.summary({'model': 'priced'})['total_tokens'], 3000)
        self.assertEqual(self.store.summary({'credential_id': self.store.credentials()[0]['id']})['requests'], 4)

    def test_partial_time_window_and_unlinked_filter_do_not_expand_to_whole_table(self):
        now = datetime.now(timezone.utc)
        self.store.ingest([event(timestamp=(now-timedelta(hours=2)).isoformat(), model='recent'),
                           event(timestamp=(now-timedelta(hours=30)).isoformat(), model='old', request_id='old')])
        report = self.store.summary({'range': '24h', 'credential_id': 'unlinked'})
        self.assertEqual(report['requests'], 1)
        self.assertEqual([r['model'] for r in report['models']], ['recent'])
        self.assertEqual(report['stored_records'], 2)
        # Option lists intentionally describe retained data, not just the time range.
        self.assertEqual(report['options']['model'], ['old', 'recent'])
        empty = self.store.summary({'range': '1h'})
        self.assertEqual((empty['requests'], empty['total_tokens'], empty['trend'], empty['models']), (0, 0, [], []))
        self.assertIsNone(empty['estimated_cost'])

    def test_options_track_inserts_deletes_and_legacy_nulls_without_stale_results(self):
        self.store.ingest([event(model='before')])
        self.assertEqual(self.store.summary({})['options']['model'], ['before'])
        with self.store.connect() as db:
            db.execute('INSERT INTO events(id,timestamp,model,total_tokens) VALUES(?,?,?,?)',
                       ('legacy-null', self.at(1), 'legacy', 42))
        options = self.store.summary({})['options']
        self.assertEqual(options['model'], ['before', 'legacy'])
        self.assertIn(None, options['source'])
        with self.store.connect() as db:
            db.execute("DELETE FROM events WHERE model='before'")
        self.assertEqual(self.store.summary({})['options']['model'], ['legacy'])

    def test_reference_counts_survive_duplicate_delivery_updates_and_rollbacks(self):
        a, b = event(model='shared', request_id='a'), event(model='shared', request_id='b')
        self.assertEqual(self.store.ingest([a, a, b]), 2)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT refs FROM event_options WHERE field='model' AND value='shared'").fetchone()[0], 2)
            first = db.execute("SELECT id FROM events WHERE model='shared' LIMIT 1").fetchone()[0]
            db.execute('DELETE FROM events WHERE id=?', (first,))
        self.assertEqual(self.store.summary({})['options']['model'], ['shared'])
        with self.store.connect() as db:
            db.execute("UPDATE events SET model='changed' WHERE model='shared'")
        self.assertEqual(self.store.summary({})['options']['model'], ['changed'])
        try:
            with self.store.connect() as db:
                db.execute("UPDATE events SET model='rolled-back'")
                raise RuntimeError('simulate rollback')
        except RuntimeError:
            pass
        self.assertEqual(self.store.summary({})['options']['model'], ['changed'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT SUM(refs) FROM event_options').fetchone()[0], 4)

    def test_dictionary_backfill_and_repeated_migration_preserve_counts(self):
        self.store.ingest([event(), event(model='another', request_id='other')])
        with self.store.connect() as db:
            for name in ('insert', 'update', 'delete'):
                db.execute(f'DROP TRIGGER event_options_{name}')
            db.execute('DROP TABLE event_options')
            before = db.total_changes
            db.execute('INSERT OR IGNORE INTO events(id,timestamp,model,total_tokens) VALUES(?,?,?,?)',
                       ('rollback-write', self.at(1), 'rollback-model', 42))
            self.assertEqual(db.total_changes-before, 1)
        for _ in range(2):
            reopened = type(self.store)(self.path)
            self.assertEqual(reopened.summary({})['requests'], 3)
            self.assertEqual(reopened.summary({})['options']['model'], ['another', 'rollback-model', 'test-model'])
            with reopened.connect() as db:
                self.assertEqual(db.execute('SELECT SUM(refs) FROM event_options').fetchone()[0], 12)

    def test_price_changes_are_visible_on_next_query(self):
        self.store.ingest([event(model='priced')])
        self.assertIsNone(self.store.summary({})['estimated_cost'])
        self.store.save_price({'model': 'priced', 'input': 1, 'output': 1, 'cache': 1})
        first = self.store.summary({})['estimated_cost']
        self.store.save_price({'model': 'priced', 'input': 2, 'output': 2, 'cache': 2})
        self.assertAlmostEqual(self.store.summary({})['estimated_cost'], first*2)

    def test_old_sqlite_hint_fallback_keeps_the_same_result(self):
        self.store.ingest([event()])
        reference = self.store.summary({})
        # Exercises the no-hint syntax branch on the installed SQLite engine.
        with patch('server.sqlite3.sqlite_version_info', (3, 34, 0)):
            self.assertEqual(self.store.summary({}), reference)

    def test_concurrent_insert_does_not_mix_summary_and_option_snapshots(self):
        self.store.ingest([event(model='before')])
        writer = type(self.store)(self.path)
        original_connect = self.store.connect
        errors, workers, finished = [], [], []
        triggered = False
        def write():
            try:
                writer.ingest([event(model='arrived-during-report', request_id='concurrent')])
            except Exception as error:
                errors.append(type(error).__name__)
        @contextmanager
        def traced():
            with original_connect() as db:
                def trace(sql):
                    nonlocal triggered
                    if 'FROM event_options' in sql and not triggered:
                        triggered = True
                        worker = threading.Thread(target=write)
                        workers.append(worker)
                        worker.start()
                        worker.join(timeout=3)
                        finished.append(not worker.is_alive())
                db.set_trace_callback(trace)
                try:
                    yield db
                finally:
                    db.set_trace_callback(None)
        self.store.connect = traced
        try:
            report = self.store.summary({})
        finally:
            self.store.connect = original_connect
            for worker in workers:
                worker.join(timeout=3)
        self.assertEqual(finished, [True])
        self.assertFalse(errors)
        self.assertEqual((report['requests'], report['stored_records']), (1, 1))
        self.assertEqual(report['options']['model'], ['before'])
        self.assertEqual(self.store.summary({})['requests'], 2)


if __name__ == '__main__':
    import unittest
    unittest.main()
