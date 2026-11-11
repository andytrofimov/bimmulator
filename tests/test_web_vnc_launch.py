"""Execute the actual firmware-free VNC validation and argument source contract.

This does not start QEMU or qualify a native guest/host renderer.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'run-emulator.sh').read_text()
PREFIX = SOURCE[:SOURCE.index('if [[ -z "${IDRIVE_ROOTFS_TREE:-}"')]
START = SOURCE.index('if [[ -n "${IDRIVE_VNC:-}" ]]; then', SOURCE.index('QEMU_ARGS='))
DISPLAY = SOURCE[START:SOURCE.index('\n# The graphics profile', START)]


class VNCLaunchTests(unittest.TestCase):
    def invoke(self, value=None, profile='omap5-graphics', display=None, unix_path=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith('IDRIVE_')}
        env['IDRIVE_EMULATOR_PROFILE'] = profile
        if value is not None:
            env['IDRIVE_VNC'] = value
        if display is not None:
            env['IDRIVE_DISPLAY'] = display
        if unix_path is not None:
            env['IDRIVE_VNC_SOCKET'] = str(unix_path)
        # Execute unchanged source sections in one shell, excluding all firmware,
        # build and process launch code. Preserve array boundaries via NULs.
        script = PREFIX + '\nQEMU_ARGS=()\n' + DISPLAY + '\nprintf "%s\\0" "${QEMU_ARGS[@]}"\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'contract.sh'
            path.write_text(script)
            result = subprocess.run(['bash', str(path)], env=env,
                                    capture_output=True, timeout=5)
        return result, result.stdout.rstrip(b'\0').split(b'\0') if result.stdout.rstrip(b'\0') else []

    def test_default_display_contract_unchanged(self):
        for profile, expected in [('omap5', []), ('omap5-graphics', []),
                                  ('vexpress', [b'-display', b'none'])]:
            with self.subTest(profile=profile):
                result, args = self.invoke(profile=profile)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(args, expected)

    def test_loopback_vnc_exact_array_arguments(self):
        for number in ('0', '1', '3', '00003', '59635'):
            with self.subTest(number=number):
                result, args = self.invoke('127.0.0.1:' + number, display='none')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(args, [b'-vnc', ('127.0.0.1:' + number).encode(),
                                        b'-display', b'none'])

    def test_private_unix_vnc_actual_validation_and_arguments(self):
        with tempfile.TemporaryDirectory(prefix='id6-vnc-') as directory:
            root = Path(directory)
            path = root / 'nbt.vnc'
            result, args = self.invoke(display='none', unix_path=path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(args, [b'-vnc', os.fsencode('unix:' + str(path)), b'-display', b'none'])
            for invalid in (Path('relative'), root / ('é' * 70), root / 'bad,option'):
                result, _ = self.invoke(unix_path=invalid)
                self.assertNotEqual(result.returncode, 0)
            path.touch()
            result, _ = self.invoke(unix_path=path)
            self.assertNotEqual(result.returncode, 0)
            result, _ = self.invoke('127.0.0.1:1', unix_path=root / 'other')
            self.assertNotEqual(result.returncode, 0)

    def test_invalid_listener_rejected_before_any_firmware_work(self):
        invalid = ['0.0.0.0:3', ':3', 'localhost:3', '[::1]:3', '127.0.0.2:3',
                   '127.0.0.1:-1', '127.0.0.1:59636', '127.0.0.1:9999999999',
                   '127.0.0.1:3,password=on', '127.0.0.1:3,reverse=on',
                   'unix:/tmp/vnc.sock', '127.0.0.1:3\n', '127.0.0.1:$(id)']
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'must-not-be-created'
            for value in invalid:
                with self.subTest(value=value):
                    result = subprocess.run(['bash', str(ROOT / 'run-emulator.sh')],
                        env={**os.environ, 'IDRIVE_VNC': value, 'IDRIVE_CACHE_DIR': str(cache)},
                        capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn(b'IDRIVE_VNC must be', result.stderr)
                    self.assertFalse(cache.exists())


if __name__ == '__main__':
    unittest.main()
