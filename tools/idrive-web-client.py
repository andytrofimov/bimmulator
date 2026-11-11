#!/usr/bin/env python3
"""Minimal offline noVNC client and fixed-path native controller/log API."""
import argparse
import ipaddress
import json
import mimetypes
from pathlib import Path
import secrets
import socket
import stat
import sys
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, unquote

ASSETS = Path(__file__).with_name('web-client')
KEYS = {'menu': 1, 'back': 2, 'options': 3, 'media': 4, 'telephone': 6,
        'navigation': 7, 'ok': 8, 'up': 9, 'down': 10, 'left': 11,
        'right': 12, 'clockwise': 13, 'counterclockwise': 14, 'voice': 17}


def controller_available(path):
    try:
        return path is not None and stat.S_ISSOCK(path.stat().st_mode)
    except OSError:
        return False


def make_server(args):
    try:
        address = ipaddress.IPv4Address(args.listen)
    except ipaddress.AddressValueError as exc:
        raise ValueError('--listen must be a numeric IPv4 loopback address') from exc
    if not address.is_loopback:
        raise ValueError('--listen must be a loopback address; remote exposure is unsupported')
    try:
        backend = ipaddress.IPv4Address(args.vnc_host)
    except ipaddress.AddressValueError as exc:
        raise ValueError('--vnc-host must be a numeric IPv4 loopback address') from exc
    if not backend.is_loopback:
        raise ValueError('--vnc-host must be a loopback address')
    if not 1 <= args.vnc_port <= 65535 or not 0 <= args.port <= 65535:
        raise ValueError('ports must be in 1..65535 (HTTP port 0 selects an ephemeral port)')
    if args.deps:
        sys.path.insert(0, str(args.deps.resolve()))
    try:
        from websockify.websocketproxy import ProxyRequestHandler
        from web_serial_log import SerialLogTail
    except ImportError as exc:
        raise ValueError(f'missing dependency: {exc}; see tools/web-client/README.md') from exc
    novnc = args.novnc.resolve()
    if not (novnc / 'core/rfb.js').is_file():
        raise ValueError('--novnc must contain core/rfb.js')
    tail = SerialLogTail(args.serial_log)
    tail_lock = threading.Lock()
    token = secrets.token_urlsafe(32)
    class Handler(ProxyRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def boundary(self, origin_required=False):
            # Accept origin-form targets only, never proxy/absolute authorities.
            if not self.path.startswith('/') or self.path.startswith('//') or '#' in self.path:
                self.reply(400, {'error': 'request target rejected'})
                return False
            hosts = self.headers.get_all('Host', [])
            origins = self.headers.get_all('Origin', [])
            if hosts != [self.server.authority]:
                self.reply(403, {'error': 'Host rejected'})
                return False
            if ((origin_required and origins != [self.server.origin]) or
                    (origins and origins != [self.server.origin])):
                self.reply(403, {'error': 'Origin rejected'})
                return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                self.reply(403, {'error': 'cross-site request rejected'})
                return False
            return True

        def reply(self, status, data, content_type='application/json'):
            body = json.dumps(data).encode() if content_type == 'application/json' else data
            self.close_connection = True
            try:
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; connect-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # A tab may disappear while an HTTP response is being written.
                # Do not hide serialization, file access or other server errors.
                pass

        def handle_upgrade(self):
            if not self.boundary(origin_required=True):
                return
            if self.path != '/websockify':
                self.reply(404, {'error': 'unknown websocket route'})
                return
            self.connection.settimeout(None)
            try:
                super().handle_upgrade()
            except ConnectionError:
                # A disappearing tab/backend can reset the close handshake.
                # There is no HTTP response left to send after an upgrade.
                pass

        def do_GET(self):
            if not self.boundary():
                return
            route = urlsplit(self.path)
            if route.path == '/api/status' and not route.query:
                self.reply(200, {'csrf': token, 'controller': controller_available(args.controller_socket),
                                 'keys': KEYS})
            elif route.path == '/api/log':
                query = parse_qs(route.query, keep_blank_values=True)
                if set(query) - {'cursor'} or len(query.get('cursor', [])) > 1:
                    self.reply(400, {'error': 'only one cursor allowed'})
                    return
                cursor = query.get('cursor', [None])[0]
                if cursor is not None and len(cursor) > 512:
                    self.reply(400, {'error': 'cursor too long'})
                    return
                try:
                    with tail_lock:
                        result = tail.read(cursor=cursor, limit=65536)
                    self.reply(200, result)
                except (ValueError, TypeError):
                    self.reply(400, {'error': 'invalid cursor'})
            else:
                name = unquote(route.path)
                if route.query or '\\' in name or '\x00' in name:
                    self.reply(404, {'error': 'not found'})
                    return
                root = novnc if name.startswith('/novnc/') else ASSETS
                relative = name[len('/novnc/'):] if root == novnc else {'/': 'index.html', '/client.js': 'client.js', '/client.css': 'client.css'}.get(name)
                if relative is None:
                    self.reply(404, {'error': 'not found'})
                    return
                if root == novnc and (not relative.startswith(('core/', 'vendor/')) or not relative.endswith('.js') or any(part in ('.', '..') for part in relative.split('/'))):
                    self.reply(404, {'error': 'not found'})
                    return
                target = (root / relative).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    self.reply(404, {'error': 'not found'})
                    return
                self.reply(200, target.read_bytes(), mimetypes.guess_type(str(target))[0] or 'application/octet-stream')

        def do_HEAD(self):
            self.reply(405, {'error': 'method not allowed'})

        def do_POST(self):
            if not self.boundary(origin_required=True):
                return
            if self.path != '/api/control':
                self.reply(404, {'error': 'not found'})
                return
            if self.headers.get_all('X-CSRF-Token', []) != [token]:
                self.reply(403, {'error': 'CSRF token rejected'})
                return
            try:
                lengths = self.headers.get_all('Content-Length', [])
                if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
                    raise ValueError()
                length = int(lengths[0])
                if not 0 < length <= 128 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError()
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or set(payload) != {'key'} or not isinstance(payload['key'], str) or payload['key'] not in KEYS:
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError):
                self.reply(400, {'error': 'expected JSON {key: allowlisted name}'})
                return
            if not controller_available(args.controller_socket):
                self.reply(503, {'error': 'controller disabled or missing'})
                return
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
                    control.settimeout(0.5)
                    control.sendto(bytes([KEYS[payload['key']]]), str(args.controller_socket))
            except OSError:
                self.reply(503, {'error': 'controller transport unavailable'})
                return
            self.reply(200, {'sent': True, 'native_transition_confirmed': False})

    server = ThreadingHTTPServer((args.listen, args.port), Handler)
    server.daemon_threads = True
    # Standard websockify proxy; fixed backend, no token/address/command plugins.
    for name, value in dict(target_host=args.vnc_host, target_port=args.vnc_port,
                            token_plugin=None, auth_plugin=None, wrap_cmd=None,
                            unix_target=None, ssl_target=False, unix_listen=None,
                            heartbeat=0).items():
        setattr(server, name, value)
    host = args.listen
    server.authority = f'{host}:{server.server_port}'
    server.origin = f'http://{server.authority}'
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vnc-host', default='127.0.0.1')
    parser.add_argument('--vnc-port', type=int, required=True)
    parser.add_argument('--controller-socket', type=Path)
    parser.add_argument('--serial-log', type=Path, required=True,
                        help='fixed existing serial log path (never modified)')
    parser.add_argument('--listen', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--novnc', type=Path, required=True)
    parser.add_argument('--deps', type=Path, help='directory containing websockify package')
    args = parser.parse_args()
    if not 1 <= args.vnc_port <= 65535 or not 1 <= args.port <= 65535:
        parser.error('ports must be in 1..65535')
    try:
        socket.inet_pton(socket.AF_INET, args.listen)
        server = make_server(args)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f'Browser client: {server.origin}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
