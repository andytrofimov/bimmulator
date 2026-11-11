"""HTTP/control/log and real websockify integration, no VM required."""
import argparse
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('client', TOOLS / 'idrive-web-client.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def dependency_paths(env):
    names = ('NOVNC_DIR', 'WEBSOCKIFY_DIR')
    if not any(name in env for name in names):
        raise unittest.SkipTest('optional browser integration: set NOVNC_DIR and WEBSOCKIFY_DIR to local source extracts')
    if not all(env.get(name) for name in names):
        raise ValueError('explicit browser integration requires both NOVNC_DIR and WEBSOCKIFY_DIR')
    novnc, deps = (Path(env[name]) for name in names)
    for path in (novnc / 'core/rfb.js', deps / 'websockify/__init__.py'):
        if not path.is_file():
            raise ValueError(f'explicit browser integration dependency missing: {path}')
    return novnc, deps


class DependencyConfigurationTests(unittest.TestCase):
    def test_nonloopback_rejected_before_dependencies_or_bind(self):
        for host in ('0.0.0.0', '192.0.2.1', '::', 'localhost'):
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, 'loopback'):
                client.make_server(argparse.Namespace(listen=host))

    def test_nonloopback_target_rejected_before_dependencies_or_bind(self):
        for host in ('0.0.0.0', '192.0.2.1', '::1', 'localhost', '127.1'):
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, 'loopback'):
                client.make_server(argparse.Namespace(listen='127.0.0.1', vnc_host=host))

    def test_missing_optional_dependency_fails_closed(self):
        result = subprocess.run([sys.executable, '-I', '-S', str(TOOLS / 'idrive-web-client.py'),
            '--vnc-port', '5903', '--serial-log', '/unused/serial', '--novnc', '/unused/novnc'],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('missing dependency', result.stderr)
        self.assertNotIn('Browser client:', result.stdout)

    def test_unconfigured_integration_skips(self):
        with self.assertRaisesRegex(unittest.SkipTest, 'optional browser integration'):
            dependency_paths({})

    def test_explicit_invalid_configuration_fails_not_skips(self):
        for env in ({'NOVNC_DIR': ''}, {'WEBSOCKIFY_DIR': '/missing'},
                    {'NOVNC_DIR': '/missing', 'WEBSOCKIFY_DIR': '/missing'}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                dependency_paths(env)


class ClientFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        cls.novnc, cls.deps = dependency_paths(os.environ)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / 'current-serial.log'
        self.log.write_bytes(b'<script>untrusted</script>\xff\n')
        self.controller = self.root / 'controller.sock'
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(str(self.controller))
        self.sock.settimeout(0.3)
        self.addCleanup(self.sock.close)
        self.backend = socket.socket()
        self.backend.bind(('127.0.0.1', 0))
        self.backend.listen()
        self.backend.settimeout(3)
        self.addCleanup(self.backend.close)
        self.args = argparse.Namespace(deps=self.deps, novnc=self.novnc,
            listen='127.0.0.1', port=0, vnc_host='127.0.0.1',
            vnc_port=self.backend.getsockname()[1], serial_log=self.log,
            controller_socket=self.controller)
        self.server = client.make_server(self.args)
        self.server_errors = []
        self.server.handle_error = lambda request, address: self.server_errors.append(sys.exc_info()[1])
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.addCleanup(self.stop)
        self.origin = self.server.origin
        self.token = self.request('/api/status')[1]['csrf']

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.server_errors, [])

    def request(self, path, method='GET', payload=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        h = {'Host': self.server.authority}
        if method == 'POST':
            h.update({'Origin': self.origin, 'X-CSRF-Token': self.token, 'Content-Type': 'application/json'})
        h.update(headers or {})
        conn.request(method, path, body=json.dumps(payload) if payload is not None else None, headers=h)
        response = conn.getresponse()
        data = response.read()
        status = response.status
        kind = response.getheader('Content-Type')
        conn.close()
        return status, json.loads(data) if kind == 'application/json' else data


class ClientTests(ClientFixture):
    def test_client_reset_during_response_headers_and_body(self):
        original = self.server.RequestHandlerClass
        for pause_at in (1, 2):  # end_headers(), then the response body write.
            with self.subTest(write=pause_at):
                entered, release, finished = (threading.Event() for _ in range(3))
                observed = []
                class PausedHandler(original):
                    def reply(handler, *args, **kwargs):
                        writer = handler.wfile
                        class PausedWriter:
                            count = 0
                            def __getattr__(self, name):
                                return getattr(writer, name)
                            def write(self, data):
                                self.count += 1
                                if self.count == pause_at:
                                    entered.set()
                                    if not release.wait(3):
                                        raise AssertionError('reset fixture not released')
                                try:
                                    return writer.write(data)
                                except (BrokenPipeError, ConnectionResetError) as exc:
                                    observed.append(type(exc))
                                    raise
                        handler.wfile = PausedWriter()
                        try:
                            return super().reply(*args, **kwargs)
                        finally:
                            handler.wfile = writer
                            finished.set()
                self.server.RequestHandlerClass = PausedHandler
                try:
                    with socket.create_connection(('127.0.0.1', self.server.server_port), 3) as peer:
                        peer.sendall(f'GET /api/status HTTP/1.1\r\nHost: {self.server.authority}\r\n\r\n'.encode())
                        self.assertTrue(entered.wait(3))
                        peer.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                    release.set()  # Real peer RST, not an injected write exception.
                    self.assertTrue(finished.wait(3))
                    self.assertTrue(observed, 'fixture did not exercise a reset write')
                finally:
                    release.set()
                    self.server.RequestHandlerClass = original
        self.assertEqual(self.request('/api/status')[0], 200)
        self.assertEqual(self.server_errors, [])

    def test_static_and_path_boundaries(self):
        self.assertIn(b'/client.js', self.request('/')[1])
        self.assertEqual(self.request('/novnc/core/rfb.js')[0], 200)
        for path in ['/novnc/../../idrive-web-client.py', '/novnc/%2e%2e/%2e%2e/etc/passwd',
                     '/novnc/core/../core/rfb.js', '/novnc/LICENSE.txt', '/novnc/app/ui.js',
                     '/api/log?path=/etc/passwd', '/api/log?cursor=a&cursor=b', '/client.js?x=1',
                     '/api/settings', '/settings.js', '/websockify/kombi']:
            self.assertIn(self.request(path)[0], (400, 404))
        self.assertEqual(self.request('/', headers={'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.request('/api/status', headers={'Origin': 'https://evil.test'})[0], 403)

    def test_duplicate_headers_and_absolute_authority_rejected(self):
        def raw(path, headers):
            connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
            connection.putrequest('GET', path, skip_host=True)
            for name, value in [('Host', self.server.authority)] + headers:
                connection.putheader(name, value)
            connection.endheaders()
            response = connection.getresponse()
            status = response.status
            response.read()
            connection.close()
            return status
        self.assertEqual(raw('/', [('Host', self.server.authority)]), 403)
        self.assertEqual(raw('/', [('Origin', self.origin), ('Origin', self.origin)]), 403)
        self.assertEqual(raw('http://evil.test/api/status', []), 400)
        self.assertEqual(self.request('/api/control', 'POST', {'key': 'menu'},
                                      {'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(self.request('/api/control', 'POST', {'key': 'x' * 200})[0], 400)
        self.assertEqual(self.request('/api/control', 'POST', {'key': 'menu'},
                                      {'Transfer-Encoding': 'chunked'})[0], 400)
        with self.assertRaises(socket.timeout):
            self.sock.recv(8)

    def test_allowlisted_one_byte_and_failures(self):
        for key, code in client.KEYS.items():
            status, data = self.request('/api/control', 'POST', {'key': key})
            self.assertEqual(status, 200)
            self.assertFalse(data['native_transition_confirmed'])
            self.assertEqual(self.sock.recv(8), bytes([code]))
        for payload in [{'key': 1}, {'key': 'shell'}, {'key': 'menu', 'socket': '/tmp/evil'}, []]:
            self.assertEqual(self.request('/api/control', 'POST', payload)[0], 400)
        for headers in [{'Origin': 'http://evil.test'}, {'X-CSRF-Token': 'wrong'}, {'Host': 'evil.test'}, {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.request('/api/control', 'POST', {'key': 'menu'}, headers)[0], 403)
        with self.assertRaises(socket.timeout):
            self.sock.recv(8)
        self.sock.close()  # stale socket path, then missing path
        self.assertEqual(self.request('/api/control', 'POST', {'key': 'menu'})[0], 503)
        self.controller.unlink()
        self.assertFalse(self.request('/api/status')[1]['controller'])
        self.assertEqual(self.request('/api/control', 'POST', {'key': 'menu'})[0], 503)

    def test_log_actual_path_rotation_and_limit(self):
        data = self.request('/api/log')[1]
        self.assertTrue(data['available'])
        self.assertIn('<script>', data['text'])
        self.assertIn('\\xff', data['text'])
        self.assertEqual(self.request('/api/log?cursor=' + data['cursor'])[1]['text'], '')
        self.log.write_text('replacement')
        result = self.request('/api/log?cursor=' + data['cursor'])[1]
        self.assertTrue(result['reset'])
        self.assertEqual(result['text'], 'replacement')
        self.log.write_text('x' * 100000)
        self.assertEqual(len(self.request('/api/log')[1]['text']), 65536)
        self.log.unlink()
        self.assertFalse(self.request('/api/log')[1]['available'])

    def test_websocket_origin_and_real_tcp_bridge(self):
        headers = {'Upgrade': 'websocket', 'Connection': 'Upgrade', 'Sec-WebSocket-Version': '13',
                   'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==', 'Origin': 'http://evil.test'}
        self.assertEqual(self.request('/websockify', headers=headers)[0], 403)
        from websockify.websocket import WebSocket
        authority = self.server.authority
        class PortAwareWebSocket(WebSocket):
            def send_header(self, name, value):
                # Upstream test client omits nondefault port from Host.
                super().send_header(name, authority if name == 'Host' else value)
        ws = PortAwareWebSocket()
        self.addCleanup(lambda: ws.socket.close() if ws.socket else None)
        ws.connect(self.origin.replace('http:', 'ws:') + '/websockify', origin=self.origin)
        backend, _ = self.backend.accept()
        try:
            backend.sendall(b'RFB 003.008\n')
            self.assertEqual(ws.recv(), b'RFB 003.008\n')
            ws.send(b'RFB 003.008\n')
            self.assertEqual(backend.recv(12), b'RFB 003.008\n')
            backend.close()  # VM/backend disconnect must close websocket, not hang.
            ws.socket.settimeout(3)
            self.assertIsNone(ws.recv())
        finally:
            if ws.socket:
                ws.close()
            backend.close()

    def test_disabled_controller_and_cli_errors(self):
        self.args.controller_socket = None
        self.assertFalse(self.request('/api/status')[1]['controller'])
        self.assertEqual(self.request('/api/control', 'POST', {'key': 'menu'})[0], 503)
        base = [sys.executable, '-I', str(TOOLS / 'idrive-web-client.py'),
                '--vnc-host', '127.0.0.1', '--vnc-port', '5903',
                '--serial-log', str(self.log), '--novnc', str(self.novnc)]
        result = subprocess.run(base, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('missing dependency', result.stderr)
        for option, value in [('--port', '0'), ('--vnc-port', '65536')]:
            result = subprocess.run(base + [option, value], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn('ports must be', result.stderr)

    def test_invalid_dependency_path(self):
        self.args.novnc = self.root / 'absent'
        with self.assertRaisesRegex(ValueError, 'core/rfb.js'):
            client.make_server(self.args)


if __name__ == '__main__':
    unittest.main()
