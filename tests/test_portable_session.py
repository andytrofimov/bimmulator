"""Firmware-free tests of the real public composition and owned-child cleanup."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import runpy
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
launch = runpy.run_path(str(TOOLS / 'idrive6-launch.py'))
from vm_lab_settings import DEFAULTS, SettingsStore


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='id6-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {'cacheDir': str(self.root), 'modules': ['head-unit', '6wb'],
                       'display': 'gtk', 'cpuCount': 2, 'web': True, 'webPort': 18080}
        self.globals = launch['run_session'].__globals__

    def composition(self, config=None, images=True):
        captured = {}
        def owner(project, cache, config, staged, head, **options):
            captured.update(config=config, images=staged, head=head, **options)
            document = next((cache / 'sessions').glob('*/session.json'))
            captured['document'] = json.loads(document.read_text())
            captured['snapshot'] = list(document.parent.glob('boot-settings-*.json'))[0].read_bytes()
            return 0
        with patch.dict(self.globals, {'run_kombi_session': owner}):
            self.assertEqual(launch['run_session'](TOOLS.parent, self.root, config or self.config,
                self.root / 'firmware', ('gss', 'config', 'graphics') if images else None,
                (Path('/fixture/noVNC'), Path('/fixture/websockify'))), 0)
        return captured

    def test_both_ecus_browser_wiring_and_run_bound_snapshot(self):
        result = self.composition()
        command, env = result['head']
        web = result['web']
        run_id = result['document']['run_id']
        self.assertEqual(command[command.index('--run-id') + 1], run_id)
        self.assertEqual(web[web.index('--boot-run-id') + 1], run_id)
        self.assertEqual(web[web.index('--vnc-socket') + 1], env['IDRIVE_VNC_SOCKET'])
        self.assertIn('--kombi-vnc-socket', web)
        self.assertEqual(env['IDRIVE_DISPLAY'], 'none')
        self.assertEqual(env['IDRIVE_QEMU_LOADVM'], '')
        self.assertEqual(env['IDRIVE_VM_CONNECTEDDRIVE_MOCK'], '0')
        self.assertEqual(json.loads(result['snapshot'])['values'], DEFAULTS)
        self.assertRegex(result['document']['source_id'], r'^sha256:[a-f0-9]{64}$')
        self.assertEqual(result['document']['profile_name'], 'f32-x20511i-id6-light-baseline')
        for path in result['endpoints'].values():
            if isinstance(path, Path):
                self.assertLess(len(os.fsencode(path)), 104)
        self.assertFalse(Path(env['IDRIVE_VNC_SOCKET']).parent.exists())

    def test_all_six_values_reach_actual_profile_override_environment(self):
        (self.root / 'firmware' / launch['RELEASE'] / 'rootfs').mkdir(parents=True)
        runner = runpy.run_path(str(TOOLS / 'run-hmi-profile.py'))['main']
        for number, (developer, camera, resources) in enumerate(
                (d, c, r) for d in (False, True) for c, r in ((False, False), (False, True), (True, True))):
            values = {**DEFAULTS, 'developer_menu': developer, 'reverse_camera': camera, 'f32_resources': resources}
            command, env = launch['head_unit_command'](TOOLS.parent, {**self.config, 'web': False}, self.root / 'firmware' / launch['RELEASE'],
                run_id='coding-fixture-' + str(number), values=values)
            with patch.dict(os.environ, env), patch.object(sys, 'argv', command[1:]), patch('os.execvpe') as execute:
                self.assertEqual(runner(), 127)
            actual = execute.call_args.args[2]
            for key, value in (('IDRIVE_HMI_CODING_DEVELOPER_MENU', developer),
                               ('IDRIVE_HMI_CODING_CAMERA_RVC', camera), ('IDRIVE_HMI_VARIANTREGISTRY_F32', resources)):
                self.assertEqual(actual[key], str(int(value)))
            self.assertEqual(Path(actual['IDRIVE_HMI_RUN_DIR']).stat().st_mode & 0o777, 0o700)
            self.assertTrue(actual['IDRIVE_ROOT_ARCHIVE_OUTPUT'].startswith(actual['IDRIVE_HMI_RUN_DIR'] + '/'))

    def test_browser_config_rejects_types_and_cluster_only_before_spawn(self):
        file = self.root / 'config.toml'
        file.touch()
        for extra in ({'web': 1}, {'web': 'true'}, {'webPort': True}, {'webPort': 0},
                      {'webPort': 65536}, {'web': True, 'modules': ['6wb']}):
            output = json.dumps({'psdzdata': '/external/psdz', **extra})
            with self.subTest(extra=extra), patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, output)), \
                    patch('platform.system', return_value='Linux'), patch('platform.machine', return_value='x86_64'), \
                    patch('subprocess.Popen') as spawn, self.assertRaises(ValueError):
                launch['checked_config'](self.root, file, 'nix')
            spawn.assert_not_called()

    def test_nbt_only_marks_no_cluster_backend(self):
        result = self.composition({**self.config, 'modules': ['head-unit']}, images=False)
        self.assertNotIn('--kombi-vnc-socket', result['web'])
        self.assertIsNone(result['images'])

    def test_native_gui_composition_has_no_web_dependency(self):
        for display in ('gtk', 'cocoa', 'none'):
            with self.subTest(display=display):
                # Each invocation has a distinct run and archive.
                result = self.composition({**self.config, 'web': False, 'display': display})
                self.assertIsNone(result['web'])
                self.assertEqual(result['head'][1]['IDRIVE_DISPLAY'], display)

    def test_pending_values_frozen_before_owner_and_explicit_profile_precedence(self):
        private = self.root / 'settings'
        private.mkdir(mode=0o700)
        values = {**DEFAULTS, 'developer_menu': False, 'reverse_camera': False, 'f32_resources': False}
        store = SettingsStore(private / 'pending.json', private)
        store.save({'values': values})
        with patch.dict(os.environ, {'IDRIVE_HMI_CODING_DEVELOPER_MENU': '1',
                                    'IDRIVE_HMI_CODING_CAMERA_RVC': '1',
                                    'IDRIVE_HMI_VARIANTREGISTRY_F32': '1'}):
            result = self.composition()
        command = result['head'][0]
        for name in ('IDRIVE_HMI_CODING_DEVELOPER_MENU', 'IDRIVE_HMI_CODING_CAMERA_RVC',
                     'IDRIVE_HMI_VARIANTREGISTRY_F32'):
            self.assertIn(name + '=0', command)
        self.assertTrue(any(arg.endswith('/rootfs.tar.gz') for arg in command))
        store.save({'values': DEFAULTS})
        self.assertEqual(json.loads(result['snapshot'])['values'], values)
        document = next((self.root / 'sessions').glob('*/session.json'))
        self.assertEqual(document.stat().st_mode & 0o777, 0o600)
        self.assertEqual(document.parent.stat().st_mode & 0o777, 0o700)

    def test_long_unicode_cache_uses_short_private_sockets(self):
        long_cache = self.root / ('long path é' * 15)
        long_cache.mkdir()
        self.root = long_cache
        self.config['cacheDir'] = str(long_cache)
        result = self.composition()
        self.assertTrue(result['head'][1]['IDRIVE_VNC_SOCKET'].startswith('/tmp/id6-'))

    def test_unsupported_pending_rejected_without_children(self):
        private = self.root / 'settings'
        private.mkdir(mode=0o700)
        pending = private / 'pending.json'
        pending.write_text(json.dumps({'version': 1, 'values': {**DEFAULTS, 'connecteddrive_service': True}}))
        pending.chmod(0o600)
        with patch('subprocess.Popen') as spawn, self.assertRaisesRegex(ValueError, 'UNAVAILABLE_CAPABILITY'):
            launch['run_session'](TOOLS.parent, self.root, self.config, self.root, None)
        spawn.assert_not_called()

    def test_foreign_http_port_and_missing_executable_zero_spawn(self):
        with socket.socket() as foreign:
            foreign.bind(('127.0.0.1', 0))
            foreign.listen()
            config = {**self.config, 'webPort': foreign.getsockname()[1]}
            with patch.dict(os.environ, {'IDRIVE_ANGLE_SERVER': '/fixture/graphics'}), \
                    patch('shutil.which', return_value='/fixture/executable'), patch('subprocess.Popen') as spawn:
                with self.assertRaises(OSError):
                    launch['preflight'](config)
                spawn.assert_not_called()
        with patch('shutil.which', return_value=None), patch('subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'executable unavailable'):
                launch['preflight'](self.config)
            spawn.assert_not_called()

    def test_http_preflight_matches_server_after_active_close_time_wait(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            listener.listen()
            with socket.create_connection(('127.0.0.1', port), timeout=2) as peer:
                connection, _ = listener.accept()
                connection.shutdown(socket.SHUT_WR)  # The server actively closes.
                connection.close()
                self.assertEqual(peer.recv(1), b'')
        config = {**self.config, 'webPort': port}
        with patch.dict(os.environ, {'IDRIVE_ANGLE_SERVER': '/fixture/graphics'}), \
                patch('shutil.which', return_value='/fixture/executable'), patch('subprocess.Popen') as spawn:
            launch['preflight'](config)
            spawn.assert_not_called()
        with socket.socket() as restarted:
            restarted.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            restarted.bind(('127.0.0.1', port))
            restarted.listen()
            with patch.dict(os.environ, {'IDRIVE_ANGLE_SERVER': '/fixture/graphics'}), \
                    patch('shutil.which', return_value='/fixture/executable'), patch('subprocess.Popen') as spawn:
                with self.assertRaises(OSError):
                    launch['preflight'](config)  # REUSEADDR must not share a live listener.
                spawn.assert_not_called()

    def test_missing_web_dependencies_zero_spawn(self):
        with patch.dict(os.environ, {'IDRIVE_NOVNC': '/absent', 'IDRIVE_WEBSOCKIFY': '/absent'}), \
                patch('subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'browser dependencies missing'):
                launch['web_dependencies'](TOOLS.parent)
            spawn.assert_not_called()

    def test_main_invalid_browser_module_or_port_zero_spawn_and_no_stage(self):
        config = {**self.config, 'modules': ['6wb'], 'web': False, 'psdzdata': '/fixture/psdz'}
        for flags in (['--web'], ['--web-port', '0']):
            with self.subTest(flags=flags), patch.dict(launch['main'].__globals__, {
                    'checked_config': Mock(return_value=config.copy()), 'stage_kombi': Mock()}) as scope, \
                    patch.object(sys, 'argv', ['idrive6', *flags]), patch('subprocess.Popen') as spawn:
                self.assertEqual(launch['main'](), 1)
                scope['stage_kombi'].assert_not_called()
                spawn.assert_not_called()

    def test_actual_owned_child_termination_and_reap_is_bounded(self):
        child = subprocess.Popen([sys.executable, '-c',
            'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print("ready",flush=True); time.sleep(60)'],
            start_new_session=True, stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        self.assertEqual(child.stdout.readline().strip(), 'ready')
        launch['_OWNED_CHILDREN'][child] = child.pid
        started = time.monotonic()
        launch['stop_process'](child, timeout=.1)
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNotNone(child.returncode)
        child.stdout.close()

    def test_unregistered_reaped_or_substituted_identity_never_signals(self):
        foreign = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        self.addCleanup(lambda: (foreign.terminate(), foreign.wait(3)))
        with patch('os.killpg', wraps=os.killpg) as signal_group:
            with self.assertRaisesRegex(RuntimeError, 'unregistered'):
                launch['stop_process'](foreign, timeout=.01)
            with self.assertRaisesRegex(RuntimeError, 'unregistered'):
                launch['stop_process'](Mock(pid=foreign.pid), timeout=.01)
            signal_group.assert_not_called()
        child = subprocess.Popen([sys.executable, '-c', 'pass'], start_new_session=True)
        launch['_OWNED_CHILDREN'][child] = child.pid
        child.wait(3)  # An unauthorized reaper breaks the reservation contract.
        with patch('os.killpg', wraps=os.killpg) as signal_group:
            with self.assertRaisesRegex(RuntimeError, 'custody lost'):
                launch['stop_process'](child, timeout=.01)
            original = child.pid
            child.pid = foreign.pid  # Simulate a substituted/reused numeric PGID.
            try:
                with self.assertRaisesRegex(RuntimeError, 'custody lost'):
                    launch['stop_process'](child, timeout=.01)
            finally:
                child.pid = original
                launch['_OWNED_CHILDREN'].pop(child)
            signal_group.assert_not_called()
        self.assertIsNone(foreign.poll())

    def test_external_waitpid_loss_fails_closed_before_signal(self):
        child = subprocess.Popen([sys.executable, '-c', 'pass'], start_new_session=True)
        launch['_OWNED_CHILDREN'][child] = child.pid
        _, status = os.waitpid(child.pid, 0)  # Leave Popen.returncode unset intentionally.
        with patch('os.killpg', wraps=os.killpg) as signal_group:
            with self.assertRaisesRegex(RuntimeError, 'reaped outside'):
                launch['stop_process'](child, timeout=.01)
            signal_group.assert_not_called()
        child.returncode = os.waitstatus_to_exitcode(status)
        launch['_OWNED_CHILDREN'].pop(child)

    def test_early_entry_exit_reserves_identity_and_grants_descendants_real_grace(self):
        receipt = self.root / 'receipt.json'
        ready = self.root / 'ready'
        payload = self.root / 'payload.py'
        payload.write_text("""import signal,time,sys
from pathlib import Path
def stop(*args):
    time.sleep(.2)
    Path(sys.argv[1]).write_text('payload cleanup complete')
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
print('payload-ready',flush=True)
while True: time.sleep(1)
""")
        custodian = self.root / 'custodian.py'
        custodian.write_text("""import json,signal,subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]+'.payload'],stdout=subprocess.PIPE,text=True)
assert child.stdout.readline().strip()=='payload-ready'
def stop(*args):
    status=child.wait(timeout=2)
    Path(sys.argv[2]).write_text(json.dumps({'reaped':status,'payload_pid':child.pid}))
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
Path(sys.argv[3]).write_text(str(child.pid))
while True: time.sleep(1)
""")
        entry = subprocess.Popen([sys.executable, '-c',
            'import subprocess,sys; subprocess.Popen(sys.argv[1:])', sys.executable,
            str(custodian), str(payload), str(receipt), str(ready)], start_new_session=True)
        launch['_OWNED_CHILDREN'][entry] = entry.pid
        self.addCleanup(lambda: launch['stop_process'](entry, timeout=.3)
                        if entry in launch['_OWNED_CHILDREN'] else None)
        deadline = time.monotonic() + 4
        while not ready.is_file() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(ready.is_file())
        self.assertEqual(launch['child_status'](entry), 0)
        self.assertIsNone(entry.returncode, 'monitor must not reap the exited entry')
        self.assertEqual(launch['child_status'](entry), 0, 'entry remains kernel-waitable')
        started = time.monotonic()
        with patch('os.killpg', wraps=os.killpg) as signals:
            launch['stop_process'](entry, timeout=.6)
        self.assertGreaterEqual(time.monotonic() - started, .55)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(json.loads(receipt.read_text())['reaped'], 0)
        self.assertEqual(Path(str(receipt)+'.payload').read_text(), 'payload cleanup complete')
        self.assertEqual([call.args[1] for call in signals.call_args_list], [signal.SIGTERM, signal.SIGKILL])
        self.assertEqual(entry.returncode, 0)
        self.assertNotIn(entry, launch['_OWNED_CHILDREN'])

    def test_darwin_nonterminal_waitid_result_does_not_end_session(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        launch['_OWNED_CHILDREN'][child] = child.pid
        try:
            stopped = Mock(si_pid=child.pid, si_code=os.CLD_STOPPED, si_status=signal.SIGSTOP)
            with patch('os.waitid', return_value=stopped):
                self.assertIsNone(launch['child_status'](child))
            self.assertIsNone(child.returncode)
        finally:
            launch['stop_process'](child, timeout=.01)

    def test_foreign_sigchld_reaper_or_auto_reap_fails_before_spawn(self):
        for handler in (signal.SIG_IGN, lambda *args: None):
            with self.subTest(handler=handler), patch('signal.getsignal', return_value=handler), \
                    patch('subprocess.Popen') as spawn:
                with self.assertRaisesRegex(ValueError, 'sole child reaping'):
                    launch['preflight'](self.config)
                spawn.assert_not_called()

    def test_waitid_capability_absence_fails_before_any_spawn(self):
        with patch.object(os, 'waitid', None), patch('subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'waitid/WNOWAIT'):
                launch['preflight'](self.config)
            spawn.assert_not_called()

    def test_owner_reaps_all_children_for_each_exit_and_partial_spawn(self):
        for fail in ('head unit', 'browser', '6WB', 'vehicle simulator', 'partial', 'interrupt'):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory(prefix='id6-owner-') as directory:
                run = Path(directory)
                with (run / 'vehicle.ram').open('wb') as stream:
                    stream.truncate(launch['RAM_SIZE'])
                with socket.socket(socket.AF_UNIX) as qmp:
                    qmp.bind(str(run / 'qmp.sock'))
                    names = ['6WB', 'vehicle simulator', 'head unit', 'browser']
                    children = []
                    def spawn(*args, **kwargs):
                        name = names[len(children)]
                        if fail == 'partial' and name == 'head unit':
                            raise OSError('fixture partial spawn')
                        if fail == 'interrupt' and name == 'head unit':
                            # Cancellation at the Popen/registration boundary.
                            signal.raise_signal(signal.SIGTERM)
                        child = Mock(pid=900000000 + len(children))
                        child.poll.return_value = 3 if name == fail else None
                        children.append(child)
                        return child
                    stopped = []
                    with patch('tempfile.mkdtemp', return_value=directory), \
                            patch('subprocess.Popen', side_effect=spawn), \
                            patch.dict(launch['run_kombi_session'].__globals__, {'stop_process': stopped.append, 'child_status': lambda process: process.poll()}):
                        with self.assertRaises((RuntimeError, OSError, KeyboardInterrupt)):
                            launch['run_kombi_session'](TOOLS.parent, self.root, self.config,
                                ('gss', 'config', 'graphics'), (['fake-nbt'], {}),
                                web=['fake-web'], endpoints={'kombi_qmp': run / 'qmp.sock',
                                                            'kombi_vnc': run / 'kombi.vnc'})
                    self.assertEqual(stopped, list(reversed(children)))

    def test_kombi_startup_timeout_reaps_entry(self):
        child = Mock()
        child.poll.return_value = None
        stopped = []
        # Absolute startup deadline, not a count reset by activity.
        with patch('subprocess.Popen', return_value=child), \
                patch.dict(launch['run_kombi_session'].__globals__, {'stop_process': stopped.append, 'child_status': lambda process: process.poll()}), \
                patch('time.monotonic', side_effect=[0, 21]):
            with self.assertRaisesRegex(RuntimeError, '6WB failed to start'):
                launch['run_kombi_session'](TOOLS.parent, self.root, self.config, ('g', 'c', 'd'), None)
        self.assertEqual(stopped, [child])

    def test_real_main_staging_composition_and_four_fake_children_reaped(self):
        # Exercise main -> staging selection -> run_session -> real owner/Popen.
        # Only the external firmware operations and child executables are replaced.
        fake = self.root / 'child.py'
        fake.write_text('''import os,socket,sys,time
from pathlib import Path
mode,root,ram,qmp=sys.argv[1:]
root=Path(root)
if mode=='6WB':
    with open(ram,'wb') as stream: stream.truncate(64*1024*1024)
    listener=socket.socket(socket.AF_UNIX); listener.bind(qmp); listener.listen()
(root/(mode+'.pid')).write_text(str(os.getpid()))
if mode=='browser':
    deadline=time.monotonic()+4
    while len(list(root.glob('*.pid')))<4 and time.monotonic()<deadline: time.sleep(.01)
    sys.exit(7)
time.sleep(60)
''')
        real_popen = subprocess.Popen
        children, commands = [], []
        names = ['6WB', 'simulator', 'head', 'browser']
        def spawn(command, **options):
            mode = names[len(children)]
            commands.append(command)
            ram = command[command.index('--vehicle-ram') + 1] if mode == '6WB' else '-'
            qmp = command[command.index('--qmp-socket') + 1] if mode == '6WB' else '-'
            child = real_popen([sys.executable, str(fake), mode, str(self.root), ram, qmp], **options)
            children.append(child)
            return child
        config = {**self.config, 'psdzdata': str(self.root / 'external-psdz')}
        with socket.socket() as port:
            port.bind(('127.0.0.1', 0))
            config['webPort'] = port.getsockname()[1]
        old_term = signal.getsignal(signal.SIGTERM)
        try:
            with patch.dict(launch['main'].__globals__, {
                    'checked_config': Mock(return_value=config),
                    'verify_packages': Mock(return_value=({}, {})),
                    'stage': Mock(return_value=self.root / 'firmware'),
                    'stage_kombi': Mock(return_value=('gss', 'config', 'graphics')),
                    'web_dependencies': Mock(return_value=(Path('/fixture/novnc'), Path('/fixture/websockify')))}), \
                    patch.dict(os.environ, {'IDRIVE_ANGLE_SERVER': '/fixture/graphics', 'IDRIVE_SOURCE_ROOT': str(TOOLS.parent)}), \
                    patch('shutil.which', return_value='/fixture/executable'), \
                    patch.object(sys, 'argv', ['idrive6', '--web']), patch('subprocess.Popen', side_effect=spawn):
                self.assertEqual(launch['main'](), 1)
        finally:
            signal.signal(signal.SIGTERM, old_term)
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait(3)
        self.assertEqual(len(children), 4)
        self.assertTrue(all(child.returncode is not None for child in children))
        self.assertIn('--vnc-socket', commands[0])
        self.assertIn('--kombi-vnc-socket', commands[3])
        self.assertIn('--run-id', commands[2])
        self.assertEqual(commands[0][commands[0].index('--vnc-socket') + 1],
                         commands[3][commands[3].index('--kombi-vnc-socket') + 1])

    def test_native_nbt_only_owner_normal_exit(self):
        child = Mock()
        child.poll.return_value = 0
        stopped = []
        with patch('subprocess.Popen', return_value=child) as spawn, \
                patch.dict(launch['run_kombi_session'].__globals__, {'stop_process': stopped.append, 'child_status': lambda process: process.poll()}):
            self.assertEqual(launch['run_kombi_session'](TOOLS.parent, self.root, self.config,
                                                       None, (['fake-nbt'], {})), 0)
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertEqual(stopped, [child])


class KombiSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('probe_fixture', TOOLS / 'kombi-gss-probe.py')
        cls.probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.probe)

    def test_run_owned_unix_validation(self):
        with tempfile.TemporaryDirectory(prefix='id6-probe-') as directory:
            root = Path(directory)
            path = root / 'cluster.vnc'
            self.assertEqual(self.probe.validate_vnc_socket(path), path)
            for invalid in (Path('relative'), root / ('é' * 70), root / 'bad,option'):
                with self.assertRaises((ValueError, OSError)):
                    self.probe.validate_vnc_socket(invalid)
            path.touch()
            with self.assertRaises(ValueError):
                self.probe.validate_vnc_socket(path)
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                self.probe.validate_vnc_socket(root / 'other')
            root.chmod(0o700)

    def test_invalid_vnc_mode_refuses_before_image_or_spawn(self):
        with tempfile.TemporaryDirectory(prefix='id6-probe-') as directory, patch('subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'requires live'):
                self.probe.run_probe('fake', b'not-firmware', Path(directory) / 'log',
                                     vnc_socket=Path(directory) / 'cluster.vnc')
            spawn.assert_not_called()

    def test_actual_probe_wires_fixed_unix_cluster_display(self):
        with tempfile.TemporaryDirectory(prefix='id6-probe-') as directory:
            root = Path(directory)
            process = Mock(stdin=None, stdout=None)
            process.poll.return_value = 0
            process.wait.return_value = 0
            with patch.object(self.probe, 'boot_image', return_value=b'synthetic'), \
                    patch('subprocess.run') as assembler, patch('subprocess.Popen', return_value=process) as spawn:
                self.probe.run_probe('fixture-qemu', b'synthetic', root / 'log',
                    config=root / 'config', graphics_data=root / 'graphics', kss_replay=True,
                    rpm_ram=root / 'ram', vnc_socket=root / 'cluster.vnc')
            command = spawn.call_args.args[0]
            self.assertEqual(command[command.index('-vnc') + 1], f'unix:{root}/cluster.vnc,display=cluster')
            self.assertEqual(command[command.index('-display') + 1], 'none')
            self.assertEqual(assembler.call_count, 2)
            process.wait.assert_called()

    def test_actual_probe_custodian_reaps_qemu_on_sigterm(self):
        # Actual public run_probe, with synthetic image preparation only. The fake
        # QEMU is an ordinary sleeping host child; no firmware or emulator runs.
        with tempfile.TemporaryDirectory(prefix='id6-custody-') as directory:
            root = Path(directory)
            fake = root / 'fake-qemu'
            pid_file = root / 'child.pid'
            fake.write_text('#!' + sys.executable + '\nimport os,time\nfrom pathlib import Path\n'
                            + f'Path({str(pid_file)!r}).write_text(str(os.getpid()))\ntime.sleep(60)\n')
            fake.chmod(0o700)
            harness = root / 'harness.py'
            harness.write_text('import importlib.util,signal,sys\nfrom pathlib import Path\n'
                + f'sys.path.insert(0,{str(TOOLS)!r})\n'
                + f's=importlib.util.spec_from_file_location("probe",{str(TOOLS / "kombi-gss-probe.py")!r})\n'
                + 'm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n'
                + 'm.boot_image=lambda *a,**k: b"synthetic"\n'
                + 'signal.signal(signal.SIGTERM,m.interrupt_probe)\n'
                + f'm.run_probe({str(fake)!r},b"synthetic",Path({str(root / "log")!r}),rpm_ram=Path({str(root / "vehicle.ram")!r}))\n')
            wrapper = subprocess.Popen([sys.executable, str(harness)], start_new_session=True,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self.addCleanup(lambda: (wrapper.kill(), wrapper.wait(3)) if wrapper.poll() is None else None)
            deadline = time.monotonic() + 5
            while not pid_file.exists() and wrapper.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(pid_file.exists())
            child_pid = int(pid_file.read_text())
            wrapper.terminate()
            wrapper.wait(4)
            wrapper.stderr.close()
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)


if __name__ == '__main__':
    unittest.main()
