#!/usr/bin/env python3
"""Minimal offline noVNC client and fixed-path native controller/log API."""
import argparse
import ipaddress
import json
import mimetypes
import re
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


class DisplayBackend:
    """Per-connection fixed backend; never mutate a shared server during a switch."""
    def __init__(self, server, unix_target):
        self._server = server
        self.unix_target = str(unix_target)

    def __getattr__(self, name):
        return getattr(self._server, name)


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
    nbt_socket = getattr(args, "vnc_socket", None)
    if (nbt_socket is None and (args.vnc_port is None or not 1 <= args.vnc_port <= 65535)) or not 0 <= args.port <= 65535:
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
    kombi_socket = getattr(args, 'kombi_vnc_socket', None)
    if kombi_socket is not None and not kombi_socket.is_absolute():
        raise ValueError('--kombi-vnc-socket must be an absolute fixed local socket path')
    settings = None
    settings_path = getattr(args, 'settings_file', None)
    boot_path = getattr(args, 'boot_settings_file', None)
    boot_run = getattr(args, 'boot_run_id', None)
    boot_values = None
    if boot_path is not None:
        if (settings_path is None or settings_path == boot_path or not isinstance(boot_run, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', boot_run)
                or boot_path.name != 'boot-settings-' + boot_run + '.json'):
            raise ValueError('boot settings require a fixed run-bound snapshot and pending settings path')
        from vm_lab_settings import SettingsStore
        boot_values = SettingsStore(boot_path, boot_path.parent).load(require_saved=True)
    elif boot_run is not None:
        raise ValueError('--boot-run-id requires --boot-settings-file')
    if settings_path is not None:
        from vm_lab_settings import SettingsStore
        settings = SettingsStore(settings_path, settings_path.parent, active_values=boot_values)

    for path in (nbt_socket, kombi_socket):
        if path is not None and (not path.is_absolute() or len(bytes(path)) >= 104):
            raise ValueError("VNC sockets require fixed absolute paths shorter than 104 UTF-8 bytes")

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
            if self.path == '/websockify/kombi' and kombi_socket is not None:
                self.server = DisplayBackend(self.server, kombi_socket)
            elif self.path != '/websockify':
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
                                 'keys': KEYS, 'displays': {
                                     'idrive': {'available': controller_available(nbt_socket) if nbt_socket else True},
                                     'kombi': {'available': controller_available(kombi_socket)}}})
            elif route.path == '/api/settings' and not route.query:
                if settings is None:
                    self.reply(503, {'error': 'Settings are not configured'})
                else:
                    try:
                        self.reply(200, dict(settings.snapshot(), boot_run_id=boot_run))
                    except (OSError, ValueError) as exc:
                        self.reply(503, {'error': str(exc)})
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
                relative = name[len('/novnc/'):] if root == novnc else {'/': 'index.html', '/client.js': 'client.js', '/client.css': 'client.css', '/settings.js': 'settings.js', '/settings.css': 'settings.css'}.get(name)
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
            if self.path not in ('/api/control', '/api/settings'):
                self.reply(404, {'error': 'not found'})
                return
            if self.headers.get_all('X-CSRF-Token', []) != [token]:
                self.reply(403, {'error': 'CSRF token rejected'})
                return
            if self.path == '/api/settings':
                if settings is None:
                    self.reply(503, {'error': 'Settings are not configured'})
                    return
                try:
                    lengths = self.headers.get_all('Content-Length', [])
                    if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
                        raise ValueError('invalid body length')
                    length = int(lengths[0])
                    if not 0 < length <= 4096 or self.headers.get('Content-Type') != 'application/json':
                        raise ValueError('invalid settings body')
                    from vm_lab_settings import decode_json
                    result = dict(settings.save(decode_json(self.rfile.read(length))), boot_run_id=boot_run)
                except (ValueError, TypeError, UnicodeError):
                    self.reply(400, {'error': 'Invalid VM settings'})
                    return
                except OSError:
                    self.reply(503, {'error': 'Unable to save VM settings'})
                    return
                self.reply(200, result)
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
                            unix_target=str(nbt_socket) if nbt_socket else None, ssl_target=False, unix_listen=None,
                            heartbeat=0).items():
        setattr(server, name, value)
    host = args.listen
    server.authority = f'{host}:{server.server_port}'
    server.origin = f'http://{server.authority}'
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vnc-host', default='127.0.0.1')
    parser.add_argument('--vnc-port', type=int)
    parser.add_argument('--vnc-socket', type=Path, help='fixed private UNIX RFB target; alternative to TCP')
    parser.add_argument('--controller-socket', type=Path)
    parser.add_argument('--kombi-vnc-socket', type=Path, help='fixed local UNIX RFB backend for the KOMBI tab')
    parser.add_argument('--settings-file', type=Path, help='fixed pending VM settings in a private 0700 directory')
    parser.add_argument('--boot-settings-file', type=Path, help='fixed private snapshot of configured values for this fresh VM launch')
    parser.add_argument('--boot-run-id', help='exact ordinary run ID bound to the boot snapshot filename')
    parser.add_argument('--serial-log', type=Path, required=True,
                        help='fixed existing serial log path (never modified)')
    parser.add_argument('--listen', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--novnc', type=Path, required=True)
    parser.add_argument('--deps', type=Path, help='directory containing websockify package')
    args = parser.parse_args()
    if (args.vnc_socket is None and (args.vnc_port is None or not 1 <= args.vnc_port <= 65535)) or not 1 <= args.port <= 65535:
        parser.error('ports must be in 1..65535')
    if args.vnc_socket is not None and args.vnc_port is not None:
        parser.error('select either --vnc-socket or --vnc-port')
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
