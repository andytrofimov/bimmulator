"""Explicit operator-prepared mode: metadata fixtures, no firmware inspection."""
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
launch = runpy.run_path(str(TOOLS / 'idrive6-launch.py'))
from vm_lab_settings import DEFAULTS


class PreparedInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='id6-prepared-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project'
        self.project.mkdir()
        self.file = self.project / 'config.toml'
        self.file.touch()
        self.root = self.base / 'operator root'
        for name in launch['PREPARED_FILES']:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()  # Metadata only: empty synthetic files, not firmware.
        self.boot = self.base / 'operator boot.ifs'
        self.boot.touch()
        self.config = {'preparedRoot': str(self.root), 'bootImage': str(self.boot),
                       'cacheDir': str(self.base / 'outputs'), 'modules': ['head-unit']}

    def checked(self, config):
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(config))), \
                patch('platform.system', return_value='Linux'), patch('platform.machine', return_value='x86_64'):
            return launch['checked_config'](self.project, self.file, 'fixture-nix')

    def test_explicit_pair_nbt_only_needs_no_psdz(self):
        checked = self.checked(self.config)
        self.assertEqual(checked['preparedRoot'], str(self.root))
        self.assertEqual(checked['bootImage'], str(self.boot))
        self.assertNotIn('psdzdata', checked)

    def test_both_modules_still_require_psdz_for_bo03(self):
        config = {**self.config, 'modules': ['head-unit', '6wb']}
        with self.assertRaisesRegex(ValueError, 'psdzdata'):
            self.checked(config)
        checked = self.checked({**config, 'psdzdata': str(self.base / 'external-psdz')})
        self.assertIn('psdzdata', checked)

    def test_pair_types_module_selection_and_external_paths_fail_closed(self):
        invalid = [dict(self.config, preparedRoot=None), dict(self.config, bootImage='relative'),
                   dict(self.config, modules=['6wb']), dict(self.config, preparedRoot=str(self.project)),
                   {key: value for key, value in self.config.items() if key != 'bootImage'},
                   {key: value for key, value in self.config.items() if key != 'preparedRoot'}]
        for config in invalid:
            with self.subTest(config=config), patch('subprocess.Popen') as spawn, self.assertRaises(ValueError):
                self.checked(config)
            spawn.assert_not_called()

    def test_outputs_must_not_write_inside_prepared_input_root(self):
        for cache in (self.root, self.root / 'outputs'):
            with self.subTest(cache=cache), patch('subprocess.Popen') as spawn, self.assertRaisesRegex(ValueError, 'read-only'):
                self.checked({**self.config, 'cacheDir': str(cache)})
            spawn.assert_not_called()

    def assert_nested_input_rejected(self, leaf):
        cache = self.base / 'cache'
        root = cache / leaf
        for name in launch['PREPARED_FILES']:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        before = sorted(str(p.relative_to(cache)) for p in cache.rglob('*'))
        with patch('subprocess.Popen') as spawn, self.assertRaisesRegex(ValueError, 'disjoint'):
            self.checked({**self.config, 'preparedRoot': str(root), 'cacheDir': str(cache)})
        spawn.assert_not_called()
        self.assertEqual(sorted(str(p.relative_to(cache)) for p in cache.rglob('*')), before)

    def test_prepared_root_must_not_contain_pending_store_path(self):
        self.assert_nested_input_rejected('settings')

    def test_prepared_root_must_not_contain_session_output_path(self):
        self.assert_nested_input_rejected('sessions')

    def test_boot_image_must_be_outside_all_mutable_cache_outputs(self):
        cache = self.base / 'cache'
        cache.mkdir()
        boot = cache / 'libidrive-angle-provider.so'
        boot.write_bytes(b'synthetic immutable boot fixture')
        with patch('subprocess.Popen') as spawn, self.assertRaisesRegex(ValueError, 'outside the mutable'):
            self.checked({**self.config, 'bootImage': str(boot), 'cacheDir': str(cache)})
        spawn.assert_not_called()
        self.assertEqual(boot.read_bytes(), b'synthetic immutable boot fixture')
        self.assertEqual(sorted(p.name for p in cache.iterdir()), [boot.name])

    def test_missing_each_unconditional_profile_input_is_zero_spawn(self):
        names = ('bin/cp', 'bin/screen', 'bin/sleep', 'lib/screen-sw.so', 'lib/libswblit.so.1',
                 'lib/graphics/omap5430/libWFDomap5430ES2_0.so', 'opt/hmi/ID5/lib/libhmicom.so',
                 'bin/io-usb', 'lib/devu-hb-ehci-omap3.so', 'opt/sys/bin/LayerManagerService')
        for name in names:
            target = self.root / name
            self.assertEqual(target.resolve(), target)
            target.unlink()  # Exact owned empty metadata fixture, restored below.
            try:
                with self.subTest(name=name), patch('subprocess.Popen') as spawn, self.assertRaisesRegex(ValueError, name):
                    self.checked(self.config)
                spawn.assert_not_called()
            finally:
                target.touch()

    def test_missing_metadata_rejected_before_any_child(self):
        missing = self.root / launch['PREPARED_FILES'][0]
        self.assertEqual(missing.resolve().parent.parent, self.root.resolve())
        missing.unlink()  # Exact newly created owned fixture.
        with patch('subprocess.Popen') as spawn, self.assertRaisesRegex(ValueError, 'not package-verified'):
            self.checked(self.config)
        spawn.assert_not_called()

    def test_prepared_sources_use_explicit_profile_overrides(self):
        config = self.checked(self.config)
        command, env = launch['head_unit_command'](TOOLS.parent, config, self.root,
                                                   run_id='prepared-fixture', values=DEFAULTS)
        for key, value in (('IDRIVE_BOOT_IMAGE', str(self.boot)),
                           ('IDRIVE_ROOTFS_TREE', str(self.root)), ('IDRIVE_REALIZED_ROOTFS', str(self.root))):
            self.assertIn(key + '=' + value, command)
        runner = runpy.run_path(str(TOOLS / 'run-hmi-profile.py'))['main']
        with patch.dict(os.environ, env), patch.object(sys, 'argv', command[1:]), patch('os.execvpe') as execute:
            self.assertEqual(runner(), 127)
        actual = execute.call_args.args[2]
        self.assertEqual(actual['IDRIVE_ROOTFS_TREE'], str(self.root))
        self.assertEqual(actual['IDRIVE_BOOT_IMAGE'], str(self.boot))
        self.assertEqual(actual['IDRIVE_ROOT_ARCHIVE_OUTPUT'],
                         str(Path(config['cacheDir']) / 'runs/prepared-fixture/rootfs.tar.gz'))

    def test_main_skips_only_nbt_package_staging_and_labels_inputs(self):
        config = self.checked({**self.config, 'modules': ['head-unit', '6wb'],
                               'psdzdata': str(self.base / 'external-psdz')})
        verify, stage, bo03, owner = Mock(), Mock(), Mock(return_value=('g', 'c', 'd')), Mock(return_value=0)
        old_term = signal.getsignal(signal.SIGTERM)
        try:
            with patch.dict(launch['main'].__globals__, {
                    'checked_config': Mock(return_value=config), 'preflight': Mock(),
                    'verify_packages': verify, 'stage': stage, 'stage_kombi': bo03, 'run_session': owner}), \
                    patch.object(sys, 'argv', ['idrive6']), patch('subprocess.Popen') as spawn:
                self.assertEqual(launch['main'](), 0)
            verify.assert_not_called()
            stage.assert_not_called()
            bo03.assert_called_once()
            self.assertEqual(owner.call_args.args[3], self.root)
            spawn.assert_not_called()
        finally:
            signal.signal(signal.SIGTERM, old_term)

    def test_session_record_never_claims_package_verification(self):
        config = self.checked(self.config)
        cache = Path(config['cacheDir'])
        # Existing real owner is intercepted only after snapshot/record composition.
        with patch.dict(launch['run_session'].__globals__, {'run_kombi_session': Mock(return_value=0)}):
            self.assertEqual(launch['run_session'](TOOLS.parent, cache, config, self.root, None), 0)
        document = json.loads(next((cache / 'sessions').glob('*/session.json')).read_text())
        self.assertEqual(document['head_unit_input'], 'operator_prepared_not_package_verified')
        self.assertEqual(document['schema'], 'idrive6-session-v1')


if __name__ == '__main__':
    unittest.main()
