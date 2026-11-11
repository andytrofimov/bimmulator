#!/usr/bin/env python3
"""Read the local TOML configuration, stage verified firmware and launch IDrive."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid


from vm_lab_settings import SettingsStore, launch_values
from kombi_firmware import stage_kombi
from kombi_rpm import RAM_SIZE


PACKAGES = {
    "swfl_00002719.bin.007_030_001": "270957bf46bbdb21262c20068cd9c53e329c5ab6ff60a9e397aaea9a8f47cd31",
    "swfl_0000271a.bin.007_030_001": "c313315a499b2c0d49b90e541e74295cb45aebd46b6552a72afbe1dcdc06188d",
    "swfl_00002720.bin.007_030_001": "a9222a2432f5318f06aec563321832a3ba41fde60a4692cbb0cf34317b2f37e1",
}
MODULES = ("head-unit", "6wb")
EXPECTED = {"psdzdata", "cacheDir", "display", "cpuCount", "modules", "web", "webPort", "preparedRoot", "bootImage"}
RELEASE = "x20511i-007_030_001-v1"
STAGING_SCHEMA = 2


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def checked_config(project: Path, file: Path, nix: str) -> dict:
    if not file.is_file():
        raise ValueError(f"Configuration not found: {file}\nCopy idrive6.example.toml to idrive6.toml and set psdzdata.")
    environment = os.environ.copy()
    environment["IDRIVE_CONFIG_FILE"] = str(file)
    result = subprocess.run(
        [nix, "eval", "--impure", "--json", "--file", str(project / "nix/config.nix")],
        cwd=project, env=environment, text=True, capture_output=True,
    )
    if result.returncode:
        raise ValueError(f"Nix could not read {file}:\n{result.stderr.strip()}")
    config = json.loads(result.stdout)
    if not isinstance(config, dict):
        raise ValueError("The TOML configuration must contain key/value settings.")
    extra = set(config) - EXPECTED
    if extra:
        raise ValueError(f"Unknown configuration keys: {', '.join(sorted(extra))}")
    modules = config.setdefault("modules", list(MODULES))
    if (not isinstance(modules, list) or not modules
            or any(module not in MODULES for module in modules)
            or len(set(modules)) != len(modules)):
        raise ValueError('modules must select "head-unit", "6wb", or both without duplicates.')
    config.setdefault("web", False)
    config.setdefault("webPort", 8090)
    if type(config["web"]) is not bool:
        raise ValueError("web must be a boolean")
    if type(config["webPort"]) is not int or not 1 <= config["webPort"] <= 65535:
        raise ValueError("webPort must be an integer in 1..65535")
    if config["web"] and "head-unit" not in modules:
        raise ValueError("browser mode requires the head-unit module")
    prepared = "preparedRoot" in config or "bootImage" in config
    if prepared:
        if "head-unit" not in modules or not {"preparedRoot", "bootImage"} <= set(config):
            raise ValueError("preparedRoot and bootImage must be supplied together for the head-unit module")
        for key in ("preparedRoot", "bootImage"):
            if not isinstance(config[key], str) or not Path(config[key]).is_absolute():
                raise ValueError(f"{key} must be an absolute external path")
            config[key] = str(external_path(project, Path(config[key]), key))
        validate_prepared(config)
    psdz = config.get("psdzdata")
    if psdz is not None or not prepared or "6wb" in modules:
        if not isinstance(psdz, str) or not Path(psdz).is_absolute():
            raise ValueError("Set psdzdata to an absolute path to the extracted PSdZData directory.")
        config["psdzdata"] = str(external_path(project, Path(psdz), "psdzdata"))
    host = (platform.system(), platform.machine())
    native_display = {("Darwin", "arm64"): "cocoa", ("Linux", "x86_64"): "gtk"}.get(host)
    if native_display is None:
        raise ValueError("Supported hosts are Apple silicon macOS and Linux x86_64.")
    config.setdefault("display", native_display)
    config.setdefault("cpuCount", 2)
    if not isinstance(config["display"], str) or config["display"] not in {native_display, "none"}:
        raise ValueError(f"display must be '{native_display}' or 'none' on this host.")
    if type(config["cpuCount"]) is not int or config["cpuCount"] not in {1, 2}:
        raise ValueError("cpuCount must be the integer 1 or 2.")
    cache = config.get("cacheDir")
    if cache is None:
        cache = os.environ.get("XDG_CACHE_HOME")
        cache = Path(cache) / "idrive6" if cache else Path.home() / ".cache/idrive6"
    elif not isinstance(cache, str) or not Path(cache).is_absolute():
        raise ValueError("cacheDir, when set, must be an absolute path.")
    config["cacheDir"] = str(external_path(project, Path(cache), "cacheDir"))
    if prepared:
        root, output = Path(config["preparedRoot"]), Path(config["cacheDir"])
        if output == root or root in output.parents or output in root.parents:
            raise ValueError("cacheDir and read-only preparedRoot must be disjoint (neither may contain the other)")
        boot = Path(config["bootImage"])
        if boot == output or output in boot.parents:
            raise ValueError("read-only bootImage must be outside the mutable cacheDir")
    return config


def external_path(project: Path, path: Path, setting: str) -> Path:
    """Keep firmware and mutable caches out of the Nix source tree."""
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(project)
    except ValueError:
        return resolved
    raise ValueError(
        f"{setting} must be outside the repository ({project}) so firmware and local cache data stay out of the Nix store."
    )


PREPARED_FILES = (
    "bin/mkqnx6fs", "bin/dd", "bin/devb-loopback", "bin/bsdtar", "bin/mount",
    "bin/cp", "bin/screen", "bin/sleep", "bin/io-usb", "lib/devu-hb-ehci-omap3.so",
    "opt/sys/bin/LayerManagerService", "lib/screen-sw.so", "lib/libswblit.so.1",
    "lib/graphics/omap5430/libWFDomap5430ES2_0.so", "opt/hmi/ID5/lib/libhmicom.so",
    "lib/libbz2.so.1", "lib/libz.so.2", "opt/sys/etc/starter.cfg",
    "opt/hmi/ID5/bin/HmiMain3D", "opt/hmi/ID5/lib/libhmicoding.so", "opt/hmi/ID5/lib/libhmidb.so",
    "opt/hmi/ID5/data/ro/common/widget/variantregistry.pbvar",
    "opt/hmi/ID5/data/ro/common/shader/Rectangle_vertex.shd",
    "opt/hmi/ID5/data/ro/common/shader/Rectangle_fragment.shd",
)


def validate_prepared(config):
    """Metadata preflight only; this does NOT establish package provenance.

    The actual archive/map builders still enforce their unchanged source pins.
    All prepared inputs remain external and read-only; only fresh outputs are made.
    """
    root = Path(config["preparedRoot"])
    absent = [name for name in PREPARED_FILES if not (root / name).is_file()]
    if not root.is_dir() or not Path(config["bootImage"]).is_file() or absent:
        raise ValueError("operator-prepared input incomplete (not package-verified): " +
                         ", ".join(absent or ["preparedRoot/bootImage"]))


def verify_packages(psdzdata: Path) -> tuple[dict[str, Path], dict[str, str]]:
    root = psdzdata / "swe/swfl"
    paths, digests = {}, {}
    for name, expected in PACKAGES.items():
        path = root / name
        if not path.is_file():
            raise ValueError(
                f"Missing required PSdZData package: {path}\n"
                "Install or extract the matching 4.61.20 HU_NBTEVO packages "
                "00002719, 0000271a and 00002720 (branch 007_030_001)."
            )
        actual = sha256(path)
        if actual != expected:
            raise ValueError(
                f"Unsupported PSdZData package {name}: expected SHA-256 {expected}, got {actual}.\n"
                "This release uses the verified NBTevo_X20511I firmware; use the matching PSdZData extraction."
            )
        paths[name] = path
        digests[name] = actual
    return paths, digests


def stage(project: Path, cache: Path, package_paths: dict[str, Path], digests: dict[str, str]) -> Path:
    final = cache / "firmware" / RELEASE
    marker = final / ".complete.json"
    cache.mkdir(parents=True, exist_ok=True)
    expected_marker = {
        "release": RELEASE,
        "stagingSchema": STAGING_SCHEMA,
        "packages": digests,
    }
    try:
        cached_marker = json.loads(marker.read_text()) if marker.is_file() else None
    except (OSError, json.JSONDecodeError):
        cached_marker = None
    if cached_marker == expected_marker:
        print(f"Using staged firmware: {final}", flush=True)
        return final

    generations = final.parent / ".generations"
    generations.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(json.dumps(expected_marker, sort_keys=True).encode()).hexdigest()[:16]
    generation = generations / f"{RELEASE}-{fingerprint}"
    generation_marker = generation / ".complete.json"
    try:
        staged_marker = json.loads(generation_marker.read_text()) if generation_marker.is_file() else None
    except (OSError, json.JSONDecodeError):
        staged_marker = None
    if staged_marker == expected_marker:
        return publish_generation(final, generation)

    temp = generations / f".staging-{uuid.uuid4().hex}"
    temp.mkdir()
    try:
        firmware = temp / "firmware"
        command = [sys.executable, str(project / "tools/extract-psdz-swfl.py")]
        command.extend(str(package_paths[name]) for name in PACKAGES)
        command.extend(["--output", str(firmware)])
        subprocess.run(command, cwd=project, check=True)

        root = temp / "rootfs"
        subprocess.run([
            sys.executable, str(project / "tools/stage-idrive-rootfs.py"),
            str(firmware / "rootfs"), str(root),
        ], cwd=project, check=True)
        subprocess.run([
            sys.executable, str(project / "tools/stage-psdz-hmi.py"),
            str(firmware / "rootfs"), str(root), "--vehicle", "F32", "--theme", "id6l",
        ], cwd=project, check=True)
        subprocess.run([
            sys.executable, str(project / "tools/materialize-hmi-assetdb.py"),
            str(firmware / "rootfs/opt/hmi/ID5/data/ro"),
            str(root / "opt/hmi/ID5/data/ro"),
            "--psdz-extraction-manifest", str(firmware / "extraction.json"),
            "--manifest", str(temp / "hmi-assetdb-overlay.json"),
        ], cwd=project, check=True)

        required = [
            firmware / "sda2/boot1.ifs",
            root / "bin/mkqnx6fs", root / "bin/devb-loopback", root / "bin/bsdtar",
            root / "opt/sys/etc/starter.cfg", root / "opt/hmi/ID5/bin/HmiMain3D",
            root / "opt/hmi/ID5/lib/libhmicoding.so",
            root / "opt/hmi/ID5/data/ro/bmw/widgetasset/vehicles/F32",
        ]
        absent = [str(path.relative_to(temp)) for path in required if not path.exists()]
        if absent:
            raise ValueError("The firmware extraction is incomplete; missing: " + ", ".join(absent))

        for shader_map in ("hmi-vertex-map-v67.json", "hmi-fragment-map-v112.json"):
            subprocess.run([
                sys.executable, str(project / "tools/prepare-hmi-native-essl-map.py"),
                str(project / "tools/shaders/native-reconstructions" / shader_map),
                str(root), str(project),
            ], cwd=project, stdout=subprocess.DEVNULL, check=True)

        (temp / ".complete.json").write_text(json.dumps(expected_marker, indent=2) + "\n")
        try:
            temp.rename(generation)
        except OSError:
            # A concurrent launch may have published the same immutable generation.
            try:
                concurrent_marker = json.loads(generation_marker.read_text())
            except (OSError, json.JSONDecodeError):
                raise
            if concurrent_marker != expected_marker:
                raise
            shutil.rmtree(temp)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    publish_generation(final, generation)
    print(f"Prepared verified firmware cache: {final}", flush=True)
    return final


def publish_generation(final: Path, generation: Path) -> Path:
    """Atomically switch the public cache path to a complete immutable generation."""
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists() and not final.is_symlink():
        raise ValueError(
            f"Cache path {final} is an older directory layout. Move it aside or remove it, then retry."
        )
    link = final.parent / f".{RELEASE}-{uuid.uuid4().hex}.link"
    target = os.path.relpath(generation, final.parent)
    os.symlink(target, link)
    try:
        os.replace(link, final)
    finally:
        link.unlink(missing_ok=True)
    return final


def head_unit_command(project, config, firmware, *, run_id=None, endpoints=None, values=None):
    environment = os.environ.copy()
    root = Path(config["preparedRoot"]) if "preparedRoot" in config else firmware / "rootfs"
    boot = Path(config["bootImage"]) if "bootImage" in config else firmware / "firmware/sda2/boot1.ifs"
    environment.update({
        "IDRIVE_CACHE_DIR": config["cacheDir"],
        "IDRIVE_BOOT_IMAGE": str(boot),
        "IDRIVE_ROOTFS_TREE": str(root),
        "IDRIVE_REALIZED_ROOTFS": str(root),
        "IDRIVE_QEMU_CPUS": str(config["cpuCount"]),
        "IDRIVE_TCG_THREAD": "single" if config["cpuCount"] == 1 else "multi",
        "IDRIVE_DISPLAY": config["display"],
        "IDRIVE_ANGLE_EGL_SERVER_BIN": os.environ.get("IDRIVE_ANGLE_SERVER") or os.environ.get("IDRIVE_ANGLE_EGL_SERVER_BIN", ""),
        "IDRIVE_OTF_CAPTURE": "0",
        "IDRIVE_QNX_PDEBUG": "0",
        "IDRIVE_QNX_HMI_WEB_INSPECTOR": "0",
        "IDRIVE_QEMU_LOADVM": "",
        "IDRIVE_QEMU_STATE_FILE": "",
    })
    profile = project / "profiles/f32-x20511i-id6-light.json"
    command = [sys.executable, str(project / "tools/run-hmi-profile.py"), str(profile),
               "--set", f"IDRIVE_QEMU_CPUS={config['cpuCount']}",
               "--set", f"IDRIVE_TCG_THREAD={environment['IDRIVE_TCG_THREAD']}",
               "--set", f"IDRIVE_BOOT_IMAGE={boot}",
               "--set", f"IDRIVE_ROOTFS_TREE={root}",
               "--set", f"IDRIVE_REALIZED_ROOTFS={root}"]
    if run_id is not None:
        command += ["--run-id", run_id]
        run = Path(config["cacheDir"]) / "runs" / run_id
        overrides = {"IDRIVE_ROOT_ARCHIVE_OUTPUT": str(run / "rootfs.tar.gz")}
        overrides.update(launch_values(values))
        # Mocks have no profile implementation: explicitly off, never an ambient opt-in.
        for key in ("IDRIVE_VM_CONNECTEDDRIVE_MOCK", "IDRIVE_VM_CONNECTEDDRIVE_AVAILABILITY_MOCK"):
            environment[key] = overrides.pop(key)
        if endpoints:
            overrides.update({"IDRIVE_QEMU_QMP_SOCKET": str(endpoints["nbt_qmp"]),
                              "IDRIVE_HMI_CONTROLLER_SOCKET": str(endpoints["controller"])})
            environment["TMPDIR"] = str(endpoints["directory"])
            environment["IDRIVE_HMI_CID_PORT"] = str(endpoints["cid_port"])
        if config.get("web"):
            environment["IDRIVE_DISPLAY"] = "none"
            environment["IDRIVE_VNC"] = ""
            environment["IDRIVE_VNC_SOCKET"] = str(endpoints["nbt_vnc"])
        for key, value in overrides.items():
            command += ["--set", f"{key}={value}"]
    return command, environment


@contextmanager
def deferred_interrupts():
    """Keep custody operations atomic with respect to user cancellation."""
    cancelled = []
    def defer(signum, frame):
        cancelled.append(signum)
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        for sig in handlers:
            signal.signal(sig, defer)
        yield cancelled
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


# Only this owner's freshly spawned Popen objects may carry a reservation. Never
# reap them in the monitor: an unreaped direct child reserves its PID/PGID until
# the last group signal, including when its entry exits before its descendants.
_OWNED_CHILDREN = {}


def require_child_reservations():
    names = ("waitid", "P_PID", "WEXITED", "WNOHANG", "WNOWAIT", "CLD_EXITED", "CLD_KILLED", "CLD_DUMPED")
    if any(not hasattr(os, name) for name in names) or not callable(os.waitid):
        raise ValueError("safe session ownership requires os.waitid/WNOWAIT; use Nix or Python 3.13+ on macOS")
    if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
        raise ValueError("safe session ownership requires sole child reaping (SIGCHLD must use its default handler)")


def child_status(process):
    """Observe one reserved direct child without releasing its kernel identity."""
    pid = _OWNED_CHILDREN.get(process)
    if type(pid) is not int or process.pid != pid or process.returncode is not None:
        raise RuntimeError("child custody lost or unregistered; refusing process-group authority")
    try:
        result = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError as error:
        raise RuntimeError("child was reaped outside its owner; refusing process-group authority") from error
    if result is None:
        return None
    if result.si_pid != pid:
        raise RuntimeError("unexpected child identity; refusing process-group authority")
    if result.si_code == os.CLD_EXITED:
        return result.si_status
    if result.si_code in (os.CLD_KILLED, os.CLD_DUMPED):
        return -result.si_status
    # Darwin can report CLD_STOPPED even with WEXITED. A stopped process is
    # still live and reserved; it must not be mistaken for a completed child.
    return None


def stop_process(process, timeout=3):
    """TERM/grace/KILL a reserved owned group, then and only then reap entry.

    The full absolute grace belongs to the entire group, not merely its entry
    child. No poll/wait occurs before the last signal: even an exited entry
    remains waitable and prevents a foreign group reusing its numeric identity.
    """
    with deferred_interrupts():
        child_status(process)  # Reject forged, externally reaped or replaced IDs.
        pid = _OWNED_CHILDREN[process]
        deadline = time.monotonic() + timeout
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        while (remaining := deadline - time.monotonic()) > 0:
            child_status(process)  # Custody must remain valid through the grace.
            time.sleep(min(0.05, remaining))
        child_status(process)
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired as error:
            # Keep the strong reference/reservation; never declare cleanup done.
            raise RuntimeError("owned child did not reap after SIGKILL; custody remains outstanding") from error
        _OWNED_CHILDREN.pop(process, None)


def web_dependencies(project):
    novnc = Path(os.environ.get("IDRIVE_NOVNC", ""))
    deps = Path(os.environ.get("IDRIVE_WEBSOCKIFY", ""))
    if not (novnc.is_absolute() and (novnc / "core/rfb.js").is_file()
            and deps.is_absolute() and (deps / "websockify/__init__.py").is_file()):
        raise ValueError("browser dependencies missing: use the Nix launcher (pinned noVNC/websockify)")
    # Import now, before staging or spawning a VM; a broken dependency fails closed.
    sys.path.insert(0, str(deps))
    try:
        from websockify.websocketproxy import ProxyRequestHandler  # noqa: F401
    except ImportError as error:
        raise ValueError(f"missing browser dependency: {error}") from error
    return novnc, deps


def preflight(config):
    """Validate executable closure and fixed listeners before starting any child."""
    require_child_reservations()
    commands = []
    if "head-unit" in config["modules"]:
        commands += [os.environ.get("IDRIVE_QEMU", "qemu-system-arm"),
                     os.environ.get("IDRIVE_ANGLE_SERVER") or os.environ.get("IDRIVE_ANGLE_EGL_SERVER_BIN", ""), "clang", "ld.lld", "llvm-objcopy"]
    if "6wb" in config["modules"]:
        commands += [os.environ.get("IDRIVE_KOMBI_QEMU", "qemu-system-mips64el"), "llvm-mc", "llvm-objcopy"]
    for command in commands:
        if not command or shutil.which(command) is None:
            raise ValueError(f"required runtime executable unavailable: {command or 'graphics server'}")
    # Reject unsupported ambient capabilities, rather than silently claiming parity.
    for name in ("IDRIVE_VM_CONNECTEDDRIVE_MOCK", "IDRIVE_VM_CONNECTEDDRIVE_AVAILABILITY_MOCK"):
        if os.environ.get(name, "0") != "0":
            raise ValueError(f"UNAVAILABLE_CAPABILITY: {name}")
    if config.get("web"):
        with socket.socket() as probe:
            # Match ThreadingHTTPServer: a completed local session may leave
            # TIME_WAIT sockets, but a live foreign listener must still refuse.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", config["webPort"]))


def run_kombi_session(project, cache, config, images, head_unit, *, web=None, endpoints=None):
    """Existing session owner, extended to NBT-only and optional browser children."""
    require_child_reservations()
    runs = cache / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix="6wb-", dir=runs)) if images else None
    with ExitStack() as cleanup:
        processes = {}

        def start(name, command, env=None):
            # Defer cancellation until the returned child is registered. Do not
            # block signals across fork/exec: the child would inherit that mask.
            with deferred_interrupts() as cancelled:
                process = subprocess.Popen(command, env=env, start_new_session=True)
                _OWNED_CHILDREN[process] = process.pid
                cleanup.callback(stop_process, process)
                processes[name] = process
            if cancelled:
                raise KeyboardInterrupt
            return process

        if images:
            ram = run / "vehicle.ram"
            qmp = endpoints["kombi_qmp"] if endpoints else run / "qmp.sock"
            if len(os.fsencode(qmp)) >= 104:
                short = cleanup.enter_context(tempfile.TemporaryDirectory(prefix="id6-", dir="/tmp"))
                qmp = Path(short) / "qmp.sock"
            display = "none" if config["display"] == "none" or web else "sdl"
            command = [sys.executable, str(project / "tools/kombi-gss-probe.py"), str(images[0]),
                       "--config", str(images[1]), "--graphics-data", str(images[2]),
                       "--qemu", os.environ.get("IDRIVE_KOMBI_QEMU", "qemu-system-mips64el"),
                       "--kss-replay", "--log", str(run / "qemu.log"), "--vehicle-ram", str(ram),
                       "--display", display, "--qmp-socket", str(qmp)]
            if web:
                command += ["--vnc-socket", str(endpoints["kombi_vnc"])]
            kombi = start("6WB", command)
            deadline = time.monotonic() + 20
            while not (ram.is_file() and ram.stat().st_size == RAM_SIZE and qmp.is_socket()):
                if child_status(kombi) is not None or time.monotonic() >= deadline:
                    raise RuntimeError(f"6WB failed to start; see {run / 'qemu.log'}")
                time.sleep(0.05)
            start("vehicle simulator", [sys.executable, str(project / "tools/kombi-sim.py"),
                                      "--port", "0", "--vehicle-ram", str(ram)])
        if head_unit:
            start("head unit", *head_unit)
        if web:
            start("browser", web)
        while True:
            for module, process in processes.items():
                if (status := child_status(process)) is not None:
                    if status or module in ("vehicle simulator", "browser"):
                        raise RuntimeError(f"{module} exited with status {status}")
                    return 0
            time.sleep(0.1)


def session_source(project):
    names = ("flake.nix", "flake.lock", "run-emulator.sh", "profiles/f32-x20511i-id6-light.json",
             "tools/idrive6-launch.py", "tools/run-hmi-profile.py", "tools/kombi-gss-probe.py",
             "tools/kombi_firmware.py", "tools/kombi-sim.py", "tools/idrive-web-client.py",
             "tools/vm_lab_settings.py", "tools/web_serial_log.py", "tools/archive-idrive-rootfs.py",
             "tools/web-client/client.js", "tools/web-client/client.css", "tools/web-client/index.html",
             "tools/web-client/settings.js", "tools/web-client/settings.css")
    hashes = {name: sha256(project / name) for name in names}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"source_id": "sha256:" + identity, "source_files": hashes}


def run_session(project, cache, config, firmware, images, dependencies=None):
    """Allocate fresh run authority, then delegate all children to the one owner."""
    run_id = "session-" + uuid.uuid4().hex[:16]
    private = cache / "settings"
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    store = SettingsStore(private / "pending.json", private)
    values = store.load()
    sessions = cache / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    record = sessions / run_id
    record.mkdir(mode=0o700)
    boot = record / f"boot-settings-{run_id}.json"
    SettingsStore(boot, record).save({"values": values})
    # Short private sockets also work with long, non-ASCII external cache paths.
    with tempfile.TemporaryDirectory(prefix="id6-", dir="/tmp") as temporary, \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as cid:
        directory = Path(temporary)
        cid.bind(("127.0.0.1", 0))
        endpoints = {key: directory / name for key, name in {
            "nbt_vnc": "nbt.vnc", "kombi_vnc": "kombi.vnc", "controller": "controller.sock",
            "nbt_qmp": "nbt.qmp", "kombi_qmp": "kombi.qmp"}.items()}
        endpoints.update(directory=directory, cid_port=cid.getsockname()[1])
        document = {"schema": "idrive6-session-v1", "run_id": run_id,
                    "profile_name": "f32-x20511i-id6-light-baseline", **session_source(project),
                    "endpoints": {key: str(value) for key, value in endpoints.items()},
                    "serial": str(cache / "runs" / run_id / "serial.log"),
                    "head_unit_input": "operator_prepared_not_package_verified" if "preparedRoot" in config else
                                       "verified_psdz_packages" if firmware else "not_selected"}
        fd = os.open(record / "session.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(document, stream, indent=2)
        head = head_unit_command(project, config, firmware, run_id=run_id,
                                 endpoints=endpoints, values=values) if firmware else None
        web = None
        if config.get("web"):
            novnc, deps = dependencies
            web = [sys.executable, str(project / "tools/idrive-web-client.py"),
                   "--vnc-socket", str(endpoints["nbt_vnc"]), "--port", str(config["webPort"]),
                   "--controller-socket", str(endpoints["controller"]),
                   "--serial-log", document["serial"], "--novnc", str(novnc), "--deps", str(deps),
                   "--settings-file", str(store.path), "--boot-settings-file", str(boot),
                   "--boot-run-id", run_id]
            if images:
                web += ["--kombi-vnc-socket", str(endpoints["kombi_vnc"])]
        cid.close()  # QEMU's CID hostfwd now owns this chosen private UDP endpoint.
        return run_kombi_session(project, cache, config, images, head, web=web, endpoints=endpoints)


def interrupt_session(_signum, _frame):
    raise KeyboardInterrupt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="TOML config; defaults to ./idrive6.toml")
    parser.add_argument("--web", action="store_true", help="run the selected head unit and optional 6WB in the local browser")
    parser.add_argument("--web-port", type=int, help="loopback HTTP port (default 8090)")
    parser.add_argument("--prepare-only", action="store_true", help="validate and stage firmware without starting QEMU")
    args = parser.parse_args()
    project = Path(os.environ.get("IDRIVE_SOURCE_ROOT", Path.cwd())).resolve()
    config_file = args.config or (project / "idrive6.toml")
    if not config_file.is_absolute():
        config_file = Path.cwd() / config_file
    nix = os.environ.get("IDRIVE_NIX", "nix")
    try:
        config = checked_config(project, config_file.resolve(), nix)
        config["web"] = config["web"] or args.web
        if args.web_port is not None:
            config["webPort"] = args.web_port
        if config["web"] and "head-unit" not in config["modules"]:
            raise ValueError("browser mode requires the head-unit module")
        if type(config["webPort"]) is not int or not 1 <= config["webPort"] <= 65535:
            raise ValueError("webPort must be an integer in 1..65535")
        dependencies = web_dependencies(project) if config["web"] else None
        if not args.prepare_only:
            preflight(config)
        modules = config["modules"]
        cache = Path(config["cacheDir"])
        psdzdata = Path(config["psdzdata"]) if "psdzdata" in config else None
        firmware = None
        kombi_images = None
        if "head-unit" in modules:
            if "preparedRoot" in config:
                validate_prepared(config)
                firmware = Path(config["preparedRoot"])
                print("Using explicit operator-prepared head-unit inputs; PSdZ package provenance is NOT verified.", flush=True)
            else:
                package_paths, digests = verify_packages(psdzdata)
                firmware = stage(project, cache, package_paths, digests)
        if "6wb" in modules:
            kombi_images = stage_kombi(psdzdata, cache)
        if args.prepare_only:
            if "preparedRoot" in config:
                print("Prepared head-unit paths checked (not package-verified); selected BO03 inputs staged if requested.")
            else:
                print(f"Firmware verified and staged for {', '.join(modules)}.")
            return 0
        signal.signal(signal.SIGTERM, interrupt_session)
        return run_session(project, cache, config, firmware, kombi_images, dependencies)
    except KeyboardInterrupt:
        return 130
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"idrive6: {error}", file=sys.stderr)
        return 1
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
