"""Focused host-only tests. All persistence fixtures live in owned temp dirs."""
import json
import os
from pathlib import Path
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from vm_lab_settings import (DEFAULTS, LAUNCH_ENV, SettingsStore, decode_json,
                             launch_values, validate_payload, validate_values)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vm-settings-test-')
        self.directory = Path(self.temp.name).resolve()
        self.path = self.directory / 'pending.json'
        self.store = SettingsStore(self.path, self.directory)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_off_no_file_created(self):
        self.assertFalse(self.store.load()['connecteddrive_service'])
        self.assertFalse(self.store.load()['connecteddrive_availability'])
        self.assertFalse(self.path.exists())
        self.assertFalse(self.store.snapshot()['restart_required'])

    def test_whitelist_types_and_no_enums(self):
        # Source-supported options are bools only: enum-like strings are rejected.
        for key in DEFAULTS:
            for invalid in (0, 1, '1', 'on', 'off', None, [], {}):
                with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                    validate_values({**DEFAULTS, key: invalid})
        for invalid in (None, [], {}, {**DEFAULTS, 'IDRIVE_ROOTFS_TREE': '/tmp/evil'}):
            with self.assertRaises(ValueError):
                validate_values(invalid)

    def test_dependencies(self):
        with self.assertRaises(ValueError):
            validate_values({**DEFAULTS, 'connecteddrive_availability': True})
        with self.assertRaises(ValueError):
            validate_values({**DEFAULTS, 'f32_resources': False})
        valid = {**DEFAULTS, 'connecteddrive_service': False, 'connecteddrive_availability': False,
                 'reverse_camera': False, 'f32_resources': False}
        self.assertEqual(validate_values(valid), valid)

    def test_unsupported_mocks_are_rejected(self):
        for key in ('connecteddrive_service', 'connecteddrive_availability'):
            with self.assertRaisesRegex(ValueError, 'UNAVAILABLE_CAPABILITY|requires'):
                validate_values({**DEFAULTS, key: True})

    def test_payload_cannot_choose_authority(self):
        for extra in ('path', 'env', 'commands', 'socket', 'profile', 'version'):
            with self.assertRaises(ValueError):
                validate_payload({'values': DEFAULTS, extra: 'anything'})
        with self.assertRaises(ValueError):
            validate_payload({'values': {'connecteddrive_service': True}})
        with self.assertRaises(ValueError):
            decode_json('{"values": {}, "values": {}}')

    def test_persist_and_atomic_replacement(self):
        values = {**DEFAULTS, 'developer_menu': False}
        response = self.store.save({'values': values})
        self.assertEqual(response['values'], values)
        self.assertTrue(response['restart_required'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        old_inode = self.path.stat().st_ino
        self.store.save({'values': DEFAULTS})
        self.assertNotEqual(self.path.stat().st_ino, old_inode)
        self.assertEqual(SettingsStore(self.path, self.directory).load(), DEFAULTS)
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ['pending.json'])
        self.assertEqual(json.loads(self.path.read_text())['version'], 1)

    def test_known_active_not_inferred_from_saved(self):
        known = SettingsStore(self.path, self.directory, active_values=DEFAULTS)
        self.assertFalse(known.save({'values': DEFAULTS})['restart_required'])
        self.assertTrue(known.save({'values': {**DEFAULTS, 'developer_menu': False}})['restart_required'])

    def test_boot_snapshot_is_defensive_and_pending_cannot_replace_it(self):
        boot = DEFAULTS.copy()
        known = SettingsStore(self.path, self.directory, active_values=boot)
        boot['developer_menu'] = False
        initial = known.snapshot()
        self.assertEqual(initial['boot_values'], DEFAULTS)
        self.assertTrue(initial['active_known'])
        self.assertFalse(initial['pending_saved'])
        initial['boot_values']['developer_menu'] = False
        self.assertEqual(known.snapshot()['boot_values'], DEFAULTS)
        pending = {**DEFAULTS, 'developer_menu': False}
        saved = known.save({'values': pending})
        self.assertEqual(saved['boot_values'], DEFAULTS)
        self.assertEqual(saved['values'], pending)
        self.assertTrue(saved['restart_required'])
        self.assertTrue(saved['pending_saved'])
        restored = known.save({'values': DEFAULTS})
        self.assertFalse(restored['restart_required'])
        self.assertEqual(restored['boot_values'], DEFAULTS)

    def test_unknown_boot_is_never_inferred_from_pending(self):
        self.assertIsNone(self.store.snapshot()['boot_values'])
        for pending in (DEFAULTS, {**DEFAULTS, 'developer_menu': False}):
            response = self.store.save({'values': pending})
            self.assertIsNone(response['boot_values'])
            self.assertFalse(response['active_known'])
            self.assertTrue(response['pending_saved'])
            self.assertTrue(response['restart_required'])
        borrowed = SettingsStore(self.path, self.directory)
        self.assertIsNone(borrowed.snapshot()['boot_values'])

    def test_boot_values_strict_keys_types_and_dependencies(self):
        for boot in ({}, {**DEFAULTS, 'path': '/tmp/foreign'},
                     {**DEFAULTS, 'developer_menu': 1},
                     {**DEFAULTS, 'connecteddrive_availability': True}):
            with self.assertRaises(ValueError):
                SettingsStore(self.path, self.directory, active_values=boot)
        with self.assertRaises(ValueError):
            self.store.save({'values': DEFAULTS, 'boot_values': DEFAULTS})
        with self.assertRaises(ValueError):
            self.store.save({'values': DEFAULTS, 'active_values': DEFAULTS})

    def test_all_six_coding_combinations_compare_against_boot(self):
        known = SettingsStore(self.path, self.directory, active_values=DEFAULTS)
        for developer in (False, True):
            for camera, resources in ((False, False), (False, True), (True, True)):
                values = {**DEFAULTS, 'developer_menu': developer,
                          'reverse_camera': camera, 'f32_resources': resources}
                with self.subTest(values=values):
                    result = known.save({'values': values})
                    self.assertEqual(result['restart_required'], values != DEFAULTS)
                    self.assertEqual(result['boot_values'], DEFAULTS)

    def test_invalid_save_preserves_file(self):
        self.store.save({'values': DEFAULTS})
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.save({'values': {**DEFAULTS, 'bad': True}})
        self.assertEqual(self.path.read_bytes(), before)

    def test_fixed_paths_only(self):
        for path, directory in ((Path('pending.json'), self.directory),
                                (self.directory / 'nested/pending.json', self.directory),
                                (self.directory / '../escape.json', self.directory)):
            with self.assertRaises(ValueError):
                SettingsStore(path, directory)
        link = self.directory / 'alias'
        link.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(ValueError):
            SettingsStore(link / 'pending.json', link)
        os.chmod(self.directory, 0o755)
        with self.assertRaises(ValueError):
            SettingsStore(self.path, self.directory)
        os.chmod(self.directory, 0o700)

    def test_symlink_and_hardlink_and_foreign_mode_refused(self):
        target = self.directory / 'other.json'
        target.write_text('untouched')
        self.path.symlink_to(target)
        with self.assertRaises((OSError, ValueError)):
            self.store.save({'values': DEFAULTS})
        self.assertEqual(target.read_text(), 'untouched')
        self.path.unlink()  # Exact owned temp fixture.
        self.store.save({'values': DEFAULTS})
        os.link(self.path, self.directory / 'hardlink.json')
        with self.assertRaises(ValueError):
            self.store.load()

    def test_malformed_document_and_unsafe_mode(self):
        self.path.write_text('{"version":true,"values":{}}')
        self.path.chmod(0o600)
        with self.assertRaises(ValueError):
            self.store.load()
        self.path.write_text(json.dumps({'version': 1, 'values': DEFAULTS, 'path': '/tmp'}))
        with self.assertRaises(ValueError):
            self.store.load()
        self.path.write_text(json.dumps({'version': 1, 'values': DEFAULTS}))
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.store.load()

    def test_only_canonical_launch_literals(self):
        result = launch_values(DEFAULTS)
        self.assertEqual(set(result), set(LAUNCH_ENV.values()))
        self.assertLessEqual(set(result.values()), {'0', '1'})
        self.assertEqual(result['IDRIVE_VM_CONNECTEDDRIVE_MOCK'], '0')
        self.assertEqual(result['IDRIVE_VM_CONNECTEDDRIVE_AVAILABILITY_MOCK'], '0')


if __name__ == '__main__':
    unittest.main()
