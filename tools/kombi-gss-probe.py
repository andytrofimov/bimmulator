#!/usr/bin/env python3
"""Trace BO03 GSS startup on Malta or the experimental Capricorn-M board."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import signal
import stat
from pathlib import Path
import subprocess
import tempfile
import time

from kombi_firmware import CONFIG, GRAPHICS, PROGRAM
from kombi_rpm import RAM_SIZE, create_ram, open_rpm_mailbox, read_applied_rpm, write_rpm


LOAD_OFFSET = 0x1500
RAM_BASE = 0x80001000
# After sysClearTlb, map virtual 0xff000000–0xff1fffff to scratch RAM at
# physical 0x01e00000. Capricorn-M overlays its modeled registers on that RAM.
TLB_TRAMPOLINE = bytes.fromhex(
    "00ff083c 00508840 1f00083c 00e00835 00288840 0700083c 17800835 00108840 "
    "0700083c 17c00835 00188840 00008040 00000000 00000000 02000042 00000000 "
    "00000000 00288040 0800e003 00000000"
)
# Install the same mapping before the TX49-specific MMIO in sysHwInit. Return
# the processor ID as the displaced instruction's original callee did.
EARLY_TLB_OFFSET = 0x80
EARLY_TLB_TRAMPOLINE = bytes.fromhex(
    "2548e003 0000400c 00000000 25f82001 00780240 0800e003 00000000"
)
MILESTONES = {
    "sysInit": 0x80001020,
    "sysAuxClkConfig": 0x800029A8,
    "auxiliary clock interrupt": 0x80002970,
    "usrRoot": 0x80008F18,
    "usrSerialInit": 0x80007980,
    "usrShellInit": 0x80008D50,
    "usrAppInit": 0x80007320,
    "Check Control config entry": 0x817FE240,
    "CBS config entry": 0x817FE230,
    "gal_Init": 0x8008CA20,
    "gal_graphics_accelerator_init": 0x800D6440,
    "gal_vectorgraphic_2d_init": 0x800D0D60,
    "TGL startup handshake return": 0x8019A3E4,
    "TGL command interrupt wait": 0x800D2920,
    "TGL command interrupt handler": 0x800D28E0,
    "HmiGraph_Init": 0x801247D8,
    "HUD frame initialization": 0x8018F640,
    "HUD production-test image": 0x800A27B8,
    "display vertical-sync handler": 0x8008D8C8,
    "GSSManager_SendGSSStarted": 0x8008B878,
    "GSS manager IPC receive": 0x8008B558,
    "draw controller task": 0x8005D860,
    "HmiScheduler_Process": 0x8012CBA0,
}


def boot_image(image, *, malta, kss_replay=False, rpm_mailbox=False):
    if hashlib.sha256(image).hexdigest() != PROGRAM.sha256:
        raise ValueError("expected unpacked GSS SWFL 00003E5B build 007_003_005")
    ram = bytearray(image[LOAD_OFFSET:])

    def write_instruction(address, instruction):
        offset = address - RAM_BASE
        ram[offset:offset + 4] = instruction.to_bytes(4, "little")

    write_instruction(0x80001254, 0x08400000)  # j 0x81000000; keep original delay slot
    if malta:
        # Mask Malta's PIC on IP2 while leaving count/compare enabled.
        for address in (0x80005618, 0x80005624, 0x80005638, 0x80005644):
            offset = address - RAM_BASE
            instruction = int.from_bytes(ram[offset:offset + 4], "little")
            write_instruction(address, instruction & ~0x400)
    else:
        write_instruction(0x80005550, 0x0C400020)  # jal 0x81000080
    write_instruction(0x80008DE8, 0)  # Bypass the observed stall during WDB startup.
    if kss_replay:
        write_instruction(0x800D9178, 0x08400080)  # j 0x81000200
        write_instruction(0x800D917C, 0x3C0380FC)  # displaced lui v1, 0x80fc
        write_instruction(0x802170DC, 0x0C400100)  # jal 0x81000400 at HUD initialization
    if rpm_mailbox:
        write_instruction(0x802170DC, 0x0C400104)  # jal 0x81000410 without the HUD test image
        write_instruction(0x8021D200, 0x0C4001A0)  # jal 0x81000680 at initial HUD status
        write_instruction(0x8005D898, 0x0C400140)  # jal 0x81000500 at the draw scheduler
        # The live fixture reduces the draw controller's default wait from two vsyncs to one.
        write_instruction(0x8005DAD0, 0x24130001)  # addiu s3, zero, 1
    return ram


def qmp_command(process, name, **arguments):
    request = json.dumps({"execute": name, "arguments": arguments})
    process.stdin.write(request + "\n")
    process.stdin.flush()
    for line in process.stdout:
        reply = json.loads(line)
        if "return" in reply:
            return
        if "error" in reply:
            raise RuntimeError(f"QMP {name} failed: {reply['error']['desc']}")
    raise RuntimeError(f"QEMU exited during QMP {name}")


def capture_displays(process, directory):
    qmp_command(process, "stop")
    for device in ("cluster", "hud"):
        filename = directory / f"{device}.ppm"
        qmp_command(process, "screendump", filename=str(filename), device=device)
        print(f"Saved {filename}")


def tachometer_digest(filename):
    with filename.open("rb") as frame:
        header = [frame.readline().strip() for _ in range(3)]
        if header != [b"P6", b"1280 480", b"255"]:
            raise RuntimeError("expected a 1280×480 cluster frame")
        pixels = memoryview(frame.read())
    if len(pixels) != 1280 * 480 * 3:
        raise RuntimeError("incomplete cluster frame")
    digest = hashlib.blake2s()
    for y in range(420):
        digest.update(pixels[(y * 1280 + 800) * 3:(y + 1) * 1280 * 3])
    return digest.digest()


def measure_tachometer(process, ram, screenshot, seconds):
    with open_rpm_mailbox(ram) as mailbox:
        write_rpm(mailbox, 1200)
        deadline = time.monotonic() + 15
        while read_applied_rpm(mailbox) != 1200:
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("cluster did not consume the initial RPM")
            time.sleep(0.01)
        time.sleep(0.5)
        qmp_command(process, "screendump", filename=str(screenshot), device="cluster")
        previous = tachometer_digest(screenshot)
        start = now = last_change = time.monotonic()
        samples = changes = 0
        longest_gap = 0.0
        while now - start < seconds:
            phase = (now - start) % 4 / 2
            write_rpm(mailbox, 1200 + 5000 * (1 - abs(phase - 1)))
            qmp_command(process, "screendump", filename=str(screenshot), device="cluster")
            current = tachometer_digest(screenshot)
            samples += 1
            now = time.monotonic()
            if current != previous:
                changes += 1
                longest_gap = max(longest_gap, now - last_change)
                previous, last_change = current, now
            time.sleep(max(0, start + samples / 120 - now))
            now = time.monotonic()
    elapsed = now - start
    longest_gap = max(longest_gap, now - last_change)
    if not changes:
        raise RuntimeError("no tachometer pixels changed during the sweep")
    print(f"{changes} changed tachometer frames in {elapsed:.2f} s "
          f"({changes / elapsed:.1f} fps), sampled at {samples / elapsed:.1f} fps, "
          f"longest gap {longest_gap * 1000:.0f} ms", flush=True)


@contextmanager
def owned_qemu(args, output, **options):
    """Register custody before delivering a cancellation at the fork boundary."""
    cancelled = []
    def defer(signum, frame):
        cancelled.append(signum)
    handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    process = None
    try:
        try:
            for sig in handlers:
                signal.signal(sig, defer)
            process = subprocess.Popen(args, stderr=output, **options)
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
        if cancelled:
            raise KeyboardInterrupt
        yield process
    finally:
        # A second Ctrl-C/SIGTERM must not abandon the QEMU grandchild.
        for sig in handlers:
            signal.signal(sig, defer)
        try:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                process.wait(timeout=2)
                for stream in (process.stdin, process.stdout):
                    if stream:
                        stream.close()
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def validate_vnc_socket(path):
    path = Path(path)
    info = path.parent.lstat()
    if (not path.is_absolute() or len(os.fsencode(path)) >= 104 or "," in str(path)
            or path.parent.resolve() != path.parent or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077
            or path.exists() or path.is_symlink()):
        raise ValueError("VNC requires a new socket in an owned private directory (<104 UTF-8 bytes)")
    return path


def interrupt_probe(_signum, _frame):
    # Keep the Python custodian alive until its actual QEMU child has been reaped.
    raise KeyboardInterrupt


def run_probe(qemu, image, log, config=None, graphics_data=None, capture=None, *,
              kss_replay=False, rpm_ram=None, display="none", benchmark=None, qmp_socket=None, vnc_socket=None):
    if vnc_socket is not None:
        validate_vnc_socket(vnc_socket)
        if not (config and kss_replay and rpm_ram and display == "none"):
            raise ValueError("UNIX cluster VNC requires live Capricorn-M KSS replay with display=none")
    with tempfile.TemporaryDirectory(prefix="idrive6-gss-") as directory:
        if benchmark:
            rpm_ram = Path(directory) / "benchmark.ram"
        ram = Path(directory) / "gss-ram.bin"
        shim = Path(directory) / "tlb.bin"
        ram.write_bytes(boot_image(image, malta=config is None, kss_replay=kss_replay,
                                   rpm_mailbox=rpm_ram is not None))
        shim.write_bytes(TLB_TRAMPOLINE.ljust(EARLY_TLB_OFFSET, b"\0") + EARLY_TLB_TRAMPOLINE)
        board = "capricorn-m" if config else "malta"
        ram_backend = []
        if rpm_ram:
            create_ram(rpm_ram)
            path = str(rpm_ram.resolve()).replace(",", ",,")
            ram_backend = ["-object", f"memory-backend-file,id=gss,size={RAM_SIZE},mem-path={path},share=on"]
            board += ",memory-backend=gss"
        args = [qemu, "-machine", board, "-cpu", "VR5432", "-accel", "tcg",
                "-m", "64M", "-display", display, "-serial", "none", "-monitor", "none",
                "-nic", "none", "-nodefaults",
                "-device", f"loader,file={ram},addr=0x1000,force-raw=on",
                "-device", f"loader,file={shim},addr=0x1000000,force-raw=on",
                "-device", "loader,addr=0xffffffff80001020,cpu-num=0", *ram_backend]
        if config:
            args += ["-name", "6WB"]
        if not rpm_ram:
            args += ["-d", "in_asm,int,unimp,guest_errors"]
        if config:
            flash = Path(directory) / "gss-flash.bin"
            flash.write_bytes(image)
            for path, address in ((flash, 0x1f400000), (config, 0x1ec00000), (graphics_data, 0x1c000000)):
                filename = str(path.resolve()).replace(",", ",,")
                args += ["-device", f"loader,file={filename},addr={address:#x},force-raw=on"]
        if kss_replay:
            source = Path(__file__).with_name("kombi-kss-replay.S")
            obj = Path(directory) / "kss-replay.o"
            payload = Path(directory) / "kss-replay.bin"
            subprocess.run(["llvm-mc", "--triple=mips64el-none-elf", "--mcpu=mips3",
                            "-filetype=obj", str(source), "-o", str(obj)], check=True)
            subprocess.run(["llvm-objcopy", "--dump-section", f".text={payload}", str(obj)], check=True)
            args += ["-device", f"loader,file={payload},addr=0x1000200,force-raw=on"]
        if vnc_socket is not None:
            args += ["-vnc", f"unix:{vnc_socket},display=cluster"]
        qmp = {}
        if qmp_socket:
            socket_path = str(qmp_socket).replace(",", ",,")
            args += ["-qmp", f"unix:{socket_path},server=on,wait=off"]
        if capture or benchmark:
            args += ["-qmp", "stdio"]
            qmp = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        with log.open("xb") as output, owned_qemu(args, output, **qmp) as process:
            if qmp:
                qmp_command(process, "qmp_capabilities")
            if benchmark:
                measure_tachometer(process, rpm_ram, Path(directory) / "cluster.ppm", benchmark)
                if capture:
                    capture.mkdir()
                    capture_displays(process, capture)
                return
            if rpm_ram:
                print(f"Vehicle mailbox ready at {rpm_ram}", flush=True)
                try:
                    if process.wait():
                        raise RuntimeError(f"QEMU exited with code {process.returncode}; see {log}")
                except KeyboardInterrupt:
                    pass
                return
            deadline = time.monotonic() + (8 if kss_replay else 3)
            while process.poll() is None and time.monotonic() < deadline and log.stat().st_size < 8 * 2**20:
                time.sleep(0.01)
            if capture:
                capture.mkdir()
                capture_displays(process, capture)
    trace = log.read_bytes()
    for name, address in MILESTONES.items():
        if f"0xffffffff{address:08x}:".encode() in trace:
            print(f"{name} 0x{address:08x} reached")
    if b"0xffffffff80007320:" not in trace:
        raise RuntimeError(f"probe stopped before usrAppInit; see {log}")
    if config and b"0xffffffff8008d8c8:" not in trace:
        raise RuntimeError(f"probe stopped before display vertical sync; see {log}")
    if kss_replay and b"0xffffffff8012cba0:" not in trace:
        raise RuntimeError(f"KSS replay stopped before HmiScheduler_Process; see {log}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gss", type=Path, help="unpacked 00003E5B 007_003_005 image")
    parser.add_argument("--config", type=Path, help="unpacked 00003E5C 007_003_005 image for Capricorn-M")
    parser.add_argument("--graphics-data", type=Path, help="unpacked 00003E5D 007_003_005 image for Capricorn-M")
    parser.add_argument("--qemu", default="qemu-system-mips64el")
    parser.add_argument("--log", type=Path, required=True, help="new file for the instruction trace")
    parser.add_argument("--capture", type=Path, help="new directory for the cluster and HUD screenshots")
    parser.add_argument("--kss-replay", action="store_true",
                        help="replay GSS startup inputs and enable the stock display renderer")
    live = parser.add_mutually_exclusive_group()
    live.add_argument("--vehicle-ram", "--rpm-ram", type=Path,
                      help="run continuously with speed and RPM from a new shared RAM file")
    live.add_argument("--benchmark", type=float, metavar="SECONDS",
                      help="measure changed cluster frames during a headless RPM sweep")
    parser.add_argument("--display", default="none", help="QEMU display backend for --vehicle-ram")
    parser.add_argument("--vnc-socket", type=Path, help="new private run-owned UNIX RFB socket for the cluster")
    parser.add_argument("--qmp-socket", type=Path, help="optional QEMU monitor socket for a live run")
    args = parser.parse_args()
    if bool(args.config) != bool(args.graphics_data):
        parser.error("Capricorn-M requires both --config and --graphics-data")
    if (args.capture or args.kss_replay) and not args.config:
        parser.error("--capture and --kss-replay require Capricorn-M images")
    if args.vehicle_ram and (not args.kss_replay or args.capture):
        parser.error("--vehicle-ram requires --kss-replay and runs without --capture")
    if args.benchmark is not None and (not args.kss_replay or not 1 <= args.benchmark <= 120):
        parser.error("--benchmark requires --kss-replay and a duration from 1 to 120 seconds")
    if (args.display != "none" or args.qmp_socket) and not args.vehicle_ram:
        parser.error("--display and --qmp-socket require --vehicle-ram")
    try:
        if args.vnc_socket is not None:
            validate_vnc_socket(args.vnc_socket)
            if not (args.config and args.kss_replay and args.vehicle_ram and args.display == "none"):
                raise ValueError("UNIX cluster VNC requires live Capricorn-M KSS replay with display=none")
        signal.signal(signal.SIGTERM, interrupt_probe)
        if args.config:
            for path, expected in ((args.config, CONFIG.sha256), (args.graphics_data, GRAPHICS.sha256)):
                with path.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                        raise ValueError(f"unexpected BO03 007_003_005 flash image: {path}")
        capture = args.capture.resolve() if args.capture else None
        run_probe(args.qemu, args.gss.read_bytes(), args.log, args.config, args.graphics_data, capture,
                  kss_replay=args.kss_replay, rpm_ram=args.vehicle_ram, display=args.display,
                  benchmark=args.benchmark, qmp_socket=args.qmp_socket, vnc_socket=args.vnc_socket)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
