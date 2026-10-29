import json
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from server import API, PRICE_PRESET, Store
from test_server import event
import test_server as fixtures


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'usage.sqlite')

    def tearDown(self):
        self.temp.cleanup()

    def test_import_is_idempotent_and_preserves_custom_prices(self):
        self.store.save_price({'model': 'gpt-6.1-sol', 'input': 7, 'output': 8, 'cache': 9})
        self.assertEqual(self.store.import_price_preset(PRICE_PRESET['id']), len(PRICE_PRESET['models'])-1)
        self.assertEqual(self.store.import_price_preset(PRICE_PRESET['id']), 0)
        rows = {p['model']: p for p in self.store.prices()}
        self.assertEqual(rows['gpt-6.1-sol']['input'], 7)
        self.assertEqual(rows['gpt-6.1-sol']['basis'], 'manual')
        self.assertNotIn('source_url', rows['gpt-6.1-sol'])
        self.assertTrue(rows['gpt-6-astra']['source_url'].startswith('https://developers.openai.com/'))
        with self.assertRaises(ValueError):
            self.store.import_price_preset('unverified-live-rates')

    def test_normal_request_prices_cache_once_and_does_not_add_reasoning_again(self):
        self.store.import_price_preset(PRICE_PRESET['id'])
        self.store.ingest([event(model='gpt-6.1-sol', tokens={'input_tokens': 10000, 'cached_tokens': 8000, 'output_tokens': 1000, 'reasoning_tokens': 600})])
        row = self.store.events({})['rows'][0]
        self.assertAlmostEqual(row['estimated_cost'], 0.0148)
        self.assertEqual(row['long_context_applied'], 0)
        self.assertAlmostEqual(self.store.summary({})['estimated_cost'], row['estimated_cost'])

    def test_threshold_is_strict_and_surcharge_applies_to_the_whole_request(self):
        self.store.import_price_preset(PRICE_PRESET['id'])
        for index, count in enumerate([272000, 272001]):
            self.store.ingest([event(model='gpt-6.1-sol', request_id=f'long-{index}', tokens={'input_tokens': count, 'cached_tokens': count, 'output_tokens': 1000})])
        rows = {r['input_tokens']: r for r in self.store.events({})['rows']}
        self.assertAlmostEqual(rows[272000]['estimated_cost'], .0272+.01)
        self.assertAlmostEqual(rows[272001]['estimated_cost'], .0272001*2+.01*1.5)
        self.assertEqual(rows[272001]['long_context_applied'], 1)

    def test_manual_rates_do_not_inherit_official_multipliers(self):
        self.store.save_price({'model': 'gpt-6.1-sol', 'input': 2, 'output': 10, 'cache': .1})
        self.store.ingest([event(model='gpt-6.1-sol', tokens={'input_tokens': 300000, 'output_tokens': 1000})])
        row = self.store.events({})['rows'][0]
        self.assertAlmostEqual(row['estimated_cost'], .61)
        self.assertEqual(row['long_context_applied'], 0)

    def test_unknown_aliases_remain_unpriced_and_explicit_free_rates_remain_zero(self):
        self.store.import_price_preset(PRICE_PRESET['id'])
        self.store.save_price({'model': 'free-test', 'input': 0, 'output': 0, 'cache': 0})
        self.store.ingest([event(model='AR/gpt-6.1-sol'), event(model='free-test', request_id='free')])
        rows = {r['model']: r for r in self.store.events({})['rows']}
        self.assertIsNone(rows['AR/gpt-6.1-sol']['estimated_cost'])
        self.assertEqual(rows['free-test']['estimated_cost'], 0)
        self.assertEqual(self.store.summary({})['priced_requests'], 1)

    def test_official_label_cannot_be_attached_to_modified_rates(self):
        data = {'model': 'gpt-6.1-sol', 'input': 99, 'output': 10, 'cache': .1, 'basis': PRICE_PRESET['id']}
        with self.assertRaises(ValueError):self.store.save_price(data)
        data['basis'] = 'manual';self.store.save_price(data)
        self.assertEqual(self.store.prices()[0]['basis'], 'manual')

    def test_legacy_prices_migrate_without_repricing_or_changing_events(self):
        path = Path(self.temp.name)/'legacy.sqlite'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE prices(model TEXT PRIMARY KEY,input REAL,output REAL,cache REAL,updated TEXT)')
            db.execute('INSERT INTO prices VALUES(?,?,?,?,?)', ['gpt-6.1-sol', 3, 4, 5, 'old-date'])
        db.close()
        for _ in range(2):
            store = Store(path)
            row = store.prices()[0]
            self.assertEqual((row['input'], row['updated'], row['basis']), (3, 'old-date', 'manual'))

    def test_legacy_writers_remain_compatible_and_invalidate_stale_reference_rules(self):
        self.store.import_price_preset(PRICE_PRESET['id'])
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO prices VALUES(?,?,?,?,?)', ['gpt-6.1-sol', 7, 8, 9, 'legacy-update'])
        row = next(p for p in self.store.prices() if p['model'] == 'gpt-6.1-sol')
        self.assertEqual(row['basis'], 'manual')
        self.assertNotIn('source_url', row)


class PricingHttpTests(unittest.TestCase):
    setUp = fixtures.HttpTests.setUp
    tearDown = fixtures.HttpTests.tearDown
    def post(self, route, data, key='test-key'):
        request = urllib.request.Request(self.url+API+route, data=json.dumps(data).encode(),
            headers={'Authorization':'Bearer '+key, 'Content-Type':'application/json'})
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request)

    def test_import_requires_authentication_and_is_idempotent(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post('prices/import', {'preset':PRICE_PRESET['id']}, key='invalid')
        self.assertEqual(error.exception.code, 401)
        with self.post('prices/import', {'preset':PRICE_PRESET['id']}) as response:
            self.assertEqual(json.load(response)['imported'], len(PRICE_PRESET['models']))
        with self.post('prices/import', {'preset':PRICE_PRESET['id']}) as response:
            self.assertEqual(json.load(response)['imported'], 0)

    def test_invalid_import_payloads_are_rejected_without_writes(self):
        for payload in [[], {'preset':'unknown'}]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.post('prices/import', payload)
            self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.store.prices(), [])

    def test_reference_metadata_is_available_only_with_management_auth(self):
        request = urllib.request.Request(self.url+API+'pricing-preset',headers={'Authorization':'Bearer test-key'})
        with urllib.request.urlopen(request) as response:
            data = json.load(response)
        self.assertEqual(data['currency'], 'USD')
        self.assertEqual(data['speed'], 'Standard')
        self.assertEqual(data['verified_at'], PRICE_PRESET['verified_at'])
