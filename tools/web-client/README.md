# Local browser client

A single real noVNC viewport, fourteen iDrive controller buttons and a bounded,
read-only serial log. There is no framebuffer imitation, screenshot polling,
VM lifecycle API, settings editor or cluster display. The browser reconnects
when its fixed RFB backend returns. No npm build, runtime CDN or automatic
dependency download is used.

The Python server works on macOS and Linux with Python 3.10+, Unix datagram
sockets, and a modern browser supporting ES modules and `AbortSignal.timeout`.
This does not add Linux support to the native emulator launcher.

## Dependencies

Keep these exact source archives and their extracts **outside the checkout**.
Verify SHA-256 before extracting; retain upstream license files and notices.
The server uses noVNC's core/vendor modules, not its themed application.

| Dependency | Official source archive | SHA-256 | License |
|---|---|---|---|
| noVNC 1.6.0 | [v1.6.0 archive](https://codeload.github.com/novnc/noVNC/tar.gz/refs/tags/v1.6.0) | `5066103959ef4e9b10f37e5a148627360dd8414e4cf8a7db92bdbd022e728aaa` | Core MPL-2.0; pako MIT; DES BSD-style; see `LICENSE.txt` and source headers |
| websockify 0.13.0 | [v0.13.0 archive](https://codeload.github.com/novnc/websockify/tar.gz/refs/tags/v0.13.0) | `b6413e364efd04f3c92ec8c17747e3c4adc20157c2ef1c5d019a26d944a46df8` | LGPL-3.0; see `COPYING` and `setup.py` |

The fixed proxy path works without websockify's optional numpy, requests,
jwcrypto and redis features; numpy absence emits a performance warning.
No token, authentication, command, recording or target-selection plugins are used.
Dependencies are not bundled with this client.

## Start the head unit

First stage firmware with the normal launcher. On the supported macOS host,
use the existing developer profile with an unused loopback VNC display:

```sh
export IDRIVE_CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/idrive6"
IDRIVE_DISPLAY=none IDRIVE_VNC=127.0.0.1:3 \
  nix develop -c python3 tools/run-hmi-profile.py \
  profiles/f32-x20511i-id6-light.json --run-id browser-session
```

Choose a fresh run ID for each launch. `IDRIVE_VNC` accepts only
`127.0.0.1:DISPLAY`, with display 0..59635 and no additional QEMU options.
The TCP port is 5900 + DISPLAY (5903 above). Without this variable the display
behavior is unchanged. The profile already enables the graphics mailbox,
CID pointer relay and native controller; no additional guest hook is needed.

The runner prints its run artifact directory; its existing `serial.log` is the
log to read. The emulator also prints the temporary controller socket path.
Copy that exact path, not the run directory: the socket belongs to the renderer's
private temporary work directory and is removed when the emulator exits.
The printed path is configuration, not a readiness or native-input acknowledgment.

## Start the browser server

In another terminal, set the paths to your dependency extracts, existing serial
log and the controller socket printed by the running emulator:

```sh
NOVNC_DIR=/absolute/path/to/noVNC-1.6.0
WEBSOCKIFY_DIR=/absolute/path/to/websockify-0.13.0
SERIAL_LOG=/absolute/path/to/run/serial.log
CONTROLLER_SOCKET=/absolute/path/to/temporary-work/controller.sock
python3 tools/idrive-web-client.py \
  --vnc-port 5903 --controller-socket "$CONTROLLER_SOCKET" \
  --serial-log "$SERIAL_LOG" --novnc "$NOVNC_DIR" --deps "$WEBSOCKIFY_DIR"
```

Open <http://127.0.0.1:8090/>. Omit `--controller-socket` to disable the buttons.
The server never launches or restarts a VM. A missing serial log is reported as
unavailable and retried; the configured file or symlink is never modified.
A restarted VM may have a different controller path: restart this server with
the new fixed path rather than selecting paths through HTTP.

## Boundaries

Both HTTP binding and the fixed TCP VNC target must be numeric IPv4 loopback
addresses; their defaults are `127.0.0.1`. Access requires the exact configured
Host/port (not `localhost` aliases). State-changing requests and WebSocket
upgrades require the exact same Origin; controller requests additionally require
a process-random CSRF token and at most 128 bytes of JSON containing exactly one
allowlisted key. Static routes expose only this client's three assets and
noVNC core/vendor JavaScript under their configured directory. HTTP cannot
choose commands, environment variables, filesystem paths or proxy targets.
There is no TLS, remote access support or VNC credential dialog. Use only a
trusted local, no-auth RFB backend; loopback access is not multi-user isolation.
Missing optional dependencies fail closed before the server binds.

A control response confirms **transport submission only**, not native acceptance.
The existing renderer checks readiness and ring capacity. It queues a down/up
pair atomically for each nonrotary key, or one event for a rotary step; input can
be dropped if the native ring is not ready or full. The browser never sends a
separate held-key state, so losing HTTP or a browser tab cannot strand a release.
Mouse/keyboard input uses noVNC and the existing QEMU CID relay, not a new guest API.

The serial endpoint reads at most 64 KiB input bytes per poll. Independent opaque
cursors preserve split UTF-8 and detect rotation, symlink changes and truncation.
Control/binary bytes are escaped. The UI uses `textContent`, keeps at most 256 Ki
characters and clips each displayed batch to 64 Ki characters. Clear affects only
the browser view, never the source log. This is not a durable log collector.

## Firmware-free tests / CI

The dependency-free subset runs with the ordinary test suite. For the real
websockify HTTP/TCP bridge checks, set both dependency paths explicitly:

```sh
NOVNC_DIR="$NOVNC_DIR" WEBSOCKIFY_DIR="$WEBSOCKIFY_DIR" \
  python3 -m unittest discover -s tests -p 'test*web*py' -v
```

With neither variable set, optional integration tests skip. An incomplete or
invalid explicit configuration fails instead of silently skipping. CI jobs
running this path should fetch and verify the pinned archives above outside the
checkout, then export these two paths. Add `CHROME_BIN=/path/to/google-chrome`
for the optional real-browser test (normal Chrome sandbox support is required).
It creates an ephemeral Chrome profile and private debugging port, decodes a
known synthetic RFB pixel through real noVNC, checks all fourteen button datagrams,
mouse forwarding, ring pointer, reconnect, serial text safety, clear and responsive
layout. History return is checked separately from synthetic persisted-page events;
the latter cover idempotent resume and stale poll responses, not proof that a
browser actually used BFCache. HTTP fixtures also reset connections during header
and body writes. Tests use only owned temporary HTTP/TCP/Unix peers, never a live emulator.

The shell tests execute the unchanged VNC validation/argument source sections
and reject invalid values through the actual launcher before firmware work.
They do not boot QEMU. These checks establish neither native HMI visual acceptance
nor a macOS/Linux native runtime qualification; verify those separately with your
own staged firmware before relying on a native session.
