#!/usr/bin/env python3
"""Add a staged root tree and native QNX format tools to a prepared IFS."""

from __future__ import annotations

import argparse
import gzip
import io
import os
from pathlib import Path
import re
import struct
import sys
import tarfile


STARTUP_SIGNATURE = b"\xeb\x7e\xff\x00"
IMAGE_HEADER = struct.Struct("<7sBLLL4LLL40sL")
DIRENT = struct.Struct("<HHLLLLL")
FILE_TYPE = 0x8000


def elf_needed(payload: bytes) -> list[str]:
    """Read DT_NEEDED from the little-endian ELF32 binaries used by QNX ARM."""
    if len(payload) < 52 or payload[:6] != b"\x7fELF\x01\x01":
        raise RuntimeError("expected a little-endian ELF32 guest binary")
    phoff = struct.unpack_from("<I", payload, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", payload, 42)
    if phentsize < 32 or phoff + phentsize * phnum > len(payload):
        raise RuntimeError("invalid guest ELF program-header table")
    loads = []
    dynamic = None
    for i in range(phnum):
        kind, offset, address, _physical, size = struct.unpack_from("<IIIII", payload, phoff + i * phentsize)
        if offset + size > len(payload):
            raise RuntimeError("ELF segment extends beyond the guest binary")
        if kind == 1:
            loads.append((address, offset, size))
        elif kind == 2:
            dynamic = (offset, size)
    if dynamic is None:
        return []
    needed = []
    strings = None
    offset, size = dynamic
    for i in range(offset, offset + size, 8):
        tag, value = struct.unpack_from("<II", payload, i)
        if tag == 0:
            break
        if tag == 1:
            needed.append(value)
        elif tag == 5:
            strings = value
    if not needed:
        return []
    for address, offset, size in loads:
        if strings is not None and address <= strings < address + size:
            base = offset + strings - address
            names = []
            for value in needed:
                end = payload.find(b"\0", base + value, offset + size)
                if end < 0:
                    raise RuntimeError("unterminated ELF library name")
                name = payload[base + value:end].decode("ascii")
                if not name or "/" in name:
                    raise RuntimeError(f"invalid guest library name: {name!r}")
                names.append(name)
            return names
    raise RuntimeError("ELF dynamic string table is outside loadable segments")


def file_entries(imagefs: bytearray, directory_offset: int):
    entries: dict[str, tuple[int, int, int, int]] = {}
    inodes: list[int] = []
    position = directory_offset
    while position + DIRENT.size <= len(imagefs):
        entry_size, _extattr, inode, mode, _gid, _uid, _mtime = DIRENT.unpack_from(
            imagefs, position
        )
        if entry_size == 0:
            return entries, inodes, position
        end = position + entry_size
        if entry_size < DIRENT.size or end > len(imagefs):
            raise RuntimeError(f"invalid IFS directory record at {position:#x}")
        inodes.append(inode)
        if mode & 0xF000 == FILE_TYPE:
            if position + 32 > end:
                raise RuntimeError(f"truncated IFS file record at {position:#x}")
            data_offset, data_size = struct.unpack_from("<II", imagefs, position + 24)
            name_end = imagefs.find(b"\0", position + 32, end)
            if name_end < 0:
                raise RuntimeError(f"unterminated IFS filename at {position:#x}")
            name = imagefs[position + 32 : name_end].decode("utf-8")
            entries[name] = (position, data_offset, data_size, inode)
        position = end
    raise RuntimeError("IFS directory table has no terminator")


def make_dirent(name: str, offset: int, size: int, inode: int, mode: int) -> bytes:
    encoded_name = name.encode("utf-8")
    if b"/" not in encoded_name or b"\0" in encoded_name:
        raise RuntimeError(f"expected a relative IFS path: {name}")
    raw = bytearray(DIRENT.pack(0, 0, inode, mode, 0, 0, 0))
    raw.extend(struct.pack("<II", offset, size) + encoded_name + b"\0")
    raw.extend(bytes((-len(raw)) & 3))
    if len(raw) > 0xFFFF:
        raise RuntimeError(f"IFS path is too long: {name}")
    struct.pack_into("<H", raw, 0, len(raw))
    return bytes(raw)


def archive_size_uncompressed(archive: bytes) -> int:
    if not archive.startswith(b"\x1f\x8b"):
        return len(archive)
    size = 0
    with gzip.GzipFile(fileobj=io.BytesIO(archive), mode="rb") as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
    return size


def archive_inode_count(archive: bytes) -> int:
    """Reserve a QNX6 inode for every archive entry plus runtime headroom."""
    mode = "r:gz" if archive.startswith(b"\x1f\x8b") else "r:"
    with tarfile.open(fileobj=io.BytesIO(archive), mode=mode) as stream:
        entries = sum(1 for _ in stream)
    # The root and /.boot consume two inodes, and HMI/Screen create runtime
    # files after extraction. Leave 25% headroom (at least 1024 inodes).
    return max(8192, entries + max(1024, entries // 4) + 2)


def patch_process(
    script: bytearray,
    label: bytes,
    old_marker: bytes,
    command: bytes,
    *,
    preserve_argc: bool,
    filler_count: int | None = None,
) -> None:
    label_offset = script.find(label)
    first = script.find(old_marker, label_offset + len(label))
    if label_offset < 0 or first < 0:
        raise RuntimeError(f"could not locate process after {label!r}")
    environment = script.find(b"PATH=/boot/bin:", first)
    if environment < 0:
        raise RuntimeError(f"could not locate process environment after {label!r}")

    region_size = environment - first
    prefix = b"/boot/bin/ksh\0ksh\0-c\0"
    packed = prefix + command + b"\0"
    if preserve_argc:
        old_count = len(script[first:environment].split(b"\0")) - 1
        filler_count = old_count - 4
        if filler_count < 1:
            raise RuntimeError("could not preserve the starter process argument count")
    elif filler_count is None:
        filler_count = 6

    filler_bytes = region_size - len(packed)
    if filler_count is None or filler_bytes < filler_count * 2:
        raise RuntimeError(
            f"replacement process needs {len(packed) + (filler_count or 0) * 2} bytes; "
            f"slot has {region_size}"
        )
    lengths = [filler_bytes - 2 * (filler_count - 1)] + [2] * (filler_count - 1)
    packed += b"".join(b"x" * (length - 1) + b"\0" for length in lengths)
    if len(packed) != region_size:
        raise RuntimeError("internal error while repacking a QNX process argument block")
    script[first:environment] = packed


def disable_dsp_logger(script: bytearray) -> None:
    # gs loads this bare-metal logger at 0x8bff0000, inside larger embedded
    # root archives. There is no DSP to inspect in the emulator. Preserve the
    # three argument strings and their total size while replacing it by sleep 0.
    label = script.find(b"starting DSP register logger...")
    marker = b"/boot/bin/gs\0gs\0/boot/bin/memcpy_utility.out\0"
    first = script.find(marker, label)
    environment = script.find(b"PATH=/boot/bin:", first)
    if min(label, first, environment) < 0:
        raise RuntimeError("could not locate the DSP logger process")
    prefix = b"/boot/bin/sleep\0sleep\0"
    zeros = environment - first - len(prefix) - 1
    if zeros < 1:
        raise RuntimeError("DSP logger argument slot is too small")
    script[first:environment] = prefix + b"0" * zeros + b"\0"


def enable_debug_shell(script: bytearray) -> None:
    marker = b"/boot/bin/login\0login\0"
    first = script.find(marker)
    if first < 0:
        # This NBTevo IFS already starts its console as an interactive ksh.
        # Accept that native root shell rather than failing the whole embed.
        if script.count(b"/boot/bin/ksh\0ksh\0-li\0") == 1:
            return
        raise RuntimeError("could not find the console login or interactive shell process")
    if script.find(marker, first + 1) >= 0:
        raise RuntimeError("expected one console login process")
    prefix = b"/boot/bin/ksh\0ksh"
    # Keep both argument strings and the fixed-size process record intact.
    script[first:first + len(marker)] = prefix + b"x" * (len(marker) - len(prefix) - 1) + b"\0"


def replace_payload(
    imagefs: bytearray,
    entry: tuple[int, int, int, int],
    payload: bytes,
    *,
    executable: bool = True,
) -> None:
    record, offset, capacity, _inode = entry
    if len(payload) > capacity:
        raise RuntimeError(
            f"replacement IFS payload ({len(payload)} bytes) exceeds slot ({capacity} bytes)"
        )
    imagefs[offset : offset + capacity] = payload + bytes(capacity - len(payload))
    struct.pack_into("<I", imagefs, record + 28, len(payload))
    if executable:
        mode = struct.unpack_from("<I", imagefs, record + 8)[0]
        struct.pack_into("<I", imagefs, record + 8, mode | 0o111)


def embed(
    prepared_ifs: Path,
    rootfs_archive: Path,
    mkqnx6fs_path: Path,
    dd_path: Path,
    loopback_path: Path,
    bsdtar_path: Path,
    mount_path: Path,
    bz2_path: Path,
    zlib_path: Path,
    output: Path,
) -> None:
    image = bytearray(prepared_ifs.read_bytes())
    header_offset = image.find(STARTUP_SIGNATURE)
    if header_offset < 0 or header_offset + 0x30 > len(image):
        raise RuntimeError("QNX startup header signature was not found")
    startup_size, imagefs_size = struct.unpack_from(
        "<II", image, header_offset + 0x20
    )[0], struct.unpack_from("<I", image, header_offset + 0x2C)[0]
    stored_size = struct.unpack_from("<I", image, header_offset + 0x24)[0]
    if startup_size <= 0 or imagefs_size <= 0 or startup_size + imagefs_size > stored_size:
        raise RuntimeError("prepared IFS has inconsistent startup/image sizes")
    imagefs_start = header_offset + startup_size
    imagefs_end = imagefs_start + imagefs_size
    if imagefs_end > len(image) or imagefs_size < IMAGE_HEADER.size + 4:
        raise RuntimeError("prepared IFS image filesystem is truncated")

    imagefs = bytearray(image[imagefs_start:imagefs_end])
    (signature, _flags, _image_size, header_directory_size, directory_offset, *_rest) = (
        IMAGE_HEADER.unpack_from(imagefs, 0)
    )
    if signature.rstrip(b"\0") != b"imagefs":
        raise RuntimeError(f"unexpected IFS image header signature: {signature!r}")
    entries, inodes, directory_end = file_entries(imagefs, directory_offset)
    if header_directory_size != directory_end + 4:
        raise RuntimeError("IFS directory size does not match its record table")

    required = (
        "proc/boot/.script",
        "boot/bin/devb-sdmmc-omap5evm",
        "boot/bin/dumper",
        "boot/bin/sysinit",
    )
    missing = [name for name in required if name not in entries]
    if missing:
        raise RuntimeError(f"prepared IFS is missing: {', '.join(missing)}")

    archive = rootfs_archive.read_bytes()
    tools = {
        "boot/bin/dd": (dd_path, True),
        "boot/bin/df": (dd_path.with_name("df"), True),
        "boot/bin/mkqnx6fs": (mkqnx6fs_path, True),
        "boot/bin/bsdtar": (bsdtar_path, True),
        "boot/bin/mount": (mount_path, True),
        "boot/bin/sleep": (dd_path.with_name("sleep"), True),
        "boot/lib/libbz2.so.1": (bz2_path, False),
        "boot/lib/libz.so.2": (zlib_path, False),
    }
    storage_diagnostics = os.environ.get("IDRIVE_STORAGE_DIAGNOSTICS") == "1"
    if storage_diagnostics:
        tools["boot/bin/pidin"] = (dd_path.with_name("pidin"), True)
    # The PSdZData bsdtar needs more libraries than the original dump's build.
    # Resolve its guest ELF dependencies before the root filesystem exists.
    pending = list(tools.values())
    while pending:
        path, _executable = pending.pop()
        for library in elf_needed(path.read_bytes()):
            name = f"boot/lib/{library}"
            if name in entries or name in tools:
                continue
            source = zlib_path.parent / library
            if not source.is_file():
                raise RuntimeError(f"bootstrap library {library} required by {path.name} is missing")
            tools[name] = (source, False)
            pending.append((source, False))
    payloads: list[tuple[str, bytes, bool]] = []
    for name, (path, executable) in tools.items():
        payload = path.read_bytes()
        if executable and not payload.startswith(b"\x7fELF"):
            raise RuntimeError(f"guest executable is not an ELF file: {path}")
        payloads.append((name, payload, executable))
    payloads.append(("proc/boot/rootfs.tar.gz", archive, False))
    if not payloads[-1][1]:
        raise RuntimeError("root filesystem archive is empty")
    angle_rpc_smoke = os.environ.get("IDRIVE_GLES_RPC_SMOKE") == "1"
    angle_rpc_helper = os.environ.get("IDRIVE_ANGLE_RPC_CLIENT_HELPER", "")
    angle_egl_rpc_smoke = os.environ.get("IDRIVE_ANGLE_EGL_RPC_SMOKE") == "1"
    angle_egl_hmi = os.environ.get("IDRIVE_ANGLE_EGL_HMI") == "1"
    angle_egl_hmi_preflight = (
        os.environ.get("IDRIVE_ANGLE_EGL_HMI_PREFLIGHT") == "1"
    )
    angle_hmi_surface_width = os.environ.get(
        "IDRIVE_ANGLE_HMI_SURFACE_WIDTH", ""
    )
    angle_hmi_surface_height = os.environ.get(
        "IDRIVE_ANGLE_HMI_SURFACE_HEIGHT", ""
    )
    angle_egl_provider_enabled = angle_egl_rpc_smoke or angle_egl_hmi
    angle_egl_provider = os.environ.get("IDRIVE_ANGLE_EGL_PROVIDER", "")
    angle_egl_smoke_helper = os.environ.get("IDRIVE_ANGLE_EGL_SMOKE_HELPER", "")
    angle_screen_bridge = os.environ.get("IDRIVE_ANGLE_SCREEN_BRIDGE") == "1"
    angle_screen_smoke_helper = os.environ.get("IDRIVE_ANGLE_SCREEN_SMOKE_HELPER", "")
    if angle_rpc_smoke:
        if not angle_rpc_helper:
            raise RuntimeError("IDRIVE_GLES_RPC_SMOKE requires its built QNX client")
        angle_rpc_bytes = Path(angle_rpc_helper).read_bytes()
        if not angle_rpc_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX ANGLE RPC client is not an ELF executable")
        payloads.append(("proc/boot/angle-rpc-client", angle_rpc_bytes, True))
    elif angle_rpc_helper:
        raise RuntimeError("IDRIVE_ANGLE_RPC_CLIENT_HELPER requires IDRIVE_GLES_RPC_SMOKE=1")
    if angle_egl_rpc_smoke and angle_egl_hmi:
        raise RuntimeError("IDRIVE_ANGLE_EGL_RPC_SMOKE and IDRIVE_ANGLE_EGL_HMI are mutually exclusive")
    if angle_egl_hmi_preflight and not angle_egl_hmi:
        raise RuntimeError("IDRIVE_ANGLE_EGL_HMI_PREFLIGHT requires IDRIVE_ANGLE_EGL_HMI=1")
    if bool(angle_hmi_surface_width) != bool(angle_hmi_surface_height):
        raise RuntimeError(
            "IDRIVE_ANGLE_HMI_SURFACE_WIDTH and HEIGHT must be configured together"
        )
    if angle_hmi_surface_width or angle_hmi_surface_height:
        if not angle_egl_hmi:
            raise RuntimeError(
                "IDRIVE_ANGLE_HMI_SURFACE_WIDTH/HEIGHT require IDRIVE_ANGLE_EGL_HMI=1"
            )
        if (angle_hmi_surface_width, angle_hmi_surface_height) not in {
            ("800", "480"),
            ("1280", "480"),
            ("1440", "540"),
            ("1600", "600"),
            ("1920", "720"),
        }:
            raise RuntimeError("unsupported BMW HMI Screen surface dimensions")
    if angle_egl_provider_enabled:
        if os.environ.get("IDRIVE_SOFTWARE_SCREEN_PROBE") != "1":
            raise RuntimeError("ANGLE EGL provider mode requires the software Screen probe")
        if angle_rpc_smoke:
            raise RuntimeError("ANGLE EGL provider mode cannot share port 41416 with IDRIVE_GLES_RPC_SMOKE")
        if not angle_egl_provider:
            raise RuntimeError("ANGLE EGL provider mode requires its provider library")
        provider_bytes = Path(angle_egl_provider).read_bytes()
        if not provider_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX ANGLE EGL provider is not an ELF library")
        payloads.append(("proc/boot/libidrive-angle-provider.so", provider_bytes, False))
        if angle_egl_rpc_smoke or angle_egl_hmi_preflight:
            if not angle_egl_smoke_helper:
                raise RuntimeError("ANGLE EGL smoke mode requires its smoke ELF")
            smoke_bytes = Path(angle_egl_smoke_helper).read_bytes()
            if not smoke_bytes.startswith(b"\x7fELF"):
                raise RuntimeError("QNX ANGLE EGL smoke client is not an ELF executable")
            payloads.append(("proc/boot/egl-angle-provider-smoke", smoke_bytes, True))
        if angle_screen_bridge:
            if not angle_screen_smoke_helper:
                raise RuntimeError("IDRIVE_ANGLE_SCREEN_BRIDGE requires its Screen smoke ELF")
            screen_smoke_bytes = Path(angle_screen_smoke_helper).read_bytes()
            if not screen_smoke_bytes.startswith(b"\x7fELF"):
                raise RuntimeError("QNX ANGLE Screen smoke client is not an ELF executable")
            payloads.append(("proc/boot/angle-screen-window-smoke", screen_smoke_bytes, True))
        elif angle_screen_smoke_helper:
            raise RuntimeError("ANGLE Screen smoke artifact requires IDRIVE_ANGLE_SCREEN_BRIDGE=1")
    elif angle_egl_provider or angle_egl_smoke_helper:
        raise RuntimeError("ANGLE EGL provider artifacts require ANGLE EGL provider mode")
    elif angle_screen_bridge or angle_screen_smoke_helper:
        raise RuntimeError("ANGLE Screen bridge artifacts require IDRIVE_ANGLE_EGL_RPC_SMOKE=1")
    variant_helper = os.environ.get("IDRIVE_STARTER_VARIANT_HELPER")
    if variant_helper:
        variant_bytes = Path(variant_helper).read_bytes()
        if not variant_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("starter variant helper is not an ELF executable")
        payloads.append(("proc/boot/starter-variant", variant_bytes, True))
    controller_library = os.environ.get("IDRIVE_HMI_CONTROLLER_LIBRARY")
    if controller_library:
        controller_bytes = Path(controller_library).read_bytes()
        if not controller_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX HMI controller bridge is not an ELF library")
        payloads.append(("proc/boot/libidrive-hmi-controller.so", controller_bytes, False))
    title_cache_helper = os.environ.get("IDRIVE_HMI_TITLE_CACHE_HELPER")
    if title_cache_helper:
        if os.environ.get("IDRIVE_HMI_FORCE_START") != "1":
            raise RuntimeError("the HMI title-cache probe requires the direct HMI launch")
        title_cache_bytes = Path(title_cache_helper).read_bytes()
        if not title_cache_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX HMI title-cache probe is not an ELF executable")
        payloads.append(("proc/boot/hmi-title-cache", title_cache_bytes, True))
    screen_test_helper = os.environ.get("IDRIVE_SCREEN_TEST_HELPER")
    if screen_test_helper:
        screen_test_bytes = Path(screen_test_helper).read_bytes()
        if not screen_test_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX Screen test helper is not an ELF executable")
        payloads.append(("proc/boot/screen-test", screen_test_bytes, True))
    screen_hmi_contract_probe = os.environ.get("IDRIVE_SCREEN_HMI_CONTRACT") == "1"
    if screen_hmi_contract_probe:
        if os.environ.get("IDRIVE_SOFTWARE_SCREEN_PROBE") != "1":
            raise RuntimeError(
                "IDRIVE_SCREEN_HMI_CONTRACT requires IDRIVE_SOFTWARE_SCREEN_PROBE=1"
            )
        screen_hmi_contract_helper = os.environ.get("IDRIVE_SCREEN_HMI_CONTRACT_HELPER")
        if not screen_hmi_contract_helper:
            raise RuntimeError(
                "IDRIVE_SCREEN_HMI_CONTRACT requires its built helper path"
            )
        screen_hmi_contract_bytes = Path(screen_hmi_contract_helper).read_bytes()
        if not screen_hmi_contract_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX HMI Screen contract helper is not an ELF executable")
        payloads.append(("proc/boot/screen-hmi-contract", screen_hmi_contract_bytes, True))
    screen_shared_ram_post_probe = (
        os.environ.get("IDRIVE_SCREEN_SHARED_RAM_POST") == "1"
    )
    if screen_shared_ram_post_probe:
        if (os.environ.get("IDRIVE_SOFTWARE_SCREEN_PROBE") != "1" or
                os.environ.get("IDRIVE_QEMU_SHARED_RAM") != "1"):
            raise RuntimeError(
                "IDRIVE_SCREEN_SHARED_RAM_POST requires software Screen and shared QEMU RAM"
            )
        screen_shared_ram_post_helper = os.environ.get(
            "IDRIVE_SCREEN_SHARED_RAM_POST_HELPER"
        )
        if not screen_shared_ram_post_helper:
            raise RuntimeError(
                "IDRIVE_SCREEN_SHARED_RAM_POST requires its built helper path"
            )
        screen_shared_ram_post_bytes = Path(screen_shared_ram_post_helper).read_bytes()
        if not screen_shared_ram_post_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX Screen shared-RAM post helper is not an ELF executable")
        payloads.append((
            "proc/boot/screen-shared-ram-post",
            screen_shared_ram_post_bytes,
            True,
        ))
    native_shared_image_probe = (
        os.environ.get("IDRIVE_SCREEN_NATIVE_SHARED_IMAGE") == "1"
    )
    if native_shared_image_probe:
        if (os.environ.get("IDRIVE_SOFTWARE_SCREEN_PROBE") != "1" or
                os.environ.get("IDRIVE_SCREEN_TEST") == "1" or
                os.environ.get("IDRIVE_SCREEN_HMI_CONTRACT") == "1" or
                os.environ.get("IDRIVE_SCREEN_SHARED_RAM_POST") == "1" or
                os.environ.get("IDRIVE_SCREEN_UI_PROBE") == "1" or
                os.environ.get("IDRIVE_HMI_FORCE_START") == "1" or
                os.environ.get("IDRIVE_NATIVE_SGX_PROBE") == "1" or
                os.environ.get("IDRIVE_EGL_DIAGNOSTICS") == "1"):
            raise RuntimeError(
                "IDRIVE_SCREEN_NATIVE_SHARED_IMAGE requires software Screen and no competing Screen/HMI/EGL probes"
            )
        native_shared_image_helper = os.environ.get(
            "IDRIVE_SCREEN_NATIVE_SHARED_IMAGE_HELPER"
        )
        if not native_shared_image_helper:
            raise RuntimeError(
                "IDRIVE_SCREEN_NATIVE_SHARED_IMAGE requires its built helper path"
            )
        native_shared_image_bytes = Path(native_shared_image_helper).read_bytes()
        if not native_shared_image_bytes.startswith(b"\x7fELF"):
            raise RuntimeError(
                "QNX native shared-image probe is not an ELF executable"
            )
        payloads.append((
            "proc/boot/screen-native-shared-image-probe",
            native_shared_image_bytes,
            True,
        ))
    screen_frame_bridge = os.environ.get("IDRIVE_SCREEN_FRAME_BRIDGE") == "1"
    if screen_frame_bridge:
        raise RuntimeError("The unfinished frame-transport prototype is paused; see IMPLEMENTATION_PLAN.md")
    software_screen_probe = os.environ.get("IDRIVE_SOFTWARE_SCREEN_PROBE") == "1"
    native_sgx_probe = os.environ.get("IDRIVE_NATIVE_SGX_PROBE") == "1"
    if native_sgx_probe and not software_screen_probe:
        raise RuntimeError("IDRIVE_NATIVE_SGX_PROBE requires IDRIVE_SOFTWARE_SCREEN_PROBE=1")
    screen_ui_probe = os.environ.get("IDRIVE_SCREEN_UI_PROBE") == "1"
    if screen_ui_probe:
        screen_ui_helper = os.environ.get("IDRIVE_SCREEN_UI_HELPER")
        if not software_screen_probe or not screen_ui_helper:
            raise RuntimeError(
                "IDRIVE_SCREEN_UI_PROBE requires software Screen and a built Screen UI helper"
            )
        screen_ui_bytes = Path(screen_ui_helper).read_bytes()
        if not screen_ui_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX Screen UI helper is not an ELF executable")
        payloads.append(("proc/boot/idrive6-screen-ui", screen_ui_bytes, True))
    egl_diagnostics = os.environ.get("IDRIVE_EGL_DIAGNOSTICS") == "1"
    if egl_diagnostics:
        egl_helper = os.environ.get("IDRIVE_EGL_DIAGNOSTIC_HELPER")
        if not software_screen_probe or not egl_helper:
            raise RuntimeError(
                "IDRIVE_EGL_DIAGNOSTICS requires software Screen and a built EGL helper"
            )
        egl_bytes = Path(egl_helper).read_bytes()
        if not egl_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX EGL diagnostic helper is not an ELF executable")
        payloads.append(("proc/boot/egl-config-diagnostic", egl_bytes, True))
    egl_provider_trace = os.environ.get("IDRIVE_EGL_PROVIDER_TRACE") == "1"
    if egl_provider_trace:
        trace_helper = os.environ.get("IDRIVE_EGL_PROVIDER_TRACE_HELPER")
        if not software_screen_probe or not trace_helper:
            raise RuntimeError("EGL provider tracing requires software Screen and its built library")
        trace_bytes = Path(trace_helper).read_bytes()
        if not trace_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("EGL provider trace library is not an ELF file")
        payloads.append(("proc/boot/libidriveegltrace.so", trace_bytes, True))
    shader_parser_probe = os.environ.get("IDRIVE_SHADER_PARSER_PROBE") == "1"
    if shader_parser_probe:
        shader_parser_helper = os.environ.get("IDRIVE_SHADER_PARSER_PROBE_HELPER")
        if not shader_parser_helper:
            raise RuntimeError("IDRIVE_SHADER_PARSER_PROBE requires a built parser helper")
        shader_parser_bytes = Path(shader_parser_helper).read_bytes()
        if not shader_parser_bytes.startswith(b"\x7fELF"):
            raise RuntimeError("QNX shader parser helper is not an ELF executable")
        payloads.append(("proc/boot/shader-parser-probe", shader_parser_bytes, True))
    if software_screen_probe:
        config = Path(__file__).with_name("graphics-omap5-software.conf").read_bytes()
        if angle_egl_provider_enabled and egl_provider_trace:
            raise RuntimeError("ANGLE EGL provider mode cannot be combined with EGL provider tracing")
        if egl_provider_trace:
            original = b"egl-dlls = [IMG%s] libusc.so libsrv_um.so libpvr2d.so libIMGegl.so"
            replacement = b"egl-dlls = [ID6%s] libusc.so libsrv_um.so libpvr2d.so libIMGegl.so /proc/boot/libidriveegltrace.so"
            if config.count(original) != 1:
                raise RuntimeError("software Screen config no longer matches the traced EGL provider contract")
            config = config.replace(original, replacement, 1)
        if angle_egl_provider_enabled:
            original_egl = b"egl-dlls = [IMG%s] libusc.so libsrv_um.so libpvr2d.so libIMGegl.so"
            replacement_egl = b"egl-dlls = [ID6%s] /proc/boot/libidrive-angle-provider.so"
            original_gles = b"glesv2-dlls = libusc.so libsrv_um.so libusc.so libIMGegl.so libImgGLESv2.so"
            replacement_gles = b"glesv2-dlls = /proc/boot/libidrive-angle-provider.so"
            if config.count(original_egl) != 1 or config.count(original_gles) != 1:
                raise RuntimeError("software Screen config no longer matches the ANGLE provider replacement contract")
            config = config.replace(original_egl, replacement_egl, 1)
            config = config.replace(original_gles, replacement_gles, 1)
        if native_sgx_probe:
            config = config[config.index(b"begin khronos"):]
            config = (b"# Native PowerVR initialization probe; requires SGX hardware emulation.\n" + config)
            config = config.replace(b"        aperture = 250", b"        gpu-dlls = libsrv_um.so libpvr2d.so pvrsrv.so\n        aperture = 250")
            config = config.replace(b"usage = sw", b"usage = pvr2d")
            config = config.replace(b"/var/dump/sgxdump.txt", b"/dev/shmem/sgxdump.txt")
        payloads.append(("proc/boot/graphics-sw.conf", config, False))

    # Replace the OMAP-only SD driver with QNX's own loopback block driver.
    driver_entry = entries["boot/bin/devb-sdmmc-omap5evm"]
    loopback = loopback_path.read_bytes()
    if not loopback.startswith(b"\x7fELF"):
        raise RuntimeError(f"loopback driver is not an ELF file: {loopback_path}")
    replace_payload(imagefs, driver_entry, loopback)

    # Create a correctly formatted RAM-backed QNX6 volume before sysinit runs.
    # Keep headroom for QNX6 metadata and growth; larger recovered HMI trees can
    # request more using IDRIVE_ROOTFS_EXTRA_MIB.
    extra_mib = int(os.environ.get("IDRIVE_ROOTFS_EXTRA_MIB", "64"))
    if not 64 <= extra_mib <= 1024:
        raise RuntimeError("IDRIVE_ROOTFS_EXTRA_MIB must be between 64 and 1024")
    try:
        rootfs_ready_hold = int(os.environ.get("IDRIVE_ROOTFS_READY_HOLD_SECONDS", "0"))
    except ValueError as exc:
        raise RuntimeError("IDRIVE_ROOTFS_READY_HOLD_SECONDS must be an integer") from exc
    if not 0 <= rootfs_ready_hold <= 300:
        raise RuntimeError("IDRIVE_ROOTFS_READY_HOLD_SECONDS must be between 0 and 300")
    volume_bytes = archive_size_uncompressed(archive) + extra_mib * 1024 * 1024
    volume_mib = (volume_bytes + (1 << 20) - 1) // (1 << 20)
    archive_blocks = volume_mib * 256
    archive_inodes = archive_inode_count(archive)
    driver_command = (
        ("exec >/dev/ser1 2>&1\nset -x\n" if storage_diagnostics else "")
        + f"dd if=/dev/zero of=/dev/shmem/i bs=1048576 count={volume_mib} || exit 1\n"
        + f"mkqnx6fs -q -b4096 -i{archive_inodes} /dev/shmem/i || exit 1\n"
        + "exec /boot/bin/devb-sdmmc-omap5evm loopback rw,blksz=4096,fd=/dev/shmem/i blk cache=512k\n"
    ).encode("ascii")
    payloads.append(("proc/boot/create-root.sh", driver_command, False))
    script_entry = entries["proc/boot/.script"]
    _script_record, script_offset, script_size, _script_inode = script_entry
    script = bytearray(imagefs[script_offset : script_offset + script_size])
    disable_dsp_logger(script)
    if os.environ.get("IDRIVE_DEBUG_SHELL") == "1":
        enable_debug_shell(script)
    patch_process(
        script,
        b"starting mmc/sd driver...",
        b"devb-sdmmc-omap5evm\0devb-sdmmc-omap5evm\0",
        b". /proc/boot/create-root.sh",
        preserve_argc=False,
        filler_count=6,
    )
    imagefs[script_offset : script_offset + script_size] = script

    # Let sysinit use the loopback device, then unpack the staged root before
    # starting BMW's normal starter process.
    sysinit_entry = entries["boot/bin/sysinit"]
    _sys_record, sysinit_offset, sysinit_size, _sys_inode = sysinit_entry
    sysinit = bytearray(imagefs[sysinit_offset : sysinit_offset + sysinit_size])
    replacements = ((b"/dev/sda0t179\0", b"/dev/lo0"), (b"/dev/sda0\0", b"/dev/lo0"))
    for old, new in replacements:
        positions = [i for i in range(len(sysinit)) if sysinit.startswith(old, i)]
        if len(positions) != 1:
            raise RuntimeError(f"expected one {old[:-1]!r} path in sysinit, found {len(positions)}")
        position = positions[0]
        sysinit[position : position + len(old)] = new + bytes(len(old) - len(new))
    imagefs[sysinit_offset : sysinit_offset + sysinit_size] = sysinit

    starter_plugin = os.environ.get(
        "IDRIVE_STARTER_PLUGIN", "libnbt_starter_plugin-omap.so"
    ).strip()
    if starter_plugin.lower() in {"", "none", "off"}:
        starter_plugin_args = ""
    elif re.fullmatch(r"[A-Za-z0-9_.+-]+", starter_plugin):
        starter_plugin_args = f"-S {starter_plugin} "
    else:
        raise RuntimeError(
            "IDRIVE_STARTER_PLUGIN must be a library basename or 'none'"
        )

    starter_command = (
        "/opt/sys/bin/starter -A -s -e -g -vvv -p 30 "
        f"{starter_plugin_args}-O verbose=3,transferverbose=3 "
        "-c /opt/sys/etc/starter.cfg"
    )
    if os.environ.get("IDRIVE_STARTER_DIAGNOSTICS") == "1":
        starter_invocation = (
            f"{starter_command} &\n"
            "starter_pid=$!\n"
            "sleep 5\n"
            "/bin/pidin\n"
            "sleep 15\n"
            "/bin/pidin\n"
            "/bin/sloginfo | /bin/tail -n 120\n"
            "wait $starter_pid\n"
        )
    else:
        starter_invocation = f"exec {starter_command}\n"
    if angle_egl_rpc_smoke:
        # This replaces the GPU provider for the whole Screen instance. Keep
        # the process set quiet so BMW HMI clients cannot race the single-thread
        # host EGL current-context state during this isolated provider smoke.
        starter_invocation = (
            "echo 'ANGLE EGL provider smoke: leaving BMW starter stopped for this isolated run'\n"
        )

    variant_start = ""
    if variant_helper:
        wait_for_software_screen = (
            "n=0\n"
            "while [ ! -e /dev/screen ]; do\n"
            "  [ $n -lt 60 ] || exit 1\n"
            "  if [ $n -eq 0 ]; then echo 'Starter variant worker: waiting for Screen' >/dev/ser1; fi\n"
            "  if [ $n -eq 0 ]; then echo 'Starter variant worker: sleeping for 1 guest second' >/dev/ser1; fi\n"
            "  /boot/bin/sleep 1\n"
            "  n=$((n + 1))\n"
            "  if [ $n -eq 1 ]; then echo 'Starter variant worker: guest sleep returned' >/dev/ser1; fi\n"
            "done\n"
            if software_screen_probe else ""
        )
        variant_start = (
            "(\n"
            "n=0\n"
            "while [ ! -e /dev/starter/variant ]; do\n"
            "  [ $n -lt 300 ] || exit 1\n"
            "  if [ $n -eq 0 ]; then echo 'Starter variant worker: waiting for /dev/starter/variant' >/dev/ser1; fi\n"
            "  if [ $n -eq 0 ]; then echo 'Starter variant worker: sleeping for 1 guest second' >/dev/ser1; fi\n"
            "  /boot/bin/sleep 1\n"
            "  n=$((n + 1))\n"
            "  if [ $n -eq 1 ]; then echo 'Starter variant worker: guest sleep returned' >/dev/ser1; fi\n"
            "done\n"
            "echo 'Starter variant worker: injecting F32 variant' >/dev/ser1\n"
            f"{wait_for_software_screen}"
            "/proc/boot/starter-variant\n"
            ") &\n"
        )

    native_sgx_libraries = (
        "echo 'Native SGX probe: staging PowerVR initializer and drivers in GRAPHICS_ROOT' >/dev/ser1\n"
        "for lib in /lib/graphics/omap5430/*.so; do\n"
        "  /bin/cp $lib /dev/shmem/ || exit 1\n"
        "done\n"
        "/bin/cp /lib/screen-pvr2d.so /dev/shmem/screen-pvr2d.so || exit 1\n"
        if native_sgx_probe else ""
    )
    software_screen_start = (
        "(\n"
        "if [ -e /dev/tiler ]; then\n"
        "  echo 'Software Screen probe: /dev/tiler node exists' >/dev/ser1\n"
        "else\n"
        "  echo 'Software Screen probe: /dev/tiler missing; continuing immediately' >/dev/ser1\n"
        "fi\n"
        "echo 'Software Screen probe: copying graphics configuration' >/dev/ser1\n"
        "/bin/cp /proc/boot/graphics-sw.conf /dev/shmem/graphics.conf || { echo 'Software Screen probe: graphics config copy failed' >/dev/ser1; exit 1; }\n"
        "echo 'Software Screen probe: copying screen-sw.so' >/dev/ser1\n"
        "/bin/cp /lib/screen-sw.so /dev/shmem/screen-sw.so || { echo 'Software Screen probe: screen-sw.so copy failed' >/dev/ser1; exit 1; }\n"
        "echo 'Software Screen probe: copying libswblit.so' >/dev/ser1\n"
        "/bin/cp /lib/libswblit.so.1 /dev/shmem/libswblit.so || { echo 'Software Screen probe: libswblit copy failed' >/dev/ser1; exit 1; }\n"
        f"{native_sgx_libraries}"
        "export GRAPHICS_ROOT=/dev/shmem\n"
        "export LD_LIBRARY_PATH=/dev/shmem:/lib/graphics/omap5430:/opt/sys/lib:/opt/car/lib:/lib:/usr/lib\n"
        "echo 'Software Screen probe: starting /bin/screen' >/dev/ser1\n"
        "/bin/screen -c /dev/shmem/graphics.conf >/dev/ser1 2>&1\n"
        "screen_status=$?\n"
        "echo \"Software Screen probe: /bin/screen exited with status $screen_status\" >/dev/ser1\n"
        ") &\n"
        if software_screen_probe else ""
    )

    screen_test_start = (
        "(\n"
        "n=0\n"
        "while [ ! -e /dev/screen ]; do\n"
        "  [ $n -lt 120 ] || exit 1\n"
        "  /boot/bin/sleep 1\n"
        "  n=$((n + 1))\n"
        "done\n"
        "echo 'Starting QNX Screen color-band test'\n"
        "/proc/boot/screen-test\n"
        ") &\n"
        if screen_test_helper else ""
    )

    screen_shared_ram_post_start = (
        "(\n"
        "n=0\n"
        "while [ ! -e /dev/screen ]; do\n"
        "  [ $n -lt 120 ] || { echo 'Screen shared-RAM post probe timed out waiting for /dev/screen' >/dev/ser1; exit 1; }\n"
        "  /boot/bin/sleep 1\n"
        "  n=$((n + 1))\n"
        "done\n"
        "echo 'Starting QNX Screen shared-RAM post probe' >/dev/ser1\n"
        "/proc/boot/screen-shared-ram-post >/dev/ser1 2>&1\n"
        "probe_status=$?\n"
        "echo \"Screen shared-RAM post probe exited with status $probe_status\" >/dev/ser1\n"
        ") &\n"
        if screen_shared_ram_post_probe else ""
    )

    native_shared_image_start = (
        "(\n"
        "n=0\n"
        "while [ ! -e /dev/screen ]; do\n"
        "  [ $n -lt 120 ] || { echo 'Native shared-image probe timed out waiting for /dev/screen' >/dev/ser1; exit 1; }\n"
        "  /boot/bin/sleep 1\n"
        "  n=$((n + 1))\n"
        "done\n"
        "echo 'Starting bounded native shared-image producer probe' >/dev/ser1\n"
        "/proc/boot/screen-native-shared-image-probe >/dev/ser1 2>&1\n"
        "probe_status=$?\n"
        "echo \"Native shared-image producer probe exited with status $probe_status\" >/dev/ser1\n"
        ") &\n"
        if native_shared_image_probe else ""
    )

    screen_hmi_contract_start = (
        "n=0\n"
        "while [ ! -e /dev/screen ]; do\n"
        "  [ $n -lt 120 ] || { echo 'HMI Screen contract probe timed out waiting for /dev/screen'; exit 1; }\n"
        "  /boot/bin/sleep 1\n"
        "  n=$((n + 1))\n"
        "done\n"
        "echo 'Starting HMI Screen contract probe'\n"
        "/proc/boot/screen-hmi-contract\n"
        "screen_contract_status=$?\n"
        "echo \"HMI Screen contract probe exited with status $screen_contract_status\"\n"
        if screen_hmi_contract_probe else ""
    )

    screen_ui_start = (
        "(\n"
        "n=0\n"
        "while [ ! -e /dev/screen ]; do\n"
        "  [ $n -lt 120 ] || exit 1\n"
        "  /boot/bin/sleep 1\n"
        "  n=$((n + 1))\n"
        "done\n"
        "echo 'Starting CPU-rendered F32 iDrive development preview'\n"
        "/proc/boot/idrive6-screen-ui\n"
        ") &\n"
        if screen_ui_probe else ""
    )

    graphics_process_dump = (
        "echo 'Skipping global pidin/slog snapshot; HmiMain3D gets PID-scoped lifecycle snapshots' >/dev/ser1\n"
        if os.environ.get("IDRIVE_HMI_FORCE_START") == "1"
        else (
            "/bin/pidin ar >/dev/ser1 2>&1 &\n"
            "/bin/pidin threads >/dev/ser1 2>&1 &\n"
            "(/bin/sloginfo | /bin/tail -n 160) >/dev/ser1 2>&1 &\n"
        )
    )
    graphics_diagnostics = (
        "(\n"
        "/boot/bin/sleep 30\n"
        "echo 'Graphics process snapshot after software Screen launch' >/dev/ser1\n"
        "if [ -e /dev/screen ]; then echo 'Graphics diagnostic: /dev/screen exists' >/dev/ser1; else echo 'Graphics diagnostic: /dev/screen missing' >/dev/ser1; fi\n"
        "if [ -e /dev/tiler ]; then echo 'Graphics diagnostic: /dev/tiler exists' >/dev/ser1; else echo 'Graphics diagnostic: /dev/tiler missing' >/dev/ser1; fi\n"
        + graphics_process_dump
        + "echo 'Graphics diagnostic queries started' >/dev/ser1\n"
        + ") &\n"
        if software_screen_probe else ""
    )

    # Query EGL through the same BMW forwarding libraries HmiMain3D loads.
    # The KD application-entry wrapper requires kdMain, which this standalone
    # diagnostic does not define. HmiMain3D keeps its original KD preload.
    egl_preload = (
        "LD_PRELOAD=libEGL_X.gpp.so:libGLESv2_X_FORWARD.gpp.so "
    )
    egl_diagnostic_start = (
        "(\n"
        "n=0\n"
        "while [ ! -e /dev/screen ]; do\n"
        "  if [ $n -ge 120 ]; then echo 'EGL diagnostic timed out waiting for /dev/screen' >/dev/ser1; exit 1; fi\n"
        "  /boot/bin/sleep 1\n"
        "  n=$((n + 1))\n"
        "done\n"
        "echo 'Querying EGL configs on the active QNX Screen display'\n"
        "GRAPHICS_ROOT=/dev/shmem "
        "LD_LIBRARY_PATH=/dev/shmem:/opt/hmi/ID5/lib:/opt/hmi/lib:/opt/hmi/otf:/boot/lib:/lib:/usr/lib:/opt/sys/lib:/opt/car/lib:.:/lib/graphics/omap5430 "
        f"{egl_preload}"
        "/proc/boot/egl-config-diagnostic\n"
        ") >/dev/ser1 2>&1 &\n"
        if egl_diagnostics else ""
    )

    hmi_force_start = ""
    if os.environ.get("IDRIVE_HMI_FORCE_START") == "1":
        if not software_screen_probe or not variant_helper:
            raise RuntimeError(
                "IDRIVE_HMI_FORCE_START requires the development variant and software Screen probe"
            )
        hmi_layer_manager = os.environ.get("IDRIVE_HMI_LAYER_MANAGER", "").strip().lower()
        if hmi_layer_manager not in {"", "sdl", "glfw"}:
            raise RuntimeError("IDRIVE_HMI_LAYER_MANAGER must be 'sdl' or 'glfw'")
        hmi_layer_manager_arg = (
            f" -lm={hmi_layer_manager}" if hmi_layer_manager else ""
        )
        hmi_run_id = os.environ.get("IDRIVE_HMI_RUN_ID", "")
        hmi_run_marker = ""
        if hmi_run_id:
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", hmi_run_id):
                raise RuntimeError("IDRIVE_HMI_RUN_ID contains unsupported characters")
            hmi_run_marker = f"echo 'IDRIVE_HMI_RUN_ID={hmi_run_id}' >/dev/ser1\n"
        # Mirror the exact graphics preloads selected by HmiMain3D's original
        # starter.cfg process entry. These BMW wrappers are present in the
        # staged runtime and forward EGL/GLES/KD calls to the recovered QNX
        # graphics stack; bypassing them changes the native startup path.
        hmi_preloads = "libEGL_X.gpp.so:libGLESv2_X_FORWARD.gpp.so:libKD_X.gpp.so"
        if controller_library:
            hmi_preloads += ":/proc/boot/libidrive-hmi-controller.so"
        hmi_gpp_preload = f"LD_PRELOAD={hmi_preloads} "
        hmi_angle_uses_private_stack = (
            os.environ.get("IDRIVE_ANGLE_EGL_HMI") == "1"
        )
        pdebug_start = ""
        if os.environ.get("IDRIVE_QNX_PDEBUG") == "1":
            if not hmi_angle_uses_private_stack or os.environ.get("IDRIVE_QEMU_CDC_NETWORK") != "1":
                raise RuntimeError("QNX pdebug requires the HMI's isolated CDC network stack")
            pdebug_port = os.environ.get("IDRIVE_QNX_PDEBUG_PORT", "8001")
            if not re.fullmatch(r"[0-9]{1,5}", pdebug_port) or not 1024 <= int(pdebug_port) <= 65535:
                raise RuntimeError("IDRIVE_QNX_PDEBUG_PORT must be between 1024 and 65535")
            pdebug_start = (
                "echo 'Starting QNX process-debug support' >/dev/ser1\n"
                f"SOCK=/idrive /fs/sda0/bin/pdebug -f {int(pdebug_port)} >/dev/ser1 2>&1 &\n"
                "pdebug_pid=$!\n"
                "/boot/bin/sleep 1\n"
                "if ! kill -0 $pdebug_pid 2>/dev/null; then echo 'QNX pdebug failed to start' >/dev/ser1; exit 1; fi\n"
                f"echo \"QNX pdebug process started pid=$pdebug_pid port={int(pdebug_port)} stack=/idrive\" >/dev/ser1\n"
                "echo 'QNX isolated-stack socket table after pdebug start' >/dev/ser1\n"
                "SOCK=/idrive /bin/netstat -an >/dev/ser1 2>&1\n"
            )
        hmi_rpc_stack_env = (
            # Select the isolated stack before HmiMain3D starts. The provider
            # can then create its RPC socket without changing the process-wide
            # SOCK environment while BMW's worker threads are active.
            "SOCK=/idrive IDRIVE_ANGLE_RPC_SOCK=/idrive "
            + (
                f"IDRIVE_ANGLE_HMI_SURFACE_WIDTH={angle_hmi_surface_width} "
                f"IDRIVE_ANGLE_HMI_SURFACE_HEIGHT={angle_hmi_surface_height} "
                if angle_hmi_surface_width else ""
            )
            if hmi_angle_uses_private_stack else ""
        )
        if hmi_angle_uses_private_stack:
            hmi_network_setup = (
                "echo 'Waiting for QEMU CDC device on USB bus 0, device 1' >/dev/ser1\n"
                "n=0\n"
                "USB_OUTPUT=''\n"
                "while [ $n -lt 30 ]; do\n"
                "  USB_OUTPUT=$(/bin/usb -b0 -d1 2>/dev/null)\n"
                "  case \"$USB_OUTPUT\" in *0xa4a1*) break ;; esac\n"
                "  /boot/bin/sleep 1\n"
                "  n=$((n + 1))\n"
                "done\n"
                "case \"$USB_OUTPUT\" in\n"
                "  *0xa4a1*)\n"
                "    echo 'Starting isolated QNX IPv4 stack and loading its ECM driver' >/dev/ser1\n"
                "    /bin/io-pkt-v4-hc -i1 -S -d /lib/devnp-ecm.so path=/dev/io-usb/io-usb,busnum=0,devnum=1,verbose -ptcpip stacksize=16384,mclbytes=4096,enmap=0,pkt_typed_mem=/ram/dma/sysram,prefix=/idrive >/dev/ser1 2>&1 &\n"
                "    angle_stack_pid=$!\n"
                "    echo \"ANGLE RPC io-pkt1 pid=$angle_stack_pid\" >/dev/ser1\n"
                "    n=0\n"
                "    while [ $n -lt 30 ] && [ ! -e /idrive/dev/socket ]; do /boot/bin/sleep 1; n=$((n + 1)); done\n"
                "    if [ ! -e /idrive/dev/socket ]; then echo 'ANGLE RPC stack did not create /idrive/dev/socket' >/dev/ser1; exit 1; fi\n"
                "    echo 'Waiting for IPv4 on the isolated QNX stack' >/dev/ser1\n"
                "    n=0\n"
                "    while [ $n -lt 30 ]; do\n"
                "      if SOCK=/idrive /bin/ifconfig ecm0 160.48.199.225/24 up >/dev/null 2>&1; then break; fi\n"
                "      /boot/bin/sleep 1\n"
                "      n=$((n + 1))\n"
                "    done\n"
                "    if [ $n -ge 30 ]; then\n"
                "      echo 'ANGLE RPC ecm0 setup on /idrive failed after 30 retries' >/dev/ser1\n"
                "      SOCK=/idrive /bin/ifconfig -a >/dev/ser1 2>&1\n"
                "      SOCK=/idrive /bin/netstat -rn >/dev/ser1 2>&1\n"
                "      for diagnostic in arguments threads times fds; do\n"
                "        echo \"ANGLE_RPC_STACK_DIAGNOSTIC_BEGIN $diagnostic pid=$angle_stack_pid\" >/dev/ser1\n"
                "        /bin/pidin -p $angle_stack_pid $diagnostic >/dev/ser1 2>&1\n"
                "        echo \"ANGLE_RPC_STACK_DIAGNOSTIC_END $diagnostic\" >/dev/ser1\n"
                "      done\n"
                "      exit 1\n"
                "    fi\n"
                "    SOCK=/idrive /bin/route add default 160.48.199.253 >/dev/ser1 2>&1 || { echo 'ANGLE RPC default route on /idrive failed' >/dev/ser1; exit 1; }\n"
                "    n=0\n"
                "    while [ $n -lt 30 ]; do\n"
                "      if SOCK=/idrive /bin/ping -c 1 160.48.199.253 >/dev/null 2>&1; then break; fi\n"
                "      /boot/bin/sleep 1\n"
                "      n=$((n + 1))\n"
                "    done\n"
                "    if [ $n -ge 30 ]; then\n"
                "      echo 'ANGLE RPC gateway ping through /idrive failed after 30 retries' >/dev/ser1\n"
                "      SOCK=/idrive /bin/ifconfig -a >/dev/ser1 2>&1\n"
                "      SOCK=/idrive /bin/netstat -rn >/dev/ser1 2>&1\n"
                "      SOCK=/idrive /bin/ping -c 1 160.48.199.253 >/dev/ser1 2>&1\n"
                "      exit 1\n"
                "    fi\n"
                "    echo 'ANGLE RPC isolated network ready: SOCK=/idrive, ecm0=160.48.199.225' >/dev/ser1\n"
                "    ;;\n"
                "  *)\n"
                "    echo 'QEMU CDC device 0xa4a1 did not appear within 30 guest seconds' >/dev/ser1\n"
                "    exit 1\n"
                "    ;;\n"
                "esac\n"
            )
        else:
            hmi_network_setup = (
            "echo 'Waiting for QEMU CDC device on USB bus 0, device 1' >/dev/ser1\n"
            "n=0\n"
            "USB_OUTPUT=''\n"
            "while [ $n -lt 30 ]; do\n"
            "  USB_OUTPUT=$(/bin/usb -b0 -d1 2>/dev/null)\n"
            "  case \"$USB_OUTPUT\" in *0xa4a1*) break ;; esac\n"
            "  /boot/bin/sleep 1\n"
            "  n=$((n + 1))\n"
            "done\n"
            "case \"$USB_OUTPUT\" in\n"
            "  *0xa4a1*)\n"
            "    echo 'Loading BMW QNX ECM driver for QEMU CDC Ethernet' >/dev/ser1\n"
            "    /bin/mount -T io-pkt -o path=/dev/io-usb/io-usb,busnum=0,devnum=1,verbose /lib/devnp-ecm.so >/dev/ser1 2>&1\n"
            "    /bin/ifconfig ecm0 160.48.199.225/24 up >/dev/ser1 2>&1\n"
            "    /bin/route add default 160.48.199.253 >/dev/ser1 2>&1\n"
            "    /bin/ping -c 1 160.48.199.253 >/dev/ser1 2>&1\n"
            "    ;;\n"
            "  *)\n"
            "    echo 'QEMU CDC device 0xa4a1 did not appear within 30 guest seconds' >/dev/ser1\n"
            "    ;;\n"
            "esac\n"
            )
        if os.environ.get("IDRIVE_QEMU_CDC_NETWORK") != "1":
            hmi_network_setup = ""
        hmi_network_diagnostics = (
            "echo 'QNX network interfaces:' >/dev/ser1\n"
            "/bin/usb >/dev/ser1 2>&1\n"
            "/bin/ifconfig -a >/dev/ser1 2>&1\n"
            "/bin/netstat -rn >/dev/ser1 2>&1\n"
            + (
                "echo 'ANGLE RPC isolated-stack interfaces and routes:' >/dev/ser1\n"
                "SOCK=/idrive /bin/ifconfig -a >/dev/ser1 2>&1\n"
                "SOCK=/idrive /bin/netstat -rn >/dev/ser1 2>&1\n"
                if hmi_angle_uses_private_stack else ""
            )
            if os.environ.get("IDRIVE_NETWORK_DIAGNOSTICS") == "1"
            else ""
        )
        hmi_angle_network_preflight = (
            "echo 'ANGLE EGL preflight on the isolated QNX stack' >/dev/ser1\n"
            "GRAPHICS_ROOT=/dev/shmem SOCK=/idrive IDRIVE_ANGLE_RPC_SOCK=/idrive "
            "LD_LIBRARY_PATH=/dev/shmem:/opt/hmi/ID5/lib:/opt/hmi/lib:/opt/hmi/otf:/boot/lib:/lib:/usr/lib:/opt/sys/lib:/opt/car/lib:.:/lib/graphics/omap5430 "
            "LD_PRELOAD=libEGL_X.gpp.so:libGLESv2_X_FORWARD.gpp.so "
            "/proc/boot/egl-angle-provider-smoke >/dev/ser1 2>&1\n"
            "angle_preflight_status=$?\n"
            "echo \"ANGLE EGL isolated-stack preflight exited with status $angle_preflight_status\" >/dev/ser1\n"
            "if [ $angle_preflight_status -ne 0 ]; then\n"
            "  echo 'ANGLE isolated-stack state after failed EGL preflight' >/dev/ser1\n"
            "  SOCK=/idrive /bin/ifconfig -a >/dev/ser1 2>&1\n"
            "  SOCK=/idrive /bin/netstat -rn >/dev/ser1 2>&1\n"
            "  SOCK=/idrive /bin/netstat -an >/dev/ser1 2>&1\n"
            "  for diagnostic in arguments threads fds; do\n"
            "    echo \"ANGLE_RPC_STACK_DIAGNOSTIC_BEGIN $diagnostic pid=$angle_stack_pid\" >/dev/ser1\n"
            "    /bin/pidin -p $angle_stack_pid $diagnostic >/dev/ser1 2>&1\n"
            "    echo \"ANGLE_RPC_STACK_DIAGNOSTIC_END $diagnostic\" >/dev/ser1\n"
            "  done\n"
            "fi\n"
            if angle_egl_hmi_preflight else ""
        )
        hmi_angle_post_otf_preflight = (
            "echo 'ANGLE EGL post-OTF preflight on the isolated QNX stack' >/dev/ser1\n"
            "GRAPHICS_ROOT=/dev/shmem SOCK=/idrive IDRIVE_ANGLE_RPC_SOCK=/idrive "
            "LD_LIBRARY_PATH=/dev/shmem:/opt/hmi/ID5/lib:/opt/hmi/lib:/opt/hmi/otf:/boot/lib:/lib:/usr/lib:/opt/sys/lib:/opt/car/lib:.:/lib/graphics/omap5430 "
            "LD_PRELOAD=libEGL_X.gpp.so:libGLESv2_X_FORWARD.gpp.so "
            "/proc/boot/egl-angle-provider-smoke >/dev/ser1 2>&1\n"
            "angle_post_otf_preflight_status=$?\n"
            "echo \"ANGLE EGL isolated-stack post-OTF preflight exited with status $angle_post_otf_preflight_status\" >/dev/ser1\n"
            "if [ $angle_post_otf_preflight_status -ne 0 ]; then\n"
            "  echo 'ANGLE isolated-stack state after failed post-OTF EGL preflight' >/dev/ser1\n"
            "  SOCK=/idrive /bin/ifconfig -a >/dev/ser1 2>&1\n"
            "  SOCK=/idrive /bin/netstat -rn >/dev/ser1 2>&1\n"
            "  SOCK=/idrive /bin/netstat -an >/dev/ser1 2>&1\n"
            "fi\n"
            if os.environ.get("IDRIVE_ANGLE_EGL_HMI_POST_OTF_PREFLIGHT") == "1"
            else ""
        )
        hmi_communication_modules = os.environ.get(
            "IDRIVE_HMI_COMM_MODULES", "DSI,MOSTSubSystem"
        )
        if hmi_communication_modules not in {
            "DSI",
            "MOSTSubSystem",
            "DSI,MOSTSubSystem",
        }:
            raise RuntimeError(
                "IDRIVE_HMI_COMM_MODULES must be DSI, MOSTSubSystem, or DSI,MOSTSubSystem"
            )
        hmi_communication_args = (
            ""
            if os.environ.get("IDRIVE_HMI_NO_COMMS") == "1"
            else f"-c={hmi_communication_modules} "
        )
        otf_agent_start = ""
        if os.environ.get("IDRIVE_OTF_CAPTURE") == "1":
            if not hmi_angle_uses_private_stack:
                raise RuntimeError("OTF capture requires the HMI's isolated QNX network stack")
            otf_agent_start = (
                "otf_agent_pid=\n"
                "echo 'Starting BMW OTF agent after the isolated QNX network is ready' >/dev/ser1\n"
                "SOCK=/idrive /opt/hmi/otf/BMWOTFagent /opt/hmi/otf/socket.cfg >/dev/ser1 2>&1 &\n"
                "otf_agent_pid=$!\n"
                "n=0\n"
                "while [ ! -e /dev/BMWOTFagent ] && [ $n -lt 10 ]; do\n"
                "  /boot/bin/sleep 1\n"
                "  n=$((n + 1))\n"
                "done\n"
                "if [ ! -e /dev/BMWOTFagent ]; then echo 'BMW OTF agent did not create /dev/BMWOTFagent' >/dev/ser1; exit 1; fi\n"
                "echo \"BMW OTF agent ready pid=$otf_agent_pid\" >/dev/ser1\n"
            )
        # Keep system logging off the serial console during lifecycle capture.
        # A concurrent sloginfo stream interleaves with pidin's framed output,
        # making thread-state snapshots impossible to parse reliably.
        mailbox_env = ("export IDRIVE_ANGLE_EGL_MAILBOX=1\n"
                       if os.environ.get("IDRIVE_ANGLE_EGL_MAILBOX") == "1" else "")
        hmi_usb_setup = (
            "if [ ! -e /dev/io-usb/io-usb ]; then\n"
            "  echo 'Starting QEMU EHCI directly (no physical I2C/sysregs prerequisites)' >/dev/ser1\n"
            "  /bin/io-usb -c -vvv -d hb-ehci-omap3 ioport=0x4a064c00,irq=109,verbose=5,num_itd=256,portd >/dev/shmem/idrive-ehci.log 2>&1 &\n"
            "fi\n"
            if os.environ.get("IDRIVE_DIRECT_EHCI") == "1" else ""
        )
        hmi_layer_manager_setup = (
            "if [ ! -e /dev/layermanager ]; then\n"
            "  echo 'Starting native LayerManagerService directly (Screen already ready)' >/dev/ser1\n"
            "  /opt/sys/bin/LayerManagerService -w1440 -h540 -d:1 >/dev/ser1 2>&1 &\n"
            "  n=0\n"
            "  while [ ! -e /dev/layermanager ] && [ $n -lt 30 ]; do /boot/bin/sleep 1; n=$((n + 1)); done\n"
            "  if [ ! -e /dev/layermanager ]; then echo 'Direct LayerManagerService did not become ready' >/dev/ser1; exit 1; fi\n"
            "fi\n"
            if os.environ.get("IDRIVE_DIRECT_LAYER_MANAGER") == "1" else ""
        )
        hmi_force_start = (
            "(\n"
            f"{hmi_run_marker}"
            "echo 'HmiMain3D startup worker waiting for /dev/screen' >/dev/ser1\n"
            "n=0\n"
            "while [ ! -e /dev/screen ]; do\n"
            "  if [ $n -ge 120 ]; then echo 'HmiMain3D startup timed out waiting for /dev/screen' >/dev/ser1; exit 1; fi\n"
            "  if [ $n -eq 0 ]; then echo 'HmiMain3D startup worker: sleeping for 1 guest second' >/dev/ser1; fi\n"
            "  /boot/bin/sleep 1\n"
            "  n=$((n + 1))\n"
            "  if [ $n -eq 1 ]; then echo 'HmiMain3D startup worker: guest sleep returned' >/dev/ser1; fi\n"
            "done\n"
            "export MALLOC_ARENA_SIZE=65536\n"
            "export GRAPHICS_ROOT=/dev/shmem\n"
            f"{mailbox_env}"
            "export LD_LIBRARY_PATH=/dev/shmem:/opt/hmi/ID5/lib:/opt/hmi/lib:/opt/hmi/otf:/boot/lib:/lib:/usr/lib:/opt/sys/lib:/opt/car/lib:.:/lib/graphics/omap5430\n"
            f"{hmi_usb_setup}"
            f"{hmi_network_setup}"
            f"{hmi_network_diagnostics}"
            f"{pdebug_start}"
            f"{hmi_angle_network_preflight}"
            f"{otf_agent_start}"
            f"{hmi_angle_post_otf_preflight}"
            f"{hmi_layer_manager_setup}"
            "echo 'Preparing HmiMain3D writable data directories on the root volume' >/dev/ser1\n"
            "/bin/ls -ld /dev/shmem /fs/sda0/opt/hmi/data /var >/dev/ser1 2>&1\n"
            "for hmi_data_dir in /fs/sda0/opt/hmi/data/rw /fs/sda0/opt/hmi/data/rw/RHMI-Cache /fs/sda0/opt/hmi/data/rw/RHMI-Cache/FbmTxtPers /fs/sda0/opt/hmi/data/rw/RHMI-Cache/PersistentA4ARes; do\n"
            "  if [ ! -d \"$hmi_data_dir\" ]; then\n"
            "    echo \"Creating $hmi_data_dir\" >/dev/ser1\n"
            "    if ! /bin/mkdir \"$hmi_data_dir\"; then echo \"Failed to create HmiMain3D writable path: $hmi_data_dir\" >/dev/ser1; exit 1; fi\n"
            "  fi\n"
            "done\n"
            "/bin/ls -ld /fs/sda0/opt/hmi/data/rw /fs/sda0/opt/hmi/data/rw/RHMI-Cache/FbmTxtPers /fs/sda0/opt/hmi/data/rw/RHMI-Cache/PersistentA4ARes >/dev/ser1 2>&1\n"
            "echo 'HmiMain3D writable data directories ready' >/dev/ser1\n"
            "echo 'Starting HmiMain3D directly after Screen is ready (development override)'\n"
            f"{hmi_rpc_stack_env}{hmi_gpp_preload}exec "
            f"/opt/hmi/ID5/bin/HmiMain3D {hmi_communication_args}-ro=/opt/hmi/data/ro/ -rw=/fs/sda0/opt/hmi/data/rw/ -sp=/fs/sda0/opt/hmi/data/rw/ -vp=/opt/hmi/data/ro/ -cp=/opt/hmi/data/ro/ -iba1=/mnt/data/iba/swe1/ -iba2=/mnt/data/iba/anim-all/swe2/ -h=10000 -z=4"
            f"{hmi_layer_manager_arg} >/dev/ser1 2>&1 &\n"
            "hmi_pid=$!\n"
            "echo \"HmiMain3D exec process pid=$hmi_pid\" >/dev/ser1\n"
            "sample_previous=0\n"
            "for sample_at in 2 4 6 8 10 12 15 20 30 60 65 70 75 80 85 90 120; do\n"
            "  sample_delay=$((sample_at - sample_previous))\n"
            "  /boot/bin/sleep $sample_delay\n"
            "  sample_previous=$sample_at\n"
            "  for diagnostic in threads times; do\n"
            "    echo \"HMI_DIAGNOSTIC_BEGIN t+${sample_at}s $diagnostic\" >/dev/ser1\n"
            "    /bin/pidin -p $hmi_pid $diagnostic >/dev/ser1 2>&1\n"
            "    echo \"HMI_DIAGNOSTIC_END t+${sample_at}s $diagnostic\" >/dev/ser1\n"
            "  done\n"
            "  if [ \"$sample_at\" -eq 15 ]; then\n"
            "    for diagnostic in arguments mapinfo fds; do\n"
            "      echo \"HMI_DIAGNOSTIC_BEGIN t+${sample_at}s $diagnostic\" >/dev/ser1\n"
            "      /bin/pidin -p $hmi_pid $diagnostic >/dev/ser1 2>&1\n"
            "      echo \"HMI_DIAGNOSTIC_END t+${sample_at}s $diagnostic\" >/dev/ser1\n"
            "    done\n"
            "  fi\n"
            "  if [ \"$sample_at\" -eq 60 ]; then\n"
            "    echo \"HMI_DIAGNOSTIC_BEGIN t+${sample_at}s fds\" >/dev/ser1\n"
            "    /bin/pidin -p $hmi_pid fds >/dev/ser1 2>&1\n"
            "    echo \"HMI_DIAGNOSTIC_END t+${sample_at}s fds\" >/dev/ser1\n"
            "  fi\n"
            "  if [ \"$sample_at\" -eq 75 ] && [ -n \"${angle_stack_pid:-}\" ]; then\n"
            "    echo 'ANGLE private-stack health check at HMI t+75s' >/dev/ser1\n"
            "    if kill -0 $angle_stack_pid 2>/dev/null; then echo \"io-pkt1 pid=$angle_stack_pid is alive\" >/dev/ser1; else echo \"io-pkt1 pid=$angle_stack_pid is not running\" >/dev/ser1; fi\n"
            "    /bin/pidin -p $angle_stack_pid arguments >/dev/ser1 2>&1\n"
            "    /bin/pidin -p $angle_stack_pid times >/dev/ser1 2>&1\n"
            "    SOCK=/idrive /bin/ifconfig -a >/dev/ser1 2>&1\n"
            "    SOCK=/idrive /bin/netstat -an >/dev/ser1 2>&1\n"
            "    echo 'ANGLE private-stack socket probe at HMI t+75s' >/dev/ser1\n"
            "    SOCK=/idrive /bin/ping -c 1 160.48.199.253 >/dev/ser1 2>&1\n"
            "  fi\n"
            "  if [ \"$sample_at\" -eq 120 ]; then\n"
            "    echo \"HMI_DIAGNOSTIC_BEGIN t+${sample_at}s fds\" >/dev/ser1\n"
            "    /bin/pidin -p $hmi_pid fds >/dev/ser1 2>&1\n"
            "    echo \"HMI_DIAGNOSTIC_END t+${sample_at}s fds\" >/dev/ser1\n"
            + (
                "    if kill -0 $hmi_pid 2>/dev/null; then\n"
                "      echo \"$hmi_pid\" | /proc/boot/hmi-title-cache >/dev/ser1 2>&1\n"
                "    fi\n"
                if title_cache_helper else ""
            )
            + "  fi\n"
            "  if kill -0 $hmi_pid 2>/dev/null; then\n"
            "    echo \"HmiMain3D exec PID remains alive at t+${sample_at}s\" >/dev/ser1\n"
            "  else\n"
            "    echo \"HmiMain3D exec PID is no longer running at t+${sample_at}s\" >/dev/ser1\n"
            "  fi\n"
            "done\n"
            "if [ -n \"${otf_agent_pid:-}\" ]; then\n"
            "  for diagnostic in arguments threads fds; do\n"
            "    echo \"OTF_AGENT_DIAGNOSTIC_BEGIN t+120s $diagnostic pid=$otf_agent_pid\" >/dev/ser1\n"
            "    /bin/pidin -p $otf_agent_pid $diagnostic >/dev/ser1 2>&1\n"
            "    echo \"OTF_AGENT_DIAGNOSTIC_END t+120s $diagnostic\" >/dev/ser1\n"
            "  done\n"
            "fi\n"
            "echo 'Default-stack TCP sockets at t+120' >/dev/ser1\n"
            "/bin/netstat -rn >/dev/ser1 2>&1\n"
            "/bin/netstat -an >/dev/ser1 2>&1\n"
            "echo 'ANGLE private-stack TCP sockets at t+120' >/dev/ser1\n"
            "SOCK=/idrive /bin/netstat -rn >/dev/ser1 2>&1\n"
            "SOCK=/idrive /bin/netstat -an >/dev/ser1 2>&1\n"
            "echo 'Starting severity-filtered QNX system log after the final HMI snapshot' >/dev/ser1\n"
            "/bin/sloginfo -s 5 -w >/dev/ser1 2>&1 &\n"
            "wait $hmi_pid\n"
            "hmi_status=$?\n"
            "echo \"HmiMain3D exited with status $hmi_status\"\n"
            "if [ \"$hmi_status\" -ne 0 ]; then\n"
            "  unset LD_PRELOAD\n"
            "  if [ -n \"${angle_stack_pid:-}\" ]; then\n"
            "    echo \"ANGLE isolated-stack state after HmiMain3D exit pid=$angle_stack_pid\" >/dev/ser1\n"
            "    SOCK=/idrive /bin/ifconfig -a >/dev/ser1 2>&1\n"
            "    SOCK=/idrive /bin/netstat -rn >/dev/ser1 2>&1\n"
            "    SOCK=/idrive /bin/netstat -an >/dev/ser1 2>&1\n"
            "    for diagnostic in arguments threads fds; do\n"
            "      echo \"ANGLE_RPC_STACK_EXIT_DIAGNOSTIC_BEGIN $diagnostic pid=$angle_stack_pid\" >/dev/ser1\n"
            "      /bin/pidin -p $angle_stack_pid $diagnostic >/dev/ser1 2>&1\n"
            "      echo \"ANGLE_RPC_STACK_EXIT_DIAGNOSTIC_END $diagnostic\" >/dev/ser1\n"
            "    done\n"
            "  fi\n"
            "  echo 'Inspecting stale HmiMain3D Screen surface 256 and layer 2147483648'\n"
            "  /opt/sys/bin/LayerManagerControl get surface 256 >/dev/ser1 2>&1\n"
            "  /opt/sys/bin/LayerManagerControl get layer 2147483648 >/dev/ser1 2>&1\n"
            "  echo 'Leaving Screen layers unchanged for the development preview'\n"
            "fi\n"
            ") &\n"
        )

    extraction_diagnostics = (
        "exec >/dev/ser1 2>&1\nset -x\n"
        "(/boot/bin/sleep 5; /boot/bin/pidin ar; /boot/bin/pidin threads) &\n"
        if storage_diagnostics else ""
    )
    rootfs_ready_hold_script = (
        f"echo 'Rootfs-ready snapshot window: holding for {rootfs_ready_hold} guest seconds'\n"
        f"/boot/bin/sleep {rootfs_ready_hold}\n"
        if rootfs_ready_hold else ""
    )
    sgx_size_log_probe = (
        "echo 'Streaming PowerVR SGXMKIF size diagnostics from QNX slogger' >/dev/ser1\n"
        "(/bin/sloginfo -m 8 -w >/dev/ser1 2>&1) &\n"
        if os.environ.get("IDRIVE_SGX_SIZE_LOG_PROBE") == "1"
        else ""
    )
    shader_parser_probe_start = (
        "echo 'Running authentic BMW shader parser probe without EGL or Screen'\n"
        "LD_LIBRARY_PATH=/lib/graphics/omap5430_ES2_0:/lib:/usr/lib "
        "/proc/boot/shader-parser-probe\n"
        "shader_parser_probe_status=$?\n"
        "echo \"Shader parser probe exited with status $shader_parser_probe_status\"\n"
        if shader_parser_probe else ""
    )
    angle_rpc_smoke_start = (
        "(\n"
        "echo 'ANGLE RPC smoke: starting the QEMU-safe EHCI USB controller' >/dev/ser1\n"
        "if [ ! -e /dev/io-usb/io-usb ]; then\n"
        "  /bin/io-usb -c -vvv -d hb-ehci-omap3 ioport=0x4a064c00,irq=109,verbose=5,num_itd=256,portd >/dev/ser1 2>&1 &\n"
        "  /boot/bin/sleep 1\n"
        "fi\n"
        "echo 'ANGLE RPC smoke: waiting for QEMU CDC Ethernet' >/dev/ser1\n"
        "n=0\n"
        "while [ $n -lt 60 ]; do\n"
        "  if [ -e /dev/io-usb/io-usb ]; then\n"
        "    USB_OUTPUT=$(/bin/usb -b0 -d1 2>/dev/null)\n"
        "    case \"$USB_OUTPUT\" in *0xa4a1*) break ;; esac\n"
        "  fi\n"
        "  /boot/bin/sleep 1\n"
        "  n=$((n + 1))\n"
        "done\n"
        "case \"$USB_OUTPUT\" in\n"
        "  *0xa4a1*)\n"
        "    echo 'ANGLE RPC smoke: starting QNX IPv4 io-pkt stack' >/dev/ser1\n"
        "    if [ ! -e /dev/socket ]; then\n"
        "      /bin/io-pkt-v4-hc -S -ptcpip stacksize=16384,mclbytes=4096,enmap=0,pkt_typed_mem=/ram/dma/sysram >/dev/ser1 2>&1 &\n"
        "      n=0\n"
        "      while [ $n -lt 30 ] && [ ! -e /dev/socket ]; do /boot/bin/sleep 1; n=$((n + 1)); done\n"
        "    fi\n"
        "    if [ ! -e /dev/socket ]; then echo 'ANGLE RPC smoke: io-pkt did not create /dev/socket' >/dev/ser1; exit 1; fi\n"
        "    /bin/mount -T io-pkt -o path=/dev/io-usb/io-usb,busnum=0,devnum=1 /lib/devnp-ecm.so >/dev/ser1 2>&1\n"
        "    ecm_status=$?\n"
        "    if [ $ecm_status -ne 0 ]; then echo \"ANGLE RPC smoke: ECM mount failed status=$ecm_status\" >/dev/ser1; exit 1; fi\n"
        "    /bin/ifconfig ecm0 160.48.199.225/24 up >/dev/ser1 2>&1\n"
        "    /bin/route add default 160.48.199.253 >/dev/ser1 2>&1\n"
        "    /bin/ping -c 1 160.48.199.253 >/dev/ser1 2>&1 || { echo 'ANGLE RPC smoke: QEMU gateway ping failed' >/dev/ser1; exit 1; }\n"
        "    echo 'ANGLE RPC smoke: sending 64x64 ES2 frame request' >/dev/ser1\n"
        "    /proc/boot/angle-rpc-client >/dev/ser1 2>&1\n"
        "    rpc_status=$?\n"
        "    echo \"ANGLE RPC smoke client exited with status $rpc_status\" >/dev/ser1\n"
        "    ;;\n"
        "  *) echo 'ANGLE RPC smoke: CDC device 0xa4a1 did not appear' >/dev/ser1 ;;\n"
        "esac\n"
        ") &\n"
        if angle_rpc_smoke else ""
    )
    angle_egl_rpc_smoke_start = (
        "(\n"
        "echo 'ANGLE EGL provider smoke: starting the QEMU-safe EHCI USB controller' >/dev/ser1\n"
        "if [ ! -e /dev/io-usb/io-usb ]; then\n"
        "  /bin/io-usb -c -vvv -d hb-ehci-omap3 ioport=0x4a064c00,irq=109,verbose=5,num_itd=256,portd >/dev/ser1 2>&1 &\n"
        "  /boot/bin/sleep 1\n"
        "fi\n"
        "echo 'ANGLE EGL provider smoke: waiting for QEMU CDC Ethernet' >/dev/ser1\n"
        "n=0\n"
        "USB_OUTPUT=''\n"
        "while [ $n -lt 60 ]; do\n"
        "  if [ -e /dev/io-usb/io-usb ]; then\n"
        "    /bin/usb -b0 -d1 >/dev/shmem/angle-egl-usb.txt 2>/dev/null\n"
        "    USB_OUTPUT=''\n"
        "    while IFS= read -r USB_LINE; do case \"$USB_LINE\" in *0xa4a1*) USB_OUTPUT=found; break ;; esac; done </dev/shmem/angle-egl-usb.txt\n"
        "    if [ \"$USB_OUTPUT\" = found ]; then break; fi\n"
        "  fi\n"
        "  /boot/bin/sleep 1\n"
        "  n=$((n + 1))\n"
        "done\n"
        "if [ \"$USB_OUTPUT\" = found ]; then\n"
        "    echo 'ANGLE EGL provider smoke: starting QNX IPv4 io-pkt stack' >/dev/ser1\n"
        "    if [ ! -e /dev/socket ]; then\n"
        "      /bin/io-pkt-v4-hc -S -ptcpip stacksize=16384,mclbytes=4096,enmap=0,pkt_typed_mem=/ram/dma/sysram >/dev/ser1 2>&1 &\n"
        "      n=0\n"
        "      while [ $n -lt 30 ] && [ ! -e /dev/socket ]; do /boot/bin/sleep 1; n=$((n + 1)); done\n"
        "    fi\n"
        "    if [ ! -e /dev/socket ]; then echo 'ANGLE EGL provider smoke: io-pkt did not create /dev/socket' >/dev/ser1; exit 1; fi\n"
        "    /bin/mount -T io-pkt -o path=/dev/io-usb/io-usb,busnum=0,devnum=1 /lib/devnp-ecm.so >/dev/ser1 2>&1\n"
        "    ecm_status=$?\n"
        "    if [ $ecm_status -ne 0 ]; then echo \"ANGLE EGL provider smoke: ECM mount failed status=$ecm_status\" >/dev/ser1; exit 1; fi\n"
        "    /bin/ifconfig ecm0 160.48.199.225/24 up >/dev/ser1 2>&1\n"
        "    /bin/route add default 160.48.199.253 >/dev/ser1 2>&1\n"
        "    /bin/ping -c 1 160.48.199.253 >/dev/ser1 2>&1 || { echo 'ANGLE EGL provider smoke: QEMU gateway ping failed' >/dev/ser1; exit 1; }\n"
        "    echo 'ANGLE EGL provider smoke: waiting for QNX Screen' >/dev/ser1\n"
        "    n=0\n"
        "    while [ $n -lt 120 ] && [ ! -e /dev/screen ]; do /boot/bin/sleep 1; n=$((n + 1)); done\n"
        "    if [ ! -e /dev/screen ]; then echo 'ANGLE EGL provider smoke: Screen did not create /dev/screen' >/dev/ser1; exit 1; fi\n"
        "    GRAPHICS_ROOT=/dev/shmem LD_LIBRARY_PATH=/dev/shmem:/opt/hmi/ID5/lib:/opt/hmi/lib:/opt/hmi/otf:/boot/lib:/lib:/usr/lib:/opt/sys/lib:/opt/car/lib:.:/lib/graphics/omap5430 LD_PRELOAD=libEGL_X.gpp.so:libGLESv2_X_FORWARD.gpp.so /proc/boot/egl-angle-provider-smoke >/dev/ser1 2>&1\n"
        "    smoke_status=$?\n"
        "    echo \"ANGLE EGL provider smoke exited with status $smoke_status\" >/dev/ser1\n"
        + (
            "    if [ $smoke_status -ne 0 ]; then exit 1; fi\n"
            "    echo 'ANGLE Screen bridge smoke: drawing two GLES2 frames through the shared-RAM Screen window surface' >/dev/ser1\n"
            "    GRAPHICS_ROOT=/dev/shmem LD_LIBRARY_PATH=/dev/shmem:/opt/hmi/ID5/lib:/opt/hmi/lib:/opt/hmi/otf:/boot/lib:/lib:/usr/lib:/opt/sys/lib:/opt/car/lib:.:/lib/graphics/omap5430 LD_PRELOAD=libEGL_X.gpp.so:libGLESv2_X_FORWARD.gpp.so /proc/boot/angle-screen-window-smoke >/dev/ser1 2>&1\n"
            "    screen_smoke_status=$?\n"
            "    echo \"ANGLE Screen bridge smoke exited with status $screen_smoke_status\" >/dev/ser1\n"
            if angle_screen_bridge else ""
        )
        +
        "else\n"
        "  echo 'ANGLE EGL provider smoke: CDC device 0xa4a1 did not appear' >/dev/ser1\n"
        "fi\n"
        ") &\n"
        if angle_egl_rpc_smoke else ""
    )
    tar_flags = "-xvpf" if storage_diagnostics else "-xpf"
    finish_script = (
        extraction_diagnostics
        + "while [ ! -e /fs/sda0/.boot ]; do /boot/bin/sleep 1; done\n"
        "/boot/bin/mount -uw /fs/sda0 || exit 1\n"
        "echo 'QNX root volume before extraction:'\n/boot/bin/df -k /fs/sda0\n"
        f"/boot/bin/bsdtar {tar_flags} /proc/boot/rootfs.tar.gz -C /fs/sda0\n"
        "tar_status=$?\n"
        "echo 'QNX root volume after extraction:'\n/boot/bin/df -k /fs/sda0\n"
        "if [ $tar_status -ne 0 ]; then\n"
        "  echo 'WARNING: bsdtar reported a delayed archive error; checking required runtime files'\n"
        "fi\n"
        "for required in /fs/sda0/opt/hmi/ID5/bin/HmiMain3D /fs/sda0/lib/libscreen.so.1 /fs/sda0/lib/screen-sw.so /fs/sda0/lib/libswblit.so.1 /fs/sda0/bin/screen; do\n"
        "  if [ ! -f $required ]; then echo \"Missing required runtime file: $required\"; exit 1; fi\n"
        "done\n"
        + ("set +x\n" if storage_diagnostics else "")
        + "echo \"iDrive root tree extraction pass finished (bsdtar status $tar_status)\"\n"
        f"{rootfs_ready_hold_script}"
        f"{shader_parser_probe_start}"
        f"{angle_rpc_smoke_start}"
        f"{angle_egl_rpc_smoke_start}"
        f"{sgx_size_log_probe}"
        f"{software_screen_start}"
        f"{graphics_diagnostics}"
        f"{variant_start}"
        f"{screen_test_start}"
        f"{screen_shared_ram_post_start}"
        f"{native_shared_image_start}"
        f"{screen_hmi_contract_start}"
        f"{screen_ui_start}"
        f"{egl_diagnostic_start}"
        f"{hmi_force_start}"
        f"{starter_invocation}"
    ).encode("ascii")
    payloads.append(("proc/boot/finish-root.sh", finish_script, False))
    starter_marker = b"/opt/sys/bin/starter\0starter\0"
    starter_offset = script.find(b"starting starter...")
    if starter_offset < 0 or script.find(starter_marker, starter_offset) < 0:
        raise RuntimeError("could not locate the starter process in .script")
    patch_process(
        script,
        b"starting starter...",
        starter_marker,
        b". /proc/boot/finish-root.sh",
        preserve_argc=True,
    )
    imagefs[script_offset : script_offset + script_size] = script

    # The storage setup needs to write and format hundreds of MiB. BMW's
    # sysinit starts concurrently with that boot process, so wait for the
    # loopback device node before invoking the original sysinit arguments.
    sysinit_label = b"starting sysinit..."
    sysinit_marker = b"sysinit\0sysinit\0"
    sysinit_label_offset = script.find(sysinit_label)
    sysinit_first = script.find(sysinit_marker, sysinit_label_offset + len(sysinit_label))
    sysinit_environment = script.find(b"PATH=/boot/bin:", sysinit_first)
    if min(sysinit_label_offset, sysinit_first, sysinit_environment) < 0:
        raise RuntimeError("could not locate sysinit arguments in .script")
    sysinit_args = script[sysinit_first:sysinit_environment].split(b"\0")[2:-1]
    sysinit_command = b"exec /boot/bin/sysinit" + b"".join(
        b" " + argument for argument in sysinit_args
    )
    wait_script = (
        ("exec >/dev/ser1 2>&1\necho 'Waiting for QNX loopback volume'\n"
         "echo /dev/*\n/boot/bin/pidin info\n/boot/bin/pidin ar\n" if storage_diagnostics else "")
        + "while [ ! -e /dev/lo0 ]; do\n"
        + ("/boot/bin/pidin info\n/boot/bin/sleep 5\n" if storage_diagnostics else "/boot/bin/sleep 1\n")
        + "done\n"
        + sysinit_command.decode("ascii")
        + "\n"
    ).encode("ascii")
    payloads.append(("proc/boot/wait-for-loopback.sh", wait_script, False))
    patch_process(
        script,
        sysinit_label,
        sysinit_marker,
        b". /proc/boot/wait-for-loopback.sh",
        preserve_argc=True,
    )
    imagefs[script_offset : script_offset + script_size] = script

    # Append new IFS payloads and corresponding flat path records.
    prefix = bytearray(imagefs[:-4])
    data_entries: list[bytes] = []
    next_inode = max((inode & 0x1FFFFFFF for inode in inodes), default=0) + 1
    for name, payload, executable in payloads:
        prefix.extend(bytes((-len(prefix)) & 15))
        offset = len(prefix)
        prefix.extend(payload)
        inode = next_inode
        next_inode += 1
        if name.startswith("boot/bin/") and executable:
            inode |= 0x80000000
            mode = 0o101555
        elif name.startswith("boot/lib/"):
            inode |= 0xC0000000
            mode = 0o100555
        elif executable:
            mode = 0o100555
        else:
            mode = 0o100444
        data_entries.append(make_dirent(name, offset, len(payload), inode, mode))
    new_directory_end = directory_end + sum(map(len, data_entries))
    minimum_file_offset = min(
        value[1] for value in entries.values() if value[2] > 0
    )
    if new_directory_end + 4 > minimum_file_offset:
        raise RuntimeError("not enough room in the existing IFS directory table for new files")
    imagefs[directory_end : directory_end + sum(map(len, data_entries))] = b"".join(data_entries)
    struct.pack_into("<I", imagefs, 12, new_directory_end + 4)
    prefix[directory_end : directory_end + sum(map(len, data_entries))] = b"".join(data_entries)
    struct.pack_into("<I", prefix, 12, new_directory_end + 4)
    prefix.extend(bytes((-len(prefix)) & 3))
    prefix.extend(bytes(4))
    new_imagefs = prefix
    new_imagefs_size = len(new_imagefs)
    struct.pack_into("<I", new_imagefs, 8, new_imagefs_size)
    checksum = sum(
        struct.unpack_from("<I", new_imagefs, offset)[0]
        for offset in range(0, new_imagefs_size - 4, 4)
    )
    struct.pack_into("<I", new_imagefs, new_imagefs_size - 4, -checksum & 0xFFFFFFFF)

    image = image[:imagefs_start] + new_imagefs + image[imagefs_end:]
    new_total_size = startup_size + new_imagefs_size
    struct.pack_into("<I", image, header_offset + 0x1C, new_total_size)
    struct.pack_into("<I", image, header_offset + 0x24, new_total_size)
    struct.pack_into("<I", image, header_offset + 0x2C, new_imagefs_size)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image)
    output.chmod(0o600)
    print(
        f"Embedded {len(archive):,}-byte root archive; QNX6 RAM volume: "
        f"{archive_blocks:,} x 4096-byte blocks, {archive_inodes:,} inodes; "
        f"prepared IFS: {len(image):,} bytes"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_ifs", type=Path)
    parser.add_argument("rootfs_archive", type=Path)
    parser.add_argument("mkqnx6fs", type=Path)
    parser.add_argument("dd", type=Path)
    parser.add_argument("devb_loopback", type=Path)
    parser.add_argument("bsdtar", type=Path)
    parser.add_argument("mount", type=Path)
    parser.add_argument("libbz2", type=Path)
    parser.add_argument("libz", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        embed(
            args.prepared_ifs,
            args.rootfs_archive,
            args.mkqnx6fs,
            args.dd,
            args.devb_loopback,
            args.bsdtar,
            args.mount,
            args.libbz2,
            args.libz,
            args.output,
        )
    except (OSError, RuntimeError, struct.error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
