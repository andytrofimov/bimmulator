"""Owned-host HTTP and websocket coverage for displays and pending settings."""
import argparse
import http.client
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest


TOOLS = Path(__file__).resolve().parents[1] / 'tools'
import sys
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('display_client', TOOLS / 'idrive-web-client.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

KEYS = {'connecteddrive_service', 'connecteddrive_availability',
        'developer_menu', 'reverse_camera', 'f32_resources'}


class DisplaySettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_idrive_web_client import dependency_paths
        cls.novnc, cls.deps = dependency_paths(os.environ)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = self.root / 'settings.json'
        self.unix_path = self.root / 'kombi.sock'
        self.unix = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(self.unix.close)
        self.unix.bind(str(self.unix_path))
        self.unix.listen()
        self.unix.settimeout(3)
        self.tcp = socket.socket()
        self.addCleanup(self.tcp.close)
        self.tcp.bind(('127.0.0.1', 0))
        self.tcp.listen()
        self.tcp.settimeout(3)
        self.args = argparse.Namespace(
            deps=self.deps, novnc=self.novnc, listen='127.0.0.1', port=0,
            vnc_host='127.0.0.1', vnc_port=self.tcp.getsockname()[1],
            serial_log=self.root / 'serial.log', controller_socket=None,
            kombi_vnc_socket=self.unix_path, settings_file=self.settings)
        self.server = client.make_server(self.args)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.origin = self.server.origin
        self.token = self.request('/api/status')[1]['csrf']

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())

    def request(self, path, method='GET', body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        self.addCleanup(connection.close)
        fields = {'Host': self.server.authority}
        if method == 'POST':
            fields.update({'Origin': self.origin, 'X-CSRF-Token': self.token,
                           'Content-Type': 'application/json'})
        fields.update(headers or {})
        if isinstance(body, dict) or isinstance(body, list):
            body = json.dumps(body)
        connection.request(method, path, body=body, headers=fields)
        response = connection.getresponse()
        data = response.read()
        if response.getheader('Content-Type') == 'application/json':
            data = json.loads(data)
        connection.close()
        return response.status, data

    def values(self):
        return self.request('/api/settings')[1]['values']

    def ws(self, route):
        from websockify.websocket import WebSocket
        authority = self.server.authority
        class PortAwareWebSocket(WebSocket):
            def send_header(self, name, value):
                super().send_header(name, authority if name == 'Host' else value)
        ws = PortAwareWebSocket()
        self.addCleanup(lambda: ws.socket.close() if ws.socket else None)
        ws.connect(self.origin.replace('http:', 'ws:') + route, origin=self.origin)
        return ws

    def test_assets_and_whitelist(self):
        for path in ('/settings.js', '/settings.css'):
            with self.subTest(path=path):
                status, content = self.request(path)
                self.assertEqual(status, 200)
                self.assertGreater(len(content), 0)
                self.assertEqual(self.request(path + '?x=1')[0], 404)
        for path in ('/settings.json', '/settings.js/extra', '/api/settings?x=1'):
            self.assertEqual(self.request(path)[0], 404)

    def test_settings_defaults_and_groups(self):
        status, data = self.request('/api/settings')
        self.assertEqual(status, 200)
        self.assertEqual(set(data['values']), KEYS)
        self.assertEqual(set(data['schema']), KEYS)
        self.assertEqual({item['id'] for item in data['groups']}, {'mocks', 'coding'})
        self.assertFalse(data['values']['connecteddrive_service'])
        self.assertFalse(data['values']['connecteddrive_availability'])
        self.assertFalse(data['restart_required'])
        self.assertEqual(data['application'], 'next_vm_start')
        self.assertFalse(self.settings.exists())

    def start_boot_server(self, values=None):
        run_id = 'test-run-01'
        path = self.root / f'boot-settings-{run_id}.json'
        if values is not None:
            path.write_text(json.dumps({'version': 1, 'values': values}))
            path.chmod(0o600)
        self.stop_server()
        self.args.boot_settings_file = path
        self.args.boot_run_id = run_id
        self.server = client.make_server(self.args)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.origin = self.server.origin
        self.token = self.request('/api/status')[1]['csrf']
        return path

    def test_boot_values_diff_and_restore(self):
        boot = {key: not key.startswith('connecteddrive_') for key in KEYS}
        pending = {key: False for key in KEYS}
        self.settings.write_text(json.dumps({'version': 1, 'values': pending}))
        self.settings.chmod(0o600)
        path = self.start_boot_server(boot)
        original = path.read_bytes()
        status, data = self.request('/api/settings')
        self.assertEqual(status, 200)
        self.assertEqual(data['values'], pending)
        self.assertEqual(data['boot_values'], boot)
        self.assertTrue(data['active_known'])
        self.assertTrue(data['pending_saved'])
        self.assertTrue(data['restart_required'])
        self.assertEqual(data['boot_run_id'], 'test-run-01')
        data['boot_values']['developer_menu'] = False
        self.assertEqual(self.request('/api/settings')[1]['boot_values'], boot)
        status, saved = self.request('/api/settings', 'POST', {'values': boot})
        self.assertEqual(status, 200)
        self.assertFalse(saved['restart_required'])
        self.assertTrue(saved['pending_saved'])
        self.assertEqual(saved['boot_values'], boot)
        self.assertEqual(saved['boot_run_id'], 'test-run-01')
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.request('/api/settings')[1]['values'], boot)

    def test_boot_metadata_cannot_be_injected(self):
        boot = {key: not key.startswith('connecteddrive_') for key in KEYS}
        path = self.start_boot_server(boot)
        original = path.read_bytes()
        for name, value in (('boot_values', {key: False for key in KEYS}),
                            ('boot_run_id', 'forged'), ('active_known', True)):
            self.assertEqual(self.request('/api/settings', 'POST',
                                          {'values': boot, name: value})[0], 400)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.request('/api/settings')[1]['boot_values'], boot)
        self.assertFalse(self.settings.exists())

    def test_unknown_boot_remains_unknown_after_save(self):
        data = self.request('/api/settings')[1]
        self.assertFalse(data['active_known'])
        self.assertIsNone(data['boot_values'])
        self.assertIsNone(data['boot_run_id'])
        self.assertFalse(data['pending_saved'])
        status, saved = self.request('/api/settings', 'POST', {'values': data['values']})
        self.assertEqual(status, 200)
        self.assertFalse(saved['active_known'])
        self.assertIsNone(saved['boot_values'])
        self.assertIsNone(saved['boot_run_id'])
        self.assertTrue(saved['pending_saved'])
        self.assertFalse(self.request('/api/settings')[1]['active_known'])

    def test_boot_construction_rejects_untrusted_snapshots(self):
        run = 'owned-run'
        path = self.root / f'boot-settings-{run}.json'
        args = argparse.Namespace(**vars(self.args), boot_settings_file=path, boot_run_id=run)
        with self.assertRaises((ValueError, OSError)):
            client.make_server(args)  # Missing, never defaults.
        args.boot_run_id = 'other-run'
        with self.assertRaises((ValueError, OSError)):
            client.make_server(args)
        args.boot_run_id = '../unsafe'
        with self.assertRaises((ValueError, OSError)):
            client.make_server(args)
        args.boot_run_id = run
        args.settings_file = None
        with self.assertRaises((ValueError, OSError)):
            client.make_server(args)
        args.settings_file = self.settings
        target = self.root / 'target.json'
        target.write_text(json.dumps({'version': 1, 'values': {key: True for key in KEYS}}))
        target.chmod(0o600)
        path.symlink_to(target)
        with self.assertRaises((ValueError, OSError)):
            client.make_server(args)
        path.unlink()
        os.link(target, path)
        with self.assertRaises((ValueError, OSError)):
            client.make_server(args)
        path.unlink()
        path.write_text('{broken')
        path.chmod(0o600)
        with self.assertRaises((ValueError, OSError)):
            client.make_server(args)

    def test_settings_labels_are_english(self):
        data = self.request('/api/settings')[1]
        self.assertEqual([group['label'] for group in data['groups']], ['Mocks', 'Coding'])
        for group in data['groups']:
            self.assertTrue(group['label'].isascii())
            self.assertNotRegex(group['submenu'], '[\\u0400-\\u04ff]')
        for field in data['schema'].values():
            self.assertTrue(field['label'].isascii())
            self.assertNotRegex(field['label'], '[\\u0400-\\u04ff]')

    def test_display_availability(self):
        displays = self.request('/api/status')[1]['displays']
        self.assertTrue(displays['idrive']['available'])
        self.assertTrue(displays['kombi']['available'])
        self.unix.close()
        self.unix_path.unlink()
        self.assertFalse(self.request('/api/status')[1]['displays']['kombi']['available'])

    def test_post_security(self):
        payload = {'values': self.values()}
        for headers in ({'Origin': 'http://evil.test'}, {'Origin': ''},
                        {'X-CSRF-Token': 'wrong'}, {'Host': 'evil.test'},
                        {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('/api/settings', 'POST', payload, headers)[0], 403)
        self.assertFalse(self.settings.exists())

    def test_reject_payload_authority_and_nonwhitelisted_values(self):
        values = self.values()
        invalid = [dict(values, extra=True), dict(values, developer_menu=1),
                   {k: v for k, v in values.items() if k != 'developer_menu'},
                   dict(values, connecteddrive_service=False, connecteddrive_availability=True)]
        for value in invalid:
            self.assertEqual(self.request('/api/settings', 'POST', {'values': value})[0], 400)
        for payload in ({'values': values, 'path': str(self.root / 'evil')},
                        {'values': values, 'settings_file': str(self.root / 'evil')},
                        {'path': str(self.root / 'evil')}, []):
            self.assertEqual(self.request('/api/settings', 'POST', payload)[0], 400)
        self.assertFalse((self.root / 'evil').exists())
        self.assertFalse(self.settings.exists())

    def test_valid_save_is_fixed_and_persistent(self):
        values = self.values()
        values.update(developer_menu=False)
        status, saved = self.request('/api/settings', 'POST', {'values': values})
        self.assertEqual(status, 200)
        self.assertEqual(saved['values'], values)
        self.assertTrue(saved['restart_required'])
        self.assertEqual(self.request('/api/settings')[1]['values'], values)
        self.assertEqual(json.loads(self.settings.read_text())['values'], values)
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o600)

    def test_unsupported_mocks_fail_closed(self):
        for key in ('connecteddrive_service', 'connecteddrive_availability'):
            values = self.values()
            values[key] = True
            self.assertEqual(self.request('/api/settings', 'POST', {'values': values})[0], 400)
        self.assertFalse(self.settings.exists())

    def test_malformed_duplicate_and_oversize(self):
        bodies = ['{', '{"values":{},"values":{}}',
                  '{"values":{"developer_menu":true,"developer_menu":false}}',
                  'x' * 4097, '\ud800']
        for body in bodies[:-1]:
            with self.subTest(body=body[:50]):
                self.assertEqual(self.request('/api/settings', 'POST', body)[0], 400)
        self.assertEqual(self.request('/api/settings', 'POST', b'\xff')[0], 400)
        self.assertEqual(self.request('/api/settings', 'POST', '{}',
                                      {'Content-Type': 'text/plain'})[0], 400)
        self.assertFalse(self.settings.exists())

    def test_duplicate_content_length(self):
        with socket.create_connection(('127.0.0.1', self.server.server_port), timeout=3) as sock:
            request = (f'POST /api/settings HTTP/1.1\r\nHost: {self.server.authority}\r\n'
                       f'Origin: {self.origin}\r\nX-CSRF-Token: {self.token}\r\n'
                       'Content-Type: application/json\r\nContent-Length: 2\r\n'
                       'Content-Length: 2\r\nConnection: close\r\n\r\n{}')
            sock.sendall(request.encode())
            self.assertIn(b' 400 ', sock.recv(1024).split(b'\r\n')[0])
        self.assertFalse(self.settings.exists())

    def test_configured_settings_unavailable(self):
        self.settings.write_text('not json')
        self.settings.chmod(0o600)
        self.assertEqual(self.request('/api/settings')[0], 503)
        self.assertEqual(self.request('/api/settings', 'POST',
                                     {'values': {key: False for key in KEYS}})[0], 400)
        self.assertEqual(self.settings.read_text(), 'not json')
        self.settings.unlink()
        self.settings.symlink_to(self.root / 'missing')
        self.assertEqual(self.request('/api/settings')[0], 503)
        self.assertEqual(self.request('/api/settings', 'POST',
                                     {'values': {key: False for key in KEYS}})[0], 503)
        self.assertFalse((self.root / 'missing').exists())

    def test_kombi_unix_bridge_does_not_mutate_idrive(self):
        original = (self.server.target_host, self.server.target_port, self.server.unix_target)
        ws = self.ws('/websockify/kombi')
        peer, _ = self.unix.accept()
        try:
            peer.settimeout(3)
            peer.sendall(b'RFB 003.008\n')
            self.assertEqual(ws.recv(), b'RFB 003.008\n')
            ws.send(b'RFB 003.008\n')
            self.assertEqual(peer.recv(12), b'RFB 003.008\n')
            self.assertEqual((self.server.target_host, self.server.target_port,
                              self.server.unix_target), original)
            idrive = self.ws('/websockify')
            tcp_peer, _ = self.tcp.accept()
            try:
                tcp_peer.settimeout(3)
                tcp_peer.sendall(b'RFB 003.008\n')
                self.assertEqual(idrive.recv(), b'RFB 003.008\n')
            finally:
                idrive.close()
                tcp_peer.close()
        finally:
            ws.close()
            peer.close()
        self.assertEqual((self.server.target_host, self.server.target_port,
                          self.server.unix_target), original)

    def test_two_unix_targets_remain_isolated_with_simultaneous_connections(self):
        nbt_path = self.root / 'nbt.sock'
        with socket.socket(socket.AF_UNIX) as nbt:
            nbt.bind(str(nbt_path))
            nbt.listen()
            nbt.settimeout(3)
            self.stop_server()
            self.args.vnc_socket = nbt_path
            self.args.vnc_port = None
            self.server = client.make_server(self.args)
            self.thread = threading.Thread(target=self.server.serve_forever)
            self.thread.start()
            self.origin = self.server.origin
            first = self.ws('/websockify')
            second = self.ws('/websockify/kombi')
            nbt_peer, _ = nbt.accept()
            cluster_peer, _ = self.unix.accept()
            try:
                for peer in (nbt_peer, cluster_peer):
                    peer.settimeout(3)
                nbt_peer.sendall(b'NBT-only')
                cluster_peer.sendall(b'CLUSTER-only')
                self.assertEqual(first.recv(), b'NBT-only')
                self.assertEqual(second.recv(), b'CLUSTER-only')
                first.send(b'touch')
                second.send(b'fixture')
                self.assertEqual(nbt_peer.recv(32), b'touch')
                self.assertEqual(cluster_peer.recv(32), b'fixture')
                self.assertEqual(self.server.unix_target, str(nbt_path))
                self.assertIsNone(self.server.target_port)
            finally:
                first.close()
                second.close()
                nbt_peer.close()
                cluster_peer.close()

    def test_unknown_and_query_websocket_routes(self):
        headers = {'Upgrade': 'websocket', 'Connection': 'Upgrade',
                   'Sec-WebSocket-Version': '13',
                   'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
                   'Origin': self.origin}
        for route in ('/websockify/unknown', '/websockify?target=other',
                      '/websockify/kombi?target=other'):
            with self.subTest(route=route):
                self.assertEqual(self.request(route, headers=headers)[0], 404)
        self.assertIsNone(self.server.unix_target)


if __name__ == '__main__':
    unittest.main()
