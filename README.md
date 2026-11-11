# BMW iDrive 6 emulator

This project boots the native BMW F32 iDrive 6 Light interface in patched
QEMU. It does not include BMW firmware. You supply an extracted PSdZData
directory containing the verified NBTevo X20511I packages.

## Quick start

The Nix flake provides Apple silicon macOS (`aarch64-darwin`, ANGLE Metal)
and Linux x86_64 (`x86_64-linux`, Mesa software EGL) host packages. Linux host
support is experimental: host compilation and firmware-free EGL tests do not
qualify the complete firmware boot/UI path. The guest remains ARM/QNX.

With Nix flakes enabled, clone the repository, copy the example config, and
set `psdzdata` to the absolute path of your extracted PSdZData directory:

```sh
cp idrive6.example.toml idrive6.toml
```

```toml
psdzdata = "/path/to/psdzdata"
modules = ["head-unit", "6wb"]
```

For the first run, check and stage the firmware:

```sh
nix run .#idrive6 -- --prepare-only
```

Then start the selected modules:

```sh
nix run .#idrive6
```

The default module selection opens the head unit, cluster, and HUD as
three windows. Use `modules = ["head-unit"]` or `modules = ["6wb"]` to
start one ECU. Closing a selected ECU's window ends the session.

Point `psdzdata` at the directory containing `swe/swfl`. The head unit
uses `swfl_00002719.bin.007_030_001`, `swfl_0000271a.bin.007_030_001`,
and `swfl_00002720.bin.007_030_001`. The 6WB uses the `.bin` and `.xml`
pairs for `00003e5b`, `00003e5c`, and `00003e5d` at `007_003_005`.
The launcher extracts and verifies the selected firmware, then reuses the
verified cache on later runs. By default the cache lives under
`$XDG_CACHE_HOME/idrive6` or `~/.cache/idrive6`.

The optional settings are `cacheDir`, `display`, and `cpuCount` (`1` or `2`).
The display defaults to `cocoa` on macOS and `gtk` on Linux; `none` selects
headless operation on either host. Native Linux windows need a working X11
or Wayland desktop. The 6WB uses SDL windows for either native GUI selection.
The Mesa server itself uses surfaceless EGL, including with `display = "none"`;
it does not need a desktop or GPU. Nix pins its Mesa vendor and software-driver
paths, so the Linux package does not depend on a system-wide graphics setup.
Keep PSdZData and the cache outside the repository; the launcher rejects paths
inside the checkout so local firmware and cache files never enter the Nix
source or store. Both paths may contain spaces.
The launcher reads `./idrive6.toml` by default; pass `--config /path/to/file`
to either command to use another config.

## Controls and logs

Use the mouse for CID touch. The controller mapping uses the wheel or Page
Up/Page Down to turn, arrow keys to tilt, Return or Space to select, Escape or
Backspace for Back, M for Menu, and O for Options. C or R sends Media/Radio,
T sends Communication, N sends Navigation, and V sends Map. Click the QEMU
window first to give it keyboard focus.

Each run gets its own directory below the cache's `runs/` folder. It contains
the guest serial stream, QEMU debug log, host EGL server log, and a manifest of
the source and firmware inputs. OTF recording, network packet dumps, ANGLE
shader/draw/resource captures, `pdebug`, and the web inspector remain off by
default. For an already staged cache, set `IDRIVE_CACHE_DIR` to the same path
as `cacheDir` (or its default) before using the developer profile runner. For
example, with the default cache location:

```sh
export IDRIVE_CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/idrive6"
nix develop -c python3 tools/run-hmi-profile.py \
  profiles/f32-x20511i-id6-light.json \
  --set IDRIVE_OTF_CAPTURE=1 \
  --set IDRIVE_OTF_CAPTURE_OUTPUT=/tmp/idrive6-otf.bin \
  --set IDRIVE_OTF_CAPTURE_SERVER_LOG=/tmp/idrive6-otf.log
```

### Optional local browser client

The [browser client](tools/web-client/README.md) shows the real head-unit RFB
viewport, fourteen iDrive controls and a read-only serial tail. It uses external,
pinned noVNC/websockify sources and an optional loopback-only `IDRIVE_VNC` listener;
no web dependencies are needed for the normal launcher. See that guide for the
existing developer-profile launch command, dependency verification and
firmware-free HTTP/browser tests. The Python browser server supports macOS and
Linux independently of the native emulator host requirements.

## Current limits

The F32 home interface, text, controller input, and CID touch run through
BMW's native HmiMain3D and QNX Screen. QEMU supplies an OMAP5430 board model
and a software display path. The PowerVR SGX540 is not fully emulated; the
host EGL bridge implements the graphics calls used by the tested HMI path.
The macOS path continues to use ANGLE; Linux uses Mesa with the same version-3
RPC and unchanged QNX provider. Other vehicle variants and the full Linux
firmware boot/UI path are not part of the verified release.

## Developer notes

- [QEMU patch workflow](docs/qemu-patches.md) explains how to update the four
  topic patches against the pinned QEMU in Nixpkgs.
- [Graphics contract](NATIVE_GRAPHICS_CONTRACT.md) documents the current
  native HMI display path and observed boundaries.
- [HMI startup trace](HMI_STARTUP_DEPENDENCY.md) records the measured service
  and startup dependencies.
- [Third-party notices](THIRD_PARTY_NOTICES.md) covers the QEMU patches and
  optional Vita3K-based shader diagnostics.
- `tools/` contains the retained firmware extraction, graphics, and QNX
  diagnostics. Enter `nix develop` for the corresponding build tools.

The exact PSdZData package SHA-256 values are pinned in
`tools/idrive6-launch.py`. A different firmware revision must be reviewed and
added as a distinct, verified profile before use. The checked-in shader data is
limited to the host-side ESSL reconstructions and hashes used by this profile;
the original BMW shader payloads are verified from PSdZData at runtime.

## Developer diagnostics

Run the firmware-free extractor, QNX bootstrap, and QEMU device tests with:

```sh
nix develop -c python3 -m unittest discover -s tests -v
```

The firmware staging diagnostics use the same verified input as the launcher;
`nix run .#idrive6 -- --prepare-only` checks and stages it without starting
QEMU. The device tests use QEMU directly and need no firmware or GUI.

### Linux host EGL checks

To build just the Mesa bridge and exercise its real version-3 RPC path without
QEMU, firmware, a desktop, or a GPU:

```sh
mkdir -p build
nix build .#mesa-egl-rpc-server --out-link build/mesa-host
IDRIVE_TEST_EGL_SERVER="$PWD/build/mesa-host/bin/mesa-egl-rpc-server" \
  python3 -m unittest discover -s tests -p test_egl_rpc_server.py -v
```

These opt-in tests start their own localhost server on a temporary port. They
check EGL initialization, an ES2 pbuffer clear/readback, GL errors, malformed
frames, and protocol-version rejection. They do not test QNX boot or the HMI.
The host package/target matrix is evaluated by `test_flake_hosts.py` when Nix
is available; the EGL tests skip unless `IDRIVE_TEST_EGL_SERVER` is set.

Without Nix, the host-only builder uses a C++17 compiler and `pkg-config` for
EGL 1.5/GLES2 development files; install Mesa's software EGL runtime using
your distribution's package manager. Then run:

```sh
tools/build-mesa-egl-rpc-server.sh build/mesa-egl-rpc-server
LIBGL_ALWAYS_SOFTWARE=1 \
  IDRIVE_TEST_EGL_SERVER="$PWD/build/mesa-egl-rpc-server" \
  python3 -m unittest discover -s tests -p test_egl_rpc_server.py -v
```

`IDRIVE_HOST_CXX` (then `CXX`) selects the compiler executable; `PKG_CONFIG`
selects the dependency-query executable. Standard pkg-config search/sysroot
variables are respected. Shell command strings and escaped-space dependency
flags are not supported. This standalone builder does not supply patched QEMU,
QNX cross-build tools, or a firmware launcher; use the Nix entry point above
for the composed host environment. Existing ANGLE-specific diagnostic builders
remain macOS/ANGLE tools, rather than implicitly switching backends.

## Experimental 6WB cluster and HUD

The Bosch BO03 6WB runs in a separate QEMU guest. Its cluster and HUD
open as SDL windows. The live fixture replays KSS startup and HUD
readiness in temporary guest RAM and uses the firmware's unwarped HUD
output.

The launcher prints a local simulator URL. Open it for manual speed and
RPM controls. External simulators can read `GET /api/v1/vehicle` or send
partial updates to `POST /api/v1/vehicle` at that URL. The API uses km/h
for `speed_kph` and RPM for `engine_rpm`.

### Standalone 6WB probe

Use this path to capture startup graphics or run the simulator separately.
Build the Capricorn-M machine and set `BO03_IMAGES` to the unpacked
`firmware/bo03-007_003_005` directory in the cache created by
`nix run .#idrive6 -- --prepare-only`.

```sh
nix build .#qemu-capricorn-m --out-link /tmp/idrive6-capricorn-qemu
kombi_run="$(mktemp -d /tmp/idrive6-kombi.XXXXXX)"
printf '6WB run directory %s\n' "$kombi_run"
nix develop -c python3 tools/kombi-gss-probe.py \
  "$BO03_IMAGES/swfl_00003e5b-bf400000.bin" \
  --config "$BO03_IMAGES/swfl_00003e5c-bec00000.bin" \
  --graphics-data "$BO03_IMAGES/swfl_00003e5d-bc000000.bin" \
  --qemu /tmp/idrive6-capricorn-qemu/bin/qemu-system-mips64el \
  --log "$kombi_run/gss.log" --kss-replay \
  --vehicle-ram "$kombi_run/vehicle.ram" \
  --display vnc=127.0.0.1:1,display=cluster
```

Connect a VNC client to `127.0.0.1:5901`. Use `display=hud` to view the
native HUD. For a one-shot cluster and HUD startup capture, replace the
live RAM and display options with `--capture "$kombi_run/frames"`.

In another terminal, set `kombi_run` to the printed run directory and start
the host-side Python simulator.

```sh
python3 tools/kombi-sim.py --vehicle-ram "$kombi_run/vehicle.ram"
```

Open `http://127.0.0.1:8765/` for controls and browser-rendered previews.
Add `--demo` for a looping feed. External simulators can read
`GET /api/v1/vehicle` and send partial updates. The API uses km/h for
`speed_kph` and RPM for `engine_rpm`. Both fields drive the stock QEMU
renderers through the shared RAM fixture.

```sh
curl --fail -H 'Content-Type: application/json' \
  --data '{"speed_kph":87,"engine_rpm":2300}' http://127.0.0.1:8765/api/v1/vehicle
```

To test head-unit MOST transport, also start the simulator with
`--sipc-port 8766` and launch the head unit with
`IDRIVE_MOST_SIPC_HOST_PORT=8766 nix run .#idrive6`. The native
`DSYSMOSTServer` runs inside the guest. QEMU forwards its upstream TCP SIPC
connection to the host Python process. `GET /api/v1/most?after=0` returns
link state and decoded telegrams. The vehicle-state feed and SIPC telegrams
are separate interfaces. Native MOST delivery to the Kombi still needs
network-master behavior and Kombi registration.
