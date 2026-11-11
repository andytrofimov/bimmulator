# Local browser session

The ordinary launcher stages verified user-supplied PSdZData and owns the native
head unit, optional BO03 cluster, vehicle simulator and browser server:

```sh
nix run .#idrive6 -- --web
```

Open <http://127.0.0.1:8090/>. Set `web = true` and optionally `webPort = 8090`
in the normal TOML config, or pass `--web-port PORT`. Browser mode requires the
`head-unit` module; `modules = ["head-unit"]` needs no cluster firmware and
reports KOMBI unavailable. Without browser mode the native GUI path remains.
The host matrix is Apple silicon macOS/ANGLE and experimental Linux x86_64/Mesa;
this integration has synthetic host coverage, not new native qualification on
either host. Windows is deferred.

There is one real noVNC viewport with iDrive/KOMBI tabs, fourteen iDrive buttons,
a single rotary rim, an observational pointer ring, a read-only raw NBT serial
tail, and next-launch settings. KOMBI uses the existing native BO03 KSS/shared
RAM recipe and its `cluster` display, not another emulator or an HTML imitation.
It is view-only, with iDrive controls disabled. Tab switching never retargets a
shared proxy. Serial stays below the display, including when KOMBI is selected;
host/cluster logs are not concatenated into it.

## Dependencies and provenance

Nix fetches these external source archives at build time, verifies their hashes,
and retains upstream license files. They are not vendored in Git. There is no
npm build, runtime CDN or server/browser download. The optional proxy features
numpy, requests, jwcrypto and redis are not required; missing numpy only emits
a performance warning. No target-selection, token, authentication, command or
recording plugin is enabled.

| Dependency | Official source archive | SHA-256 | License |
|---|---|---|---|
| noVNC 1.6.0 | [v1.6.0 archive](https://codeload.github.com/novnc/noVNC/tar.gz/refs/tags/v1.6.0) | `5066103959ef4e9b10f37e5a148627360dd8414e4cf8a7db92bdbd022e728aaa` | Core MPL-2.0; pako MIT; DES BSD-style; see `LICENSE.txt` and source headers |
| websockify 0.13.0 | [v0.13.0 archive](https://codeload.github.com/novnc/websockify/tar.gz/refs/tags/v0.13.0) | `b6413e364efd04f3c92ec8c17747e3c4adc20157c2ef1c5d019a26d944a46df8` | LGPL-3.0; see `COPYING` and `setup.py` |

The flake also exports `novnc-source` and `websockify-source`. For standalone
Python operation, verify/extract these same archives outside the checkout.
The server requires Python 3.10+, Unix sockets and a modern browser with ES modules
and `AbortSignal.timeout`. Missing dependencies fail closed before binding; the
integrated launcher checks them before starting any VM.

## Operator-prepared inputs (advanced)

The same session entry point accepts the explicit TOML pair `preparedRoot` and
`bootImage`, both absolute external paths. This skips only NBT package staging;
selected BO03 still uses `psdzdata`. NBT-only prepared mode may omit `psdzdata`.
Required-file metadata is checked before VM spawn and the root/boot paths are
passed as explicit profile overrides. Fresh archive outputs stay in the external
cache, never the input root. Root and cache must be disjoint (neither contains
the other), and the boot image must be outside the mutable cache. No source/package pin is weakened: actual archive
and shader builders still enforce their supported-byte hashes. Console/session
records label this mode operator-prepared, **not package-verified**. Metadata
presence is not provenance or native qualification; use only reviewed matching
inputs, not roots with unknown apps/overlays. See the main README for the config.

## Settings: current boot versus next launch

Settings → Coding provides three booleans: developer menu, reverse-camera coding
(RVC), and the optional F32 resources/VariantRegistry overlay. RVC requires F32.
The launcher loads canonical preferences once, passes explicit profile `--set`
overrides (profiles override ambient environment), and creates a fresh per-run
archive. Existing source-pinned overlays transform in-memory tar members only.
OFF omits optional changes from the next archive; base ID6 Light/F32/English/CID
settings remain. The immutable staged source tree is not patched or cloned.

The current-boot column comes from the private snapshot of those exact configured
flags, bound to the fresh run ID. It means **configured at boot**, not verified
native functionality. The separate pending store is atomically replaced (0700
owned directory, 0600 regular file); saving cannot replace the snapshot. An
unmanaged/standalone server without a snapshot reports boot configuration unknown,
never inferring it from pending values.

The complete schema contains five booleans. Both ConnectedDrive mocks are OFF,
disabled and marked unavailable; attempts to enable either fail before VM spawn
or preference persistence. Cleared own app resources, provenance/ABI gates and
separate native qualification are not part of this release. No full EvoHello,
ConnectedDrive visual parity or native camera-video acceptance is claimed. The
aggregate pairs protocol 4 host/provider state forwarding with an explicit, bounded
[host ESSL selection](../../docs/NATIVE_SHADER_MAPS.md). Do not mix protocol versions.
These source/pin checks are not universal shader or native rendering proofs.

## Ownership and endpoints

Each invocation creates a fresh run ID and owns only its newly created child
process groups. Partial startup, any selected ECU/browser failure, Ctrl-C and
SIGTERM clean up and reap those children with bounded TERM/KILL escalation.
No systemd service, root factory, global process lookup, historical PID or
`current-*` alias supplies authority. The BO03 probe retains custody of its
actual QEMU child through cancellation and bounded reap. The owner observes
children without reaping (`waitid`/`WNOWAIT`), retaining the kernel PID reservation
through a full group-wide TERM grace and final KILL, then reaps the entry. Lost or
unregistered custody refuses group signals. This requires Python 3.13+ on macOS
(or the pinned Nix Python); unsupported environments fail before VM spawn.

NBT/KOMBI VNC, controller and QMP endpoints live in a fresh private short Unix
directory, below the conservative 104-byte encoded path limit on both platforms.
The CID UDP endpoint is chosen per run. The endpoint schema, exact source-input
hashes and run-bound boot snapshot are saved privately under the external cache's
`sessions/` directory; NBT logs/archive/manifest are under `runs/RUN_ID/`.
HTTP endpoint conflicts are checked before VM spawn. A later bind failure still
ends and cleans up only this invocation. Closing a browser tab leaves the session
running; stop from the launching terminal. No HTTP lifecycle API is exposed.

## Standalone server (advanced)

The hardened fixed TCP head-unit route remains compatible with an independently
started native backend. Supply the exact run's serial path and controller socket,
not a mutable run alias. For example, with an existing trusted local RFB backend:

```sh
python3 tools/idrive-web-client.py \
  --vnc-port 5907 --port 8090 \
  --controller-socket /absolute/run/controller.sock \
  --serial-log /absolute/run/serial.log \
  --novnc /external/noVNC-1.6.0 --deps /external/websockify-0.13.0
```

Alternatively use `--vnc-socket /absolute/private/nbt.vnc` instead of `--vnc-port`.
`--kombi-vnc-socket /absolute/private/cluster.vnc` adds the second fixed target.
Omit `--controller-socket` to disable buttons. Pending settings are optional via
`--settings-file` in an owned 0700 directory. Only a trusted launcher should supply
`--boot-settings-file boot-settings-RUN_ID.json` and matching `--boot-run-id` for a
newly configured boot. Do not attach a pending document as a boot snapshot.
The server never starts/stops guests or modifies serial files.

## HTTP and input boundaries

HTTP and fixed TCP VNC addresses must be numeric IPv4 loopback. Requests require
the exact configured Host/port, not `localhost` aliases. Mutations/WebSocket
upgrades require the exact same Origin; mutations also need a process-random CSRF
token. HTTP cannot choose commands, environment, files, proxy targets or paths.
Static routes expose only the five client assets and noVNC core/vendor JavaScript.
There is no TLS or remote-access support; loopback is not multi-user isolation.

Control accepts only one allowlisted key and at most 128 JSON bytes. A response
confirms transport submission only, not native acceptance. The existing renderer
queues an atomic down/up pair for nonrotary keys or one rotary step; native
readiness/ring-capacity checks may drop input. Losing a tab cannot strand a
separate HTTP key-release state. Mouse/keyboard events use noVNC and the existing
QEMU CID relay. The pointer ring observes input without intercepting it.

Serial reads are bounded to 64 KiB per poll with independent opaque cursors,
split UTF-8/rotation/truncation handling and control-byte escaping. The UI uses
`textContent`, retains at most 256 Ki characters, and has a separate serial
scrollbar. Clear changes only the browser view. Desktop 8:3 display sizing and
mobile page flow do not crop the display or hide settings actions.

## Firmware-free tests

```sh
NOVNC_DIR=/external/noVNC-1.6.0 \
WEBSOCKIFY_DIR=/external/websockify-0.13.0 \
CHROME_BIN=/path/to/google-chrome \
  python3 -m unittest discover -s tests -v
```

Without optional paths, their integration classes skip; incomplete explicit
configuration fails, not skips. Chrome uses an ephemeral profile/debugging port
with its normal sandbox. Fixtures use only owned temporary HTTP/TCP/Unix peers,
synthetic RFB pixels, fake children, and generated archive bytes. They exercise
the real composition, two concurrent fixed proxy targets, native GUI argument
compatibility, immutable boot/next settings, six valid coding triples, OFF
reversibility/source integrity, lifecycle failure/timeout/cancellation, all
fourteen controller datagrams, view-only KOMBI, pointer safety, reconnect,
response resets, history return, generation-safe persisted-page events, serial
safety and four responsive layouts. Persisted-event tests are not proof that
Chrome used BFCache. None of these tests executes firmware or qualifies native
loaded/rendered/input behavior.
