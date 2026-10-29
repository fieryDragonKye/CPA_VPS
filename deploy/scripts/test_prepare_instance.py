"""Initializer contract checks; private temporary data only, no network/dependencies."""
from pathlib import Path
import importlib.util,json,tempfile,unittest

spec=importlib.util.spec_from_file_location('prepare_instance',Path(__file__).with_name('prepare-instance.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class InitializerTests(unittest.TestCase):
    def test_block_mappings_preserve_plugin_plain_keys(self):
        text=module.block_yaml({'plugins':{'configs':{'freetier2api':{'enabled':True,'state_dir':'/private/test','auto_checkin':False}}}})
        self.assertIn('      state_dir: "/private/test"\n',text)
        self.assertNotIn('"state_dir":',text)
        self.assertIn('      auto_checkin: false\n',text)

    def test_scalar_types_and_escaping(self):
        text=module.block_yaml({'text':'a: b\n"quoted"','flag':False,'number':0,'nil':None,'true':'literal','empty':[],'mapping':{}})
        self.assertIn('text: "a: b\\n\\"quoted\\""',text)
        self.assertIn('flag: false',text);self.assertIn('number: 0',text);self.assertIn('nil: null',text)
        self.assertIn('"true": "literal"',text)
        self.assertIn('empty: []',text);self.assertIn('mapping: {}',text)
        self.assertEqual(module.block_yaml({}),'{}\n');self.assertEqual(module.block_yaml([]),'[]\n')
        with self.assertRaises(ValueError):module.block_yaml({'bad':float('nan')})

    def test_new_instance_matches_its_secret_files_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'instance';module.prepare(target,'private-pod')
            text=(target/'config/config.yaml').read_text(encoding='utf-8')
            self.assertTrue(text.startswith('config-version: 8\nserver:\n'))
            for name in ['management','client']:
                key=(target/'secrets'/f'{name}.key').read_text().strip()
                self.assertIn(json.dumps(key),text)
            self.assertIn('request-log: false',text);self.assertIn('logs-max-total-size-mb: 20',text)
            self.assertIn('allow-remote: false',text);self.assertIn('disable-auto-update-panel: true',text)
            self.assertEqual(json.loads((target/'instance.json').read_text())['createdBy'],json.loads((module.ROOT/'lock.json').read_text())['bundleVersion'])
            with self.assertRaises(ValueError):module.prepare(target,'private-pod')

if __name__=='__main__':unittest.main()
