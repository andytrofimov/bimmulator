"""Optional real noVNC/Chrome checks against an owned, synthetic RFB peer only.

Set CHROME_BIN, NOVNC_DIR and WEBSOCKIFY_DIR. No guest or live port is used.
"""
import http.client
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import threading
import time
import unittest

import test_idrive_web_client as webtests


def receive(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise EOFError()
        data += chunk
    return data


class RFBFixture:
    """Minimal RFB 3.8 peer with one known raw pixel, not an HMI simulation."""
    def __init__(self, listener):
        self.listener = listener
        self.stop = threading.Event()
        self.drop = threading.Event()
        self.pointer = threading.Event()
        self.connections = 0
        self.errors = []
        listener.settimeout(.2)
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                peer, _ = self.listener.accept()
            except socket.timeout:
                continue
            try:
                with peer:
                    peer.settimeout(2)
                    self.connections += 1
                    peer.sendall(b'RFB 003.008\n')
                    receive(peer, 12)
                    peer.sendall(b'\x01\x01')  # Security: None, private fixture only.
                    receive(peer, 1)
                    peer.sendall(struct.pack('!I', 0))
                    receive(peer, 1)
                    fmt = struct.pack('!BBBBHHHBBB3x', 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
                    peer.sendall(struct.pack('!HH', 1440, 540) + fmt + struct.pack('!I', 7) + b'fixture')
                    peer.settimeout(.2)
                    pixel = b'\x30\x20\x10\x00'
                    while not self.stop.is_set() and not self.drop.is_set():
                        try:
                            kind = receive(peer, 1)[0]
                        except socket.timeout:
                            continue
                        if kind == 0:
                            fmt = struct.unpack('!BBBBHHHBBB3x', receive(peer, 19)[3:])
                            value = (16 << fmt[7]) | (32 << fmt[8]) | (48 << fmt[9])
                            pixel = value.to_bytes(fmt[0] // 8, 'big' if fmt[2] else 'little')
                        elif kind == 2:
                            header = receive(peer, 3)
                            receive(peer, struct.unpack('!H', header[1:])[0] * 4)
                        elif kind == 3:
                            receive(peer, 9)
                            # One raw pixel is enough to prove actual decoding/rendering.
                            peer.sendall(struct.pack('!BBHHHHHi', 0, 0, 1, 0, 0, 1, 1, 0) + pixel)
                        elif kind == 4:
                            receive(peer, 7)
                        elif kind == 5:
                            receive(peer, 5)
                            self.pointer.set()
                        elif kind == 6:
                            header = receive(peer, 7)
                            receive(peer, struct.unpack('!I', header[3:])[0])
                        else:
                            raise AssertionError(f'unexpected client message {kind}')
            except (EOFError, ConnectionError, socket.timeout):
                pass
            except Exception as exc:
                self.errors.append(exc)
            self.drop.clear()

    def close(self):
        self.stop.set()
        self.thread.join(4)
        if self.thread.is_alive():
            raise AssertionError('RFB fixture did not stop')
        if self.errors:
            raise AssertionError(self.errors)


class BrowserTests(webtests.ClientFixture):
    @classmethod
    def setUpClass(cls):
        cls.chrome = os.environ.get('CHROME_BIN')
        if not cls.chrome:
            raise unittest.SkipTest('optional browser test: set CHROME_BIN')
        cls.novnc, cls.deps = webtests.dependency_paths(os.environ)

    def setUp(self):
        super().setUp()
        self.rfb = RFBFixture(self.backend)
        self.addCleanup(self.rfb.close)
        self.profile = self.root / 'chrome-profile'
        self.browser = subprocess.Popen([self.chrome, '--headless', '--disable-gpu',
            '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
            '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
            '--remote-allow-origins=http://127.0.0.1', '--user-data-dir=' + str(self.profile),
            'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.close_browser)
        active = self.profile / 'DevToolsActivePort'
        self.until(lambda: active.is_file())
        port = int(active.read_text().splitlines()[0])
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
        conn.request('PUT', '/json/new?about:blank')
        target = json.loads(conn.getresponse().read())
        conn.close()
        from websockify.websocket import WebSocket
        class ChromeSocket(WebSocket):
            # Adapt the binary-only RFB transport locally for CDP text JSON.
            # This test helper never changes the websockify server.
            def _decode_hybi(self, buf):
                frame = super()._decode_hybi(buf)
                if frame and frame['opcode'] == 1:
                    frame['opcode'] = 2
                return frame

            def send_text(self, message):
                self._sendmsg(1, message.encode())

            def send_header(self, name, value):
                super().send_header(name, f'127.0.0.1:{port}' if name == 'Host' else value)
        self.devtools = ChromeSocket()
        self.devtools.connect(target['webSocketDebuggerUrl'], origin='http://127.0.0.1')
        self.devtools.socket.settimeout(5)
        self.addCleanup(self.devtools.socket.close)
        self.sequence = 0
        self.command('Page.navigate', {'url': self.origin + '/'})
        self.until(lambda: self.evaluate("document.getElementById('vnc-status')?.textContent === 'Connected'"))

    def close_browser(self):
        self.browser.terminate()
        try:
            self.browser.wait(5)
        except subprocess.TimeoutExpired:
            self.browser.kill()
            self.browser.wait(5)

    def until(self, condition):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if condition():
                return
            threading.Event().wait(.05)
        self.fail('timed out waiting for browser/fixture state')

    def command(self, method, params):
        self.sequence += 1
        self.devtools.send_text(json.dumps({'id': self.sequence, 'method': method, 'params': params}))
        while True:
            result = json.loads(self.devtools.recv())
            if result.get('id') == self.sequence:
                self.assertNotIn('error', result)
                return result.get('result', {})

    def evaluate(self, expression):
        result = self.command('Runtime.evaluate', {'expression': expression, 'returnByValue': True,
                                                    'awaitPromise': True})
        self.assertNotIn('exceptionDetails', result)
        return result['result'].get('value')

    def test_history_return_and_synthetic_persisted_resume(self):
        self.evaluate("window.__historySentinel = true")
        history = self.command('Page.getNavigationHistory', {})
        entry = history['entries'][history['currentIndex']]['id']
        self.command('Page.navigate', {'url': self.origin + '/client.css'})
        self.until(lambda: self.evaluate("location.pathname === '/client.css'"))
        self.command('Page.navigateToHistoryEntry', {'entryId': entry})
        self.until(lambda: self.evaluate("document.getElementById('vnc-status')?.textContent === 'Connected'"))
        # History may reload instead of using BFCache (e.g. active WebSockets).
        # The explicit persisted-event fixture below is not a BFCache repro claim.
        restored = self.evaluate('window.__historySentinel === true')
        print('Chrome history return: ' + ('persisted document' if restored else 'reloaded document'))
        self.evaluate("""window.__savedFetch = window.fetch;
            window.__held = [];
            window.fetch = (url, options) => {
                if (url === '/api/status' || url.startsWith('/api/log')) {
                    return new Promise(resolve => window.__held.push({url, resolve}));
                }
                return window.__savedFetch(url, options);
            };
            window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true}));
            window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}));""")
        self.until(lambda: self.evaluate('window.__held.length === 2'))
        with self.log.open('ab') as stream:
            stream.write(b'\nafter-resume\n')
        self.evaluate("""window.dispatchEvent(new PageTransitionEvent('pagehide', {persisted:true}));
            window.fetch = window.__savedFetch;
            window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}));
            window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted:true}));
            for (const held of window.__held) {
                held.resolve(new Response(JSON.stringify(held.url === '/api/status'
                    ? {csrf:'stale-token',controller:false}
                    : {cursor:'stale-cursor',text:'STALE_RESPONSE',reset:true,available:true})));
            }
            new Promise(resolve => setTimeout(resolve, 0));""")
        self.until(lambda: self.evaluate("document.getElementById('vnc-status').textContent === 'Connected'"))
        self.until(lambda: self.evaluate("document.getElementById('log').textContent.includes('after-resume')"))
        self.assertFalse(self.evaluate("document.getElementById('log').textContent.includes('STALE_RESPONSE')"))
        self.until(lambda: self.evaluate("!document.querySelector('[data-key=menu]').disabled"))
        self.evaluate("document.querySelector('[data-key=menu]').click()")
        self.assertEqual(self.sock.recv(8), bytes([webtests.client.KEYS['menu']]))
        self.assertEqual(self.evaluate("document.querySelectorAll('canvas').length"), 1)
        point = self.evaluate("(()=>{const r=document.querySelector('canvas').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
        self.command('Input.dispatchMouseEvent', {'type': 'mouseMoved', **point})
        self.assertFalse(self.evaluate("document.getElementById('pointer').hidden"))
        with self.log.open('ab') as stream:
            stream.write(b'\nnext-poll\n')
        self.until(lambda: self.evaluate("document.getElementById('log').textContent.includes('next-poll')"))

    def test_real_viewport_controls_reconnect_log_and_layout(self):
        self.until(lambda: self.evaluate("document.querySelector('canvas')?.width === 1440"))
        self.until(lambda: self.evaluate("JSON.stringify([...document.querySelector('canvas').getContext('2d').getImageData(0,0,1,1).data]) === '[16,32,48,255]'"))
        self.assertEqual(self.evaluate("document.querySelectorAll('[data-key]').length"), 14)
        self.assertFalse(self.evaluate("Boolean(document.querySelector('[role=tab],dialog,[src*=settings]'))"))
        self.until(lambda: self.evaluate("document.getElementById('log').textContent.includes('<script>')"))
        self.assertFalse(self.evaluate("Boolean(document.querySelector('#log script'))"))
        for key, code in webtests.client.KEYS.items():
            self.evaluate(f"document.querySelector('[data-key={key}]').click()")
            self.assertEqual(self.sock.recv(8), bytes([code]))
        for width, height in [(1440, 900), (1280, 720), (390, 844)]:
            self.command('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
                'deviceScaleFactor': 1, 'mobile': False})
            self.assertLessEqual(self.evaluate('document.documentElement.scrollWidth'), width)
            if width > 760:
                self.assertLessEqual(self.evaluate('document.documentElement.scrollHeight'), height)
        self.command('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 900,
            'deviceScaleFactor': 1, 'mobile': False})
        point = self.evaluate("(()=>{const r=document.querySelector('canvas').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
        self.command('Input.dispatchMouseEvent', {'type': 'mouseMoved', **point})
        self.command('Input.dispatchMouseEvent', {'type': 'mousePressed', 'button': 'left', 'clickCount': 1, **point})
        self.command('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'button': 'left', 'clickCount': 1, **point})
        self.assertTrue(self.rfb.pointer.wait(3))
        self.assertFalse(self.evaluate("document.getElementById('pointer').hidden"),
            self.evaluate("JSON.stringify({state:document.getElementById('display-state').hidden,rect:document.getElementById('viewport').getBoundingClientRect().toJSON(),pointer:document.getElementById('pointer').outerHTML})"))
        self.rfb.drop.set()
        self.until(lambda: self.rfb.connections >= 2)
        self.until(lambda: self.evaluate("document.getElementById('vnc-status').textContent === 'Connected'"))
        self.evaluate("document.getElementById('clear').click()")
        self.assertEqual(self.evaluate("document.getElementById('log').textContent"), '')
        self.assertEqual(self.log.read_bytes(), b'<script>untrusted</script>\xff\n')


if __name__ == '__main__':
    unittest.main()
