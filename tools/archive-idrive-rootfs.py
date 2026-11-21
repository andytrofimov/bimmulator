#!/usr/bin/env python3
"""Create a reproducible PAX archive for QNX, optionally gzip-compressed."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
from pathlib import Path
import struct
import sys
import tarfile
import xml.etree.ElementTree as ET


ARCHIVE_CACHE_SCHEMA = b"idrive-rootfs-archive-v11\0"

HMI_CODING_PATH = "opt/hmi/ID5/lib/libhmicoding.so"
HMI_CODING_SHA256 = "d1b52567a853d944a2a2ad0a50361c9ab82a0825889d9deed3b9af7739774a4d"
HMI_VARIANTREGISTRY_PATH = "opt/hmi/ID5/data/ro/common/widget/variantregistry.pbvar"
HMI_VARIANTREGISTRY_SHA256 = "e21044c65cfeda08eda0bc42a2ee6a8ea35e3faaa31f721abe8a37a5916517a3"
HMI_CODING_DEFAULTS_INDEX_OFFSET = 0xDB548
HMI_CAMERA_RVC_PAGE_KEY = 5
HMI_CAMERA_RVC_PAGE_DATA_OFFSET = 0xDAFAC
HMI_CAMERA_RVC_PATCH = (0xDAFE9, b"\x00", b"\x02")
HMI_VARIANTREGISTRY_F32_ASSET_PATHS = (
    (b"vehicles/G11/vehicle_G11", b"vehicles/F32/vehicle_F32"),
    (b"vehicles/G11/camera_crane", b"vehicles/F32/camera_crane"),
)
HMI_VARIANTREGISTRY_INDEX_PATH = (
    "opt/hmi/ID5/data/ro/bmw/id6l/widgetasset/resources.ptr"
)
HMI_ID6L_PATCHES = (
    # CHmiCodingService::openBinaryStream: force creation of CDsiBinaryStream
    # when the QNX sysetpage attachment is absent. That stream can then use
    # nbtSysetDefaults_getBuffer, which ships with this same BMW library.
    (0x6512C, bytes.fromhex("16 00 00 0a"), bytes.fromhex("00 00 a0 e1")),
    # SysetPageGetSh_getBuffer: report "use BMW defaults" to the stream path.
    (0x68C78, bytes.fromhex("f0 45 2d e9 e0 40 9f e5"),
     bytes.fromhex("01 00 a0 e3 1e ff 2f e1")),
    # Built-in defaults index entry 7 is page 0x3000, 0x96 bytes at 0xdb2c0.
    # Ghidra's coding descriptor maps feature 0x0ca8 to
    # HMI_ID_VERSION_id6_light (byte 0x1d, mask 0x1c, value 3). The adjacent
    # feature 0x0ca9 is full ID6 (value 4), which maps to variant 0x5384; this
    # HmiMain3D menu selector only handles 0x5381/0x5382/0x5383. Thus 0x0c
    # selects the supported ID6 Light menu, while 0x10 selects full ID6.
    (0xDB2DD, b"\x00", b"\x0c"),
    # Built-in defaults index entry 12 is page 0x3004, 0x32 bytes at 0xda2b4.
    # Ghidra feature 0x0552 selects BAUREIHE_F32 (byte 4 == 0x42); feature
    # 0x0a53 selects productline 35up (low nibble at byte 16 == 8).
    (0xDA2B8, b"\x00", b"\x42"),
    (0xDA2C4, b"\x11", b"\x18"),
    # Built-in defaults index entry 8 is page 0x3007, 0x32 bytes at 0xda500.
    # Feature 0x0796 selects LANGUAGE_ENGLISH_US_master with mask 0x30 and
    # expected value 1 in byte 0, preserving the unrelated low bits.
    (0xDA500, b"\x04", b"\x14"),
    # Built-in defaults index entry 9 is page 0x3006, 0x64 bytes at 0xdaedc.
    # Feature 0x0a5c selects DISPLAY_SIZE_RESOLUTION_10_25_1440x540;
    # bits 2..5 of byte 0x1d currently encode value 2 (0x08), and 0x0c is 3.
    (0xDAEF9, b"\x08", b"\x0c"),
)
HMI_DEVELOPER_MENU_PATCH = (0xDAEF8, b"\x00", b"\x40")
# Built-in defaults index entry 7 is page 0x3000, 0x96 bytes at 0xdb2c0.
# The coding descriptor for feature 0x019a (va_REMOTE_HMI, the active value;
# 0x019b is _nicht_aktiv) is byte 0x6b, mask 0x70, value 1. The shipped
# default byte is zero, which leaves REMOTE_HMI, A4A (mask 0x80 in the same
# byte) and A4A_REMOTE_APPS (byte 0x6c bit 0) all inactive, so the derived
# feature 0x9c56 is false and RemotingBundle skips its start.
HMI_REMOTE_HMI_PATCH = (0xDB32B, b"\x00", b"\x10")
# CDsiBinaryStream maps page 0x3005 to default key 3. Feature 0x638
# (CID_DISPLAY_RES_1440_540) uses mask 0x07, value 3 at byte 0x45.
HMI_CID_1440_PATCH = (0xDB4B1, b"\x09", b"\x0b")
# BMW variant 0x51a5 requires both CID_TOUCH and CID_HMI_TOUCH.
HMI_CID_TOUCH_PATCHES = (
    (0xDB4B0, b"\xa4", b"\xa5"),  # page 0x3005, byte 0x44, bit 0
    (0xDA2F5, b"\x00", b"\x01"),  # page 0x300b, byte 0x05, bit 0
)
HMI_MAIN_PATH = "opt/hmi/ID5/bin/HmiMain3D"
HMI_MAIN_SHA256 = "418906bf10aeebcee6a02b8687b63a6c6e530a9263dc7171892c568e4d86845e"
HMI_BENCH_INPUT_PATCHES = (
    # 0x21cdf8: Enable the home input subscription during the bench boot.
    (0x11CDF8, bytes.fromhex("01 10 a0 13"), bytes.fromhex("01 10 a0 e3")),
    # 0x33586c: Seed the home touch handler with the emulated display on.
    # The handler still subscribes to subsequent native display notifications.
    (0x23586C, bytes.fromhex("33 ff 2f e1"), bytes.fromhex("01 00 a0 e3")),
)


HMI_RESOURCE_LIBRARY_PATH = "opt/hmi/ID5/lib/libhmidb.so"
HMI_RESOURCE_LIBRARY_SHA256 = "1037e4aa98bb5c63790a1000fb5c163bdae99fbe996db94b29053626b512da67"
HMI_RESOURCE_EN_US_PATCHES = (
    # CHmiResourceManager C1 and C2 initialize the language before providers
    # attach. The native database loader uses that byte as its map index.
    (0x84BAC, bytes.fromhex("00 00 e0 e3"), bytes.fromhex("02 00 a0 e3")),
    (0x84EF8, bytes.fromhex("00 00 e0 e3"), bytes.fromhex("02 00 a0 e3")),
)


def _hmi_binary_overlay(source: Path, sha256: str, patches: tuple[tuple[int, bytes, bytes], ...]) -> bytearray:
    data = bytearray(source.read_bytes())
    if hashlib.sha256(data).hexdigest() != sha256:
        raise RuntimeError(f"HMI overlay expects {source} SHA-256 {sha256}")
    for offset, expected, replacement in patches:
        end = offset + len(expected)
        if data[offset:end] != expected:
            raise RuntimeError(f"HMI overlay found an unexpected instruction in {source} at {offset:#x}")
        data[offset:end] = replacement
    return data


def _hmi_coding_id6l_overlay(
    root: Path, *, cid_1440: bool = False, cid_touch: bool = False
) -> bytes:
    """Return the exact-firmware, emulator-only ID6 Light coding overlay."""
    source = root / HMI_CODING_PATH
    data = source.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != HMI_CODING_SHA256:
        raise RuntimeError(
            f"ID6 Light coding overlay expects {HMI_CODING_PATH} SHA-256 "
            f"{HMI_CODING_SHA256}, got {actual_sha256}"
        )

    # Verify the exact BMW default pages used below. Keys start at one while
    # the table is zero-indexed.
    expected_pages = {
        7: (0x96, 0xDB2C0),  # HMI_ID_VERSION
        8: (0x32, 0xDA500),  # master language
        9: (0x64, 0xDAEDC),  # display size / resolution
        12: (0x32, 0xDA2B4),  # productline and BAUREIHE
    }
    if cid_1440 or cid_touch:
        expected_pages[3] = (0x96, 0xDB46C)  # CID_DISPLAY_RES
    if cid_touch:
        expected_pages[15] = (0x1E, 0xDA2F0)  # CID_HMI_TOUCH
    for key, expected in expected_pages.items():
        table_entry = 0xDB548 + (key - 1) * 12
        actual_key, packed_size, data_offset = struct.unpack_from(
            "<III", data, table_entry
        )
        if (actual_key, packed_size & 0xFFFF, data_offset) != (
            key,
            expected[0],
            expected[1],
        ):
            raise RuntimeError(
                f"ID6 Light coding overlay found an unexpected BMW default page index for key {key}"
            )

    patched = bytearray(data)
    patches = HMI_ID6L_PATCHES + ((HMI_CID_1440_PATCH,) if cid_1440 else ())
    if cid_touch:
        patches += HMI_CID_TOUCH_PATCHES
    for offset, expected, replacement in patches:
        if patched[offset : offset + len(expected)] != expected:
            raise RuntimeError(
                f"ID6 Light coding overlay found unexpected bytes at 0x{offset:x}"
            )
        patched[offset : offset + len(expected)] = replacement
    return bytes(patched)


def _hmi_coding_developer_menu_overlay(data: bytes) -> bytes:
    """Enable the HMI's development-only inspector gate in a staged copy."""
    page_index = 0xDB548 + (9 - 1) * 12
    key, packed_size, data_offset = struct.unpack_from("<III", data, page_index)
    if (key, packed_size & 0xFFFF, data_offset) != (9, 0x64, 0xDAEDC):
        raise RuntimeError(
            "developer-menu coding overlay found an unexpected BMW default page index"
        )

    offset, expected, replacement = HMI_DEVELOPER_MENU_PATCH
    if data[offset : offset + len(expected)] != expected:
        raise RuntimeError(
            f"developer-menu coding overlay found unexpected bytes at 0x{offset:x}"
        )
    patched = bytearray(data)
    # Feature 0x0709 (va_ENTWICKLER_MENUE) uses mask 0x40, value 1, at
    # page 0x3006 byte 0x1c. The expected source byte is zero, so this sets
    # only that feature bit and preserves all other coding bits.
    patched[offset : offset + len(expected)] = replacement
    return bytes(patched)


def _hmi_coding_remote_hmi_overlay(data: bytes) -> bytes:
    """Code REMOTE_HMI active so the HMI starts RemotingBundle and plugin apps."""
    page_index = 0xDB548 + (7 - 1) * 12
    key, packed_size, data_offset = struct.unpack_from("<III", data, page_index)
    if (key, packed_size & 0xFFFF, data_offset) != (7, 0x96, 0xDB2C0):
        raise RuntimeError(
            "remote-HMI coding overlay found an unexpected BMW default page index"
        )

    offset, expected, replacement = HMI_REMOTE_HMI_PATCH
    if data[offset : offset + len(expected)] != expected:
        raise RuntimeError(
            f"remote-HMI coding overlay found unexpected bytes at 0x{offset:x}"
        )
    patched = bytearray(data)
    # Feature 0x019a (va_REMOTE_HMI) uses mask 0x70, value 1, at page 0x3000
    # byte 0x6b. The expected source byte is zero, so this sets only that
    # field and leaves A4A (mask 0x80) inactive.
    patched[offset : offset + len(expected)] = replacement
    return bytes(patched)


def _hmi_coding_camera_rvc_overlay(root: Path, data: bytes) -> bytes:
    """Select the shipped F32 reversing-camera coding in an emulator-only copy."""
    source = root / HMI_CODING_PATH
    source_data = source.read_bytes()
    actual_sha256 = hashlib.sha256(source_data).hexdigest()
    if actual_sha256 != HMI_CODING_SHA256:
        raise RuntimeError(
            "F32 camera coding overlay expects "
            f"{HMI_CODING_PATH} SHA-256 {HMI_CODING_SHA256}, got {actual_sha256}"
        )

    # CDsiBinaryStream::readCodingBlock maps page 0x3001 to defaults key 5;
    # the exact library also maps CAMERA_SYSTEM=icam_rvc (feature 0x2d3) to
    # byte 0x3d, low nibble 2. Pin the index entry and pristine byte so the
    # emulator-only change cannot drift onto another firmware layout.
    table_entry = HMI_CODING_DEFAULTS_INDEX_OFFSET + (HMI_CAMERA_RVC_PAGE_KEY - 1) * 12
    key, packed_size, data_offset = struct.unpack_from("<III", source_data, table_entry)
    if (key, packed_size & 0xFFFF, data_offset) != (
        HMI_CAMERA_RVC_PAGE_KEY,
        0x96,
        HMI_CAMERA_RVC_PAGE_DATA_OFFSET,
    ):
        raise RuntimeError("F32 camera coding overlay found an unexpected page 0x3001 defaults entry")

    offset, expected, replacement = HMI_CAMERA_RVC_PATCH
    if data[offset : offset + len(expected)] != expected:
        raise RuntimeError(
            f"F32 camera coding overlay found unexpected bytes at 0x{offset:x}"
        )
    patched = bytearray(data)
    patched[offset : offset + len(expected)] = replacement
    return bytes(patched)


def _hmi_variantregistry_f32_overlay(root: Path) -> bytes:
    """Select the shipped F32 3D assets in an emulator-only PBVAR copy."""
    source = root / HMI_VARIANTREGISTRY_PATH
    data = source.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != HMI_VARIANTREGISTRY_SHA256:
        raise RuntimeError(
            "F32 VariantRegistry overlay expects "
            f"{HMI_VARIANTREGISTRY_PATH} SHA-256 "
            f"{HMI_VARIANTREGISTRY_SHA256}, got {actual_sha256}"
        )

    index_path = root / HMI_VARIANTREGISTRY_INDEX_PATH
    index_data = index_path.read_bytes()
    patched = data
    for expected, replacement in HMI_VARIANTREGISTRY_F32_ASSET_PATHS:
        if len(expected) != len(replacement):
            raise RuntimeError("F32 VariantRegistry paths must preserve protobuf lengths")
        occurrences = patched.count(expected)
        if occurrences != 2:
            raise RuntimeError(
                f"F32 VariantRegistry overlay expected two occurrences of "
                f"{expected.decode('ascii')}, found {occurrences}"
            )
        alias = b'alias: "' + replacement + b'"'
        resource_file = (
            b'file: "bmw/widgetasset/' + replacement + b'/widget.pbw"'
        )
        if alias not in index_data or resource_file not in index_data:
            raise RuntimeError(
                f"F32 resource index does not register {replacement.decode('ascii')}"
            )
        asset_file = (
            root
            / "opt/hmi/ID5/data/ro/bmw/widgetasset"
            / replacement.decode("ascii")
            / "widget.pbw"
        )
        if not asset_file.is_file():
            raise RuntimeError(f"F32 indexed widget asset is missing: {asset_file}")
        patched = patched.replace(expected, replacement)

    if any(expected in patched for expected, _ in HMI_VARIANTREGISTRY_F32_ASSET_PATHS):
        raise RuntimeError("F32 VariantRegistry overlay left a G11 asset path behind")
    return patched


HEADLESS_STOP_PACKAGES = {"NET", "PACKET_FILTER", "TILER", "SCREEN"}
GRAPHICS_STOP_PACKAGES = {"PACKET_FILTER"}
GRAPHICS_RUN_PACKAGES = {"HMI", "HMI_BMW_OTF_AGENT", "TRACE", "USB"}


def _profile_starter_config(
    config: Path,
    stop_packages: set[str],
    *,
    software_screen_variant: bool = False,
    hmi_without_comms: bool = False,
    suppress_hmi: bool = False,
    defer_otf_agent: bool = False,
    most_sipc_stack: bool = False,
    run_packages: set[str] | None = None,
) -> bytes:
    root = ET.fromstring(config.read_bytes())
    if most_sipc_stack:
        table = root.find("EnvironmentTable")
        count = root.find("EnvironmentCount")
        clients = [process for process in root.iter("Process")
                   if process.findtext("Name") == "/opt/sys/bin/most"
                   and "--devmode=client" in (process.findtext("Args") or "")]
        if table is None or count is None or not clients:
            raise RuntimeError("starter.cfg lacks the environment table or native MOST client")
        number = str(max(int(env.findtext("Number")) for env in table.findall("Environment")) + 1)
        environment = ET.SubElement(table, "Environment")
        for tag, value in (("Number", number), ("Name", "IDRIVE_MOST_SIPC_STACK"),
                           ("EnvName", "SOCK"), ("Value", "/idrive"), ("Overwrite", "1")):
            ET.SubElement(environment, tag).text = value
        count.text = str(len(table.findall("Environment")))
        for process in clients:
            high_mem = process.find("HighMem")
            index = list(process).index(high_mem) if high_mem is not None else len(process)
            entry = ET.Element("RequiresEnvironment")
            entry.text = number
            process.insert(index, entry)
    found = set()
    for package in root.iter("Package"):
        name = package.findtext("Name")
        if name in stop_packages:
            state = package.find("RequestState")
            if state is None:
                raise RuntimeError(f"starter package {name} has no RequestState")
            state.text = "STOP"
            found.add(name)
    missing = stop_packages - found
    if missing:
        raise RuntimeError(
            "starter.cfg is missing expected packages: " + ", ".join(sorted(missing))
        )
    requested_run = run_packages or set()
    found_run = set()
    for package in root.iter("Package"):
        name = package.findtext("Name")
        if name in requested_run:
            state = package.find("RequestState")
            if state is None:
                raise RuntimeError(f"starter package {name} has no RequestState")
            state.text = "RUN"
            found_run.add(name)
    missing_run = requested_run - found_run
    if missing_run:
        raise RuntimeError(
            "starter.cfg is missing expected packages: " + ", ".join(sorted(missing_run))
        )
    if defer_otf_agent:
        otf_packages = [
            package for package in root.iter("Package")
            if package.findtext("Name") == "HMI_BMW_OTF_AGENT"
        ]
        if len(otf_packages) != 1:
            raise RuntimeError(
                "starter.cfg must contain exactly one HMI_BMW_OTF_AGENT package"
            )
        state = otf_packages[0].find("RequestState")
        if state is None:
            raise RuntimeError("starter.cfg HMI_BMW_OTF_AGENT package has no RequestState")
        state.text = "STOP"
    if run_packages and "HMI" in run_packages:
        hmi_library_environment = next(
            (
                environment
                for environment in root.iter("Environment")
                if environment.findtext("Number") == "4"
            ),
            None,
        )
        if hmi_library_environment is None:
            raise RuntimeError("starter.cfg has no HMI library-path environment 4")
        value = hmi_library_environment.find("Value")
        if value is None:
            raise RuntimeError("starter.cfg HMI library-path environment 4 has no Value")
        value.text = (value.text or "").replace(
            "/opt/hmi/lib", "/opt/hmi/ID5/lib:/opt/hmi/lib", 1
        )
    if hmi_without_comms:
        hmi_processes = [
            process
            for process in root.iter("Process")
            if process.findtext("Number") == "17"
        ]
        if len(hmi_processes) != 1:
            raise RuntimeError("starter.cfg must contain exactly one HmiMain3D process 17")
        for tag in ("Args", "ResArgs"):
            element = hmi_processes[0].find(tag)
            if element is None or "-c=DSI,MOSTSubSystem" not in (element.text or ""):
                raise RuntimeError(f"HmiMain3D process 17 has no DSI/MOST option in {tag}")
            element.text = element.text.replace("-c=DSI,MOSTSubSystem ", "", 1)
    if suppress_hmi:
        hmi_packages = [
            package for package in root.iter("Package")
            if package.findtext("Name") == "HMI"
        ]
        if len(hmi_packages) != 1:
            raise RuntimeError("starter.cfg must contain exactly one HMI package")
        state = hmi_packages[0].find("RequestState")
        if state is None:
            raise RuntimeError("starter.cfg HMI package has no RequestState")
        state.text = "STOP"
    if software_screen_variant:
        for environment in root.iter("Environment"):
            if environment.findtext("EnvName") == "GRAPHICS_ROOT":
                value = environment.find("Value")
                if value is None:
                    raise RuntimeError("GRAPHICS_ROOT environment has no Value")
                value.text = "/dev/shmem"

        screen_processes = [
            process
            for process in root.iter("Process")
            if process.findtext("Number") == "120"
        ]
        if len(screen_processes) != 1:
            raise RuntimeError("starter.cfg must contain exactly one Screen process 120")
        for tag, value in (("Name", "/bin/sleep"), ("Args", "86400"), ("ResArgs", "86400")):
            element = screen_processes[0].find(tag)
            if element is None:
                raise RuntimeError(f"Screen process 120 has no {tag} element")
            element.text = value

        layer_processes = [
            process
            for process in root.iter("Process")
            if process.findtext("Number") == "121"
        ]
        if len(layer_processes) != 1:
            raise RuntimeError(
                "starter.cfg must contain exactly one LayerManagerService process 121"
            )
        for tag, value in (("Args", "-w1440 -h540 -d:1"), ("ResArgs", "-w1440 -h540 -d:1")):
            element = layer_processes[0].find(tag)
            if element is None:
                raise RuntimeError(f"LayerManagerService process 121 has no {tag} element")
            element.text = value
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def archive_rootfs(
    root: Path,
    output: Path,
    *,
    compressed: bool,
    emulator_profile: str = "vehicle",
    software_screen_variant: bool = False,
    hmi_without_comms: bool = False,
    suppress_hmi: bool = False,
    defer_otf_agent: bool = False,
    most_sipc_stack: bool = False,
    hmi_coding_id6l: bool = False,
    hmi_coding_cid_1440: bool = False,
    hmi_coding_cid_touch: bool = False,
    hmi_bench_input: bool = False,
    hmi_resource_en_us: bool = False,
    hmi_coding_developer_menu: bool = False,
    hmi_coding_remote_hmi: bool = False,
    hmi_coding_camera_rvc: bool = False,
    hmi_variantregistry_f32: bool = False,
    cache_unchanged: bool = False,
) -> int:
    root = root.resolve()
    output = output.resolve()
    if not root.is_dir():
        raise RuntimeError(f"root filesystem tree is not a directory: {root}")
    if root == output or root in output.parents:
        raise RuntimeError("archive output must be outside the root filesystem tree")
    if hmi_coding_cid_1440 and not hmi_coding_id6l:
        raise RuntimeError("CID resolution coding requires the ID6 Light coding overlay")
    if hmi_coding_cid_touch and not hmi_coding_id6l:
        raise RuntimeError("CID touch coding requires the ID6 Light coding overlay")
    if hmi_bench_input and not hmi_coding_cid_touch:
        raise RuntimeError("bench input requires CID touch coding")
    if hmi_resource_en_us and not hmi_coding_id6l:
        raise RuntimeError("initial English resources require the ID6 Light coding overlay")
    fingerprint = hashlib.sha256() if cache_unchanged else None
    if fingerprint is not None:
        fingerprint.update(ARCHIVE_CACHE_SCHEMA)
        fingerprint.update(emulator_profile.encode("ascii") + b"\0")
        fingerprint.update(b"1" if software_screen_variant else b"0")
        fingerprint.update(b"1" if hmi_without_comms else b"0")
        fingerprint.update(b"1" if suppress_hmi else b"0")
        fingerprint.update(b"1" if defer_otf_agent else b"0")
        if most_sipc_stack:
            fingerprint.update(b"most-sipc-private-stack\0")
        fingerprint.update(b"1" if hmi_coding_id6l else b"0")
        if hmi_coding_id6l:
            fingerprint.update(b"hmi-id6-light-overlay\0")
            for offset, expected, replacement in HMI_ID6L_PATCHES:
                fingerprint.update(offset.to_bytes(4, "little"))
                fingerprint.update(len(expected).to_bytes(4, "little"))
                fingerprint.update(expected)
                fingerprint.update(replacement)
        if hmi_coding_cid_1440:
            offset, expected, replacement = HMI_CID_1440_PATCH
            fingerprint.update(b"hmi-cid-1440-overlay\0")
            fingerprint.update(offset.to_bytes(4, "little") + expected + replacement)
        if hmi_coding_cid_touch:
            fingerprint.update(b"hmi-cid-touch-overlay\0")
            for offset, expected, replacement in HMI_CID_TOUCH_PATCHES:
                fingerprint.update(offset.to_bytes(4, "little") + expected + replacement)
        if hmi_bench_input:
            fingerprint.update(b"hmi-bench-input-overlay\0" + HMI_MAIN_SHA256.encode("ascii"))
            for offset, expected, replacement in HMI_BENCH_INPUT_PATCHES:
                fingerprint.update(offset.to_bytes(4, "little") + expected + replacement)
        if hmi_resource_en_us:
            fingerprint.update(b"hmi-resource-en-us-overlay\0" + HMI_RESOURCE_LIBRARY_SHA256.encode("ascii"))
            for offset, expected, replacement in HMI_RESOURCE_EN_US_PATCHES:
                fingerprint.update(offset.to_bytes(4, "little") + expected + replacement)
        if hmi_coding_developer_menu:
            fingerprint.update(b"hmi-developer-menu-overlay\0")
            offset, expected, replacement = HMI_DEVELOPER_MENU_PATCH
            fingerprint.update(offset.to_bytes(4, "little"))
            fingerprint.update(len(expected).to_bytes(4, "little"))
            fingerprint.update(expected)
            fingerprint.update(replacement)
        if hmi_coding_remote_hmi:
            fingerprint.update(b"hmi-remote-hmi-overlay\0")
            offset, expected, replacement = HMI_REMOTE_HMI_PATCH
            fingerprint.update(offset.to_bytes(4, "little"))
            fingerprint.update(len(expected).to_bytes(4, "little"))
            fingerprint.update(expected)
            fingerprint.update(replacement)
        fingerprint.update(b"1" if hmi_coding_camera_rvc else b"0")
        if hmi_coding_camera_rvc:
            fingerprint.update(b"hmi-camera-rvc-overlay\0")
            fingerprint.update(HMI_CODING_SHA256.encode("ascii") + b"\0")
            fingerprint.update(HMI_CAMERA_RVC_PAGE_KEY.to_bytes(4, "little"))
            fingerprint.update(HMI_CAMERA_RVC_PAGE_DATA_OFFSET.to_bytes(4, "little"))
            offset, expected, replacement = HMI_CAMERA_RVC_PATCH
            fingerprint.update(offset.to_bytes(4, "little"))
            fingerprint.update(len(expected).to_bytes(4, "little"))
            fingerprint.update(expected)
            fingerprint.update(replacement)
        fingerprint.update(b"1" if hmi_variantregistry_f32 else b"0")
        if hmi_variantregistry_f32:
            fingerprint.update(b"hmi-variantregistry-f32-overlay\0")
            fingerprint.update(HMI_VARIANTREGISTRY_SHA256.encode("ascii") + b"\0")
            for expected, replacement in HMI_VARIANTREGISTRY_F32_ASSET_PATHS:
                fingerprint.update(len(expected).to_bytes(4, "little"))
                fingerprint.update(expected)
                fingerprint.update(replacement)
        fingerprint.update(b"1" if compressed else b"0")
    for item in sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()):
        relative = item.relative_to(root).as_posix()
        info = item.lstat()
        if fingerprint is not None:
            fingerprint.update(relative.encode("utf-8", "surrogateescape") + b"\0")
            fingerprint.update(info.st_mode.to_bytes(4, "little", signed=False))
        if item.is_symlink():
            if fingerprint is not None:
                fingerprint.update(b"L" + os.readlink(item).encode("utf-8", "surrogateescape"))
        elif item.is_file():
            with item.open("rb") as source:
                if fingerprint is not None:
                    fingerprint.update(b"F")
                    while block := source.read(1024 * 1024):
                        fingerprint.update(block)
        elif item.is_dir():
            if fingerprint is not None:
                fingerprint.update(b"D")
        else:
            if fingerprint is not None:
                fingerprint.update(b"O")

    cache_key = fingerprint.hexdigest() if fingerprint is not None else None
    sidecar = output.with_name(output.name + ".sha256")
    if cache_key and output.is_file() and sidecar.is_file():
        if sidecar.read_text(encoding="ascii").strip() == cache_key:
            print(f"Root archive cache hit ({emulator_profile}): {output}")
            return output.stat().st_size

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = (
        output.with_name(f"{output.name}.tmp-{os.getpid()}")
        if cache_unchanged
        else output
    )

    profile_config = None
    qemu_cdc_configs: dict[str, bytes] = {}
    otf_socket_config = None
    otf_socket_config_data = None
    qemu_usb_script = None
    qemu_usb_script_data = None
    hmi_coding_library = None
    hmi_coding_library_data = None
    hmi_binary_overlays = {}
    if hmi_bench_input:
        hmi_binary_overlays[HMI_MAIN_PATH] = _hmi_binary_overlay(
            root / HMI_MAIN_PATH, HMI_MAIN_SHA256, HMI_BENCH_INPUT_PATCHES
        )
    if hmi_resource_en_us:
        hmi_binary_overlays[HMI_RESOURCE_LIBRARY_PATH] = _hmi_binary_overlay(
            root / HMI_RESOURCE_LIBRARY_PATH, HMI_RESOURCE_LIBRARY_SHA256, HMI_RESOURCE_EN_US_PATCHES
        )
        print(f"Initializing native English resources in {HMI_RESOURCE_LIBRARY_PATH}")
    hmi_variantregistry = None
    hmi_variantregistry_data = None
    if hmi_coding_remote_hmi and not hmi_coding_id6l:
        # Only the ID6 Light overlay makes the HMI read BMW's built-in coding
        # defaults, which is where the remote-HMI byte lives.
        raise RuntimeError(
            "remote-HMI coding requires the emulator-only ID6 Light coding profile"
        )
    if hmi_coding_id6l or hmi_coding_developer_menu or hmi_coding_camera_rvc:
        if emulator_profile != "omap5-graphics":
            raise RuntimeError(
                "HMI coding overlays require --emulator-profile omap5-graphics"
            )
        hmi_coding_library = root / HMI_CODING_PATH
        if hmi_coding_id6l:
            hmi_coding_library_data = _hmi_coding_id6l_overlay(
                root, cid_1440=hmi_coding_cid_1440, cid_touch=hmi_coding_cid_touch
            )
            print(
                "Applying emulator-only ID6 Light coding defaults to "
                f"{HMI_CODING_PATH} (source SHA-256 {HMI_CODING_SHA256})"
            )
        else:
            hmi_coding_library_data = hmi_coding_library.read_bytes()
            actual_sha256 = hashlib.sha256(hmi_coding_library_data).hexdigest()
            if actual_sha256 != HMI_CODING_SHA256:
                raise RuntimeError(
                    "developer-menu coding overlay expects "
                    f"{HMI_CODING_PATH} SHA-256 {HMI_CODING_SHA256}, "
                    f"got {actual_sha256}"
                )
        if hmi_coding_developer_menu:
            hmi_coding_library_data = _hmi_coding_developer_menu_overlay(
                hmi_coding_library_data
            )
            print(
                "Applying emulator-only HMI developer-menu coding to "
                f"{HMI_CODING_PATH} (source SHA-256 {HMI_CODING_SHA256})"
            )
        if hmi_coding_remote_hmi:
            hmi_coding_library_data = _hmi_coding_remote_hmi_overlay(
                hmi_coding_library_data
            )
            print(
                "Applying emulator-only REMOTE_HMI coding (plugin apps) to "
                f"{HMI_CODING_PATH} (source SHA-256 {HMI_CODING_SHA256})"
            )
        if hmi_coding_camera_rvc:
            if not hmi_coding_id6l or not hmi_variantregistry_f32:
                raise RuntimeError(
                    "F32 rear-camera coding requires the emulator-only ID6 Light and F32 asset profile"
                )
            hmi_coding_library_data = _hmi_coding_camera_rvc_overlay(
                root, hmi_coding_library_data
            )
            print(
                "Applying emulator-only F32 reversing-camera coding "
                f"(CAMERA_SYSTEM=icam_rvc) to {HMI_CODING_PATH}"
            )
    if hmi_variantregistry_f32:
        if emulator_profile != "omap5-graphics" or not hmi_coding_id6l:
            raise RuntimeError(
                "F32 VariantRegistry overlay requires the omap5-graphics profile "
                "and the ID6 Light coding overlay that selects BAUREIHE_F32"
            )
        hmi_variantregistry = root / HMI_VARIANTREGISTRY_PATH
        hmi_variantregistry_data = _hmi_variantregistry_f32_overlay(root)
        print(
            "Applying emulator-only F32 3D vehicle assets to "
            f"{HMI_VARIANTREGISTRY_PATH} (source SHA-256 "
            f"{HMI_VARIANTREGISTRY_SHA256})"
        )
    if emulator_profile in {"vexpress", "omap5", "omap5-graphics"}:
        profile_config = root / "opt/sys/etc/starter.cfg"
        if not profile_config.is_file():
            raise RuntimeError(f"starter config not found: {profile_config}")
        stop_packages = (
            GRAPHICS_STOP_PACKAGES
            if emulator_profile == "omap5-graphics"
            else HEADLESS_STOP_PACKAGES
        )
        profile_config_data = _profile_starter_config(
            profile_config,
            stop_packages,
            software_screen_variant=software_screen_variant,
            hmi_without_comms=hmi_without_comms,
            suppress_hmi=suppress_hmi,
            defer_otf_agent=defer_otf_agent,
            most_sipc_stack=most_sipc_stack,
            run_packages=(
                GRAPHICS_RUN_PACKAGES
                if emulator_profile == "omap5-graphics"
                else set()
            ),
        )
        if defer_otf_agent:
            otf_socket_config = root / "opt/hmi/otf/socket.cfg"
            if not otf_socket_config.is_file():
                raise RuntimeError(f"BMW OTF socket config not found: {otf_socket_config}")
            otf_socket_config_data = otf_socket_config.read_bytes()
            localhost = (
                b"SOCKET;/opt/hmi/otf/libBMWOTFdrvSocket.so.3;127.0.0.1,1000"
            )
            # OTFDRV_open binds and listens on this address inside QNX. Point
            # it at the guest's CDC address so QEMU hostfwd can reach it; the
            # QEMU gateway address belongs to the Mac side of user networking.
            qemu_gateway = (
                b"SOCKET;/opt/hmi/otf/libBMWOTFdrvSocket.so.3;160.48.199.253,1000"
            )
            qemu_guest = (
                b"SOCKET;/opt/hmi/otf/libBMWOTFdrvSocket.so.3;160.48.199.225,1000"
            )
            if localhost in otf_socket_config_data:
                otf_socket_config_data = otf_socket_config_data.replace(
                    localhost, qemu_guest, 1
                )
            elif qemu_gateway in otf_socket_config_data:
                otf_socket_config_data = otf_socket_config_data.replace(
                    qemu_gateway, qemu_guest, 1
                )
            elif qemu_guest not in otf_socket_config_data:
                raise RuntimeError(
                    "BMW OTF socket.cfg has no expected localhost, QEMU gateway, or guest endpoint"
                )
        if emulator_profile in {"omap5", "omap5-graphics"}:
            umass_configs = sorted((root / "etc").glob("umass-enum*.cfg"))
            if not umass_configs:
                raise RuntimeError(f"USB enumeration configs not found: {root / 'etc'}")
            qemu_cdc_entry = (
                b"vendor=0x0525,device=0xa4a1,type=CDC,driver=devnp-ecm.so,"
                b"aps_partname=softrt_CONN,args=,netip=160.48.199.225,"
                b"netmsk=255.255.255.0"
            )
            for umass_config in umass_configs:
                config_data = umass_config.read_bytes()
                if qemu_cdc_entry in config_data:
                    qemu_cdc_configs[umass_config.relative_to(root).as_posix()] = config_data
                    continue
                peiker_entry = b"vendor=0x2239,device=0xf004,type=CDC"
                position = config_data.find(peiker_entry)
                if position < 0:
                    raise RuntimeError(
                        f"USB enumeration config has no CDC section for QEMU's virtual NIC: {umass_config}"
                    )
                line_start = config_data.rfind(b"\n", 0, position) + 1
                newline = b"\r\n" if b"\r\n" in config_data else b"\n"
                qemu_cdc_configs[umass_config.relative_to(root).as_posix()] = (
                    config_data[:line_start]
                    + qemu_cdc_entry
                    + newline
                    + config_data[line_start:]
                )
        if emulator_profile == "omap5-graphics":
            qemu_usb_script = root / "bin/start_usb.sh"
            if not qemu_usb_script.is_file():
                raise RuntimeError(f"USB startup script not found: {qemu_usb_script}")
            qemu_usb_script_data = qemu_usb_script.read_bytes()
            qnx_xhci_driver = (
                b"-d omap5-xhci ioport=0x4a030000,irq=124,verbose=5 "
            )
            if qnx_xhci_driver not in qemu_usb_script_data:
                raise RuntimeError(
                    "USB startup script does not contain the expected OMAP5 xHCI driver"
                )
            # QNX's proprietary OMAP5 xHCI driver crashes while initializing
            # QEMU's generic xHCI model (evtring_create). Keep the OMAP EHCI
            # host and its OHCI companion for QEMU keyboard/mouse input.
            qemu_usb_script_data = qemu_usb_script_data.replace(
                qnx_xhci_driver, b"", 1
            )
    else:
        profile_config_data = None

    def add_tree(archive: tarfile.TarFile) -> None:
        def select(entry: tarfile.TarInfo) -> tarfile.TarInfo | None:
            if profile_config is not None and entry.name == "opt/sys/etc/starter.cfg":
                return None
            if otf_socket_config is not None and entry.name == "opt/hmi/otf/socket.cfg":
                return None
            if entry.name in qemu_cdc_configs:
                return None
            if qemu_usb_script is not None and entry.name == "bin/start_usb.sh":
                return None
            if hmi_coding_library is not None and entry.name == HMI_CODING_PATH:
                return None
            if entry.name in hmi_binary_overlays:
                return None
            if (
                hmi_variantregistry is not None
                and entry.name == HMI_VARIANTREGISTRY_PATH
            ):
                return None
            return _normalize(entry)

        for item in sorted(root.iterdir(), key=lambda path: path.name):
            archive.add(item, arcname=item.name, recursive=True, filter=select)
        if profile_config is not None:
            entry = archive.gettarinfo(
                str(profile_config), arcname="opt/sys/etc/starter.cfg"
            )
            entry.size = len(profile_config_data)
            archive.addfile(_normalize(entry), io.BytesIO(profile_config_data))
        if otf_socket_config is not None:
            entry = archive.gettarinfo(
                str(otf_socket_config), arcname="opt/hmi/otf/socket.cfg"
            )
            entry.size = len(otf_socket_config_data)
            archive.addfile(_normalize(entry), io.BytesIO(otf_socket_config_data))
        for relative_path, config_data in qemu_cdc_configs.items():
            umass_config = root / relative_path
            entry = archive.gettarinfo(str(umass_config), arcname=relative_path)
            entry.size = len(config_data)
            archive.addfile(_normalize(entry), io.BytesIO(config_data))
        if qemu_usb_script is not None:
            entry = archive.gettarinfo(
                str(qemu_usb_script), arcname="bin/start_usb.sh"
            )
            entry.size = len(qemu_usb_script_data)
            archive.addfile(_normalize(entry), io.BytesIO(qemu_usb_script_data))
        if hmi_coding_library is not None:
            entry = archive.gettarinfo(
                str(hmi_coding_library), arcname=HMI_CODING_PATH
            )
            entry.size = len(hmi_coding_library_data)
            archive.addfile(_normalize(entry), io.BytesIO(hmi_coding_library_data))
        for relative_path, data in hmi_binary_overlays.items():
            entry = archive.gettarinfo(str(root / relative_path), arcname=relative_path)
            archive.addfile(_normalize(entry), io.BytesIO(data))
        if hmi_variantregistry is not None:
            entry = archive.gettarinfo(
                str(hmi_variantregistry), arcname=HMI_VARIANTREGISTRY_PATH
            )
            entry.size = len(hmi_variantregistry_data)
            archive.addfile(_normalize(entry), io.BytesIO(hmi_variantregistry_data))

    if compressed:
        with temporary_output.open("wb") as raw:
            with gzip.GzipFile(
                filename="", mode="wb", compresslevel=6, fileobj=raw, mtime=0
            ) as compressed_output:
                with tarfile.open(
                    fileobj=compressed_output,
                    mode="w",
                    format=tarfile.PAX_FORMAT,
                ) as archive:
                    add_tree(archive)
    else:
        with tarfile.open(temporary_output, mode="w", format=tarfile.PAX_FORMAT) as archive:
            add_tree(archive)
    if cache_unchanged:
        os.replace(temporary_output, output)
        temporary_sidecar = sidecar.with_name(f"{sidecar.name}.tmp-{os.getpid()}")
        temporary_sidecar.write_text(cache_key + "\n", encoding="ascii")
        os.replace(temporary_sidecar, sidecar)
    return output.stat().st_size


def _normalize(entry: tarfile.TarInfo) -> tarfile.TarInfo:
    entry.uid = 0
    entry.gid = 0
    entry.uname = ""
    entry.gname = ""
    entry.mtime = 0
    if entry.isfile() and Path(entry.name).parent.name in {"bin", "sbin", "lib"}:
        # Preserve the executable mode expected for QNX programs and libraries.
        entry.mode |= 0o111
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rootfs_tree", type=Path)
    parser.add_argument("output_archive", type=Path)
    parser.add_argument(
        "--gzip", action="store_true", help="compress the PAX archive with gzip"
    )
    parser.add_argument(
        "--emulator-profile",
        choices=("vehicle", "vexpress", "omap5", "omap5-graphics"),
        default="vehicle",
        help="use the source BMW config, a headless profile, or start OMAP5 TILER/SCREEN for graphics development",
    )
    parser.add_argument(
        "--software-screen-variant",
        action="store_true",
        help="use software Screen and configure LayerManagerService for the emulator display",
    )
    parser.add_argument(
        "--hmi-without-comms",
        action="store_true",
        help="omit the DSI/MOST command option from the native HmiMain3D starter entry",
    )
    parser.add_argument(
        "--suppress-hmi",
        action="store_true",
        help="stop the starter-managed HMI package so a diagnostic direct launch cannot duplicate it",
    )
    parser.add_argument(
        "--defer-otf-agent",
        action="store_true",
        help="stop the starter-managed BMW OTF agent so a direct launch can start it after networking",
    )
    parser.add_argument("--most-sipc-stack", action="store_true",
                        help="route stock MOST clients through the emulator's isolated IPv4 stack")
    parser.add_argument(
        "--hmi-coding-id6-light",
        action="store_true",
        help="use the shipped BMW HMI coding defaults with ID6 Light selected (emulator-only)",
    )
    parser.add_argument(
        "--hmi-coding-cid-1440",
        action="store_true",
        help="select 1440x540 in the native CID resolution coding (emulator-only)",
    )
    parser.add_argument(
        "--hmi-coding-cid-touch",
        action="store_true",
        help="enable the native CID touch decoder in the emulator-only coding defaults",
    )
    parser.add_argument(
        "--hmi-bench-input",
        action="store_true",
        help="initialize native home input for an awake emulated CID",
    )
    parser.add_argument(
        "--hmi-resource-en-us",
        action="store_true",
        help="initialize the native resource manager with English (US)",
    )
    parser.add_argument(
        "--hmi-coding-developer-menu",
        action="store_true",
        help="enable the HMI developer-menu feature for its inspector service (emulator-only)",
    )
    parser.add_argument(
        "--hmi-coding-remote-hmi",
        action="store_true",
        help="code REMOTE_HMI active so the HMI starts RemotingBundle and plugin apps (emulator-only)",
    )
    parser.add_argument(
        "--hmi-coding-camera-rvc",
        action="store_true",
        help="select the F32 reversing-camera coding required by the native camera factory (emulator-only)",
    )
    parser.add_argument(
        "--hmi-variantregistry-f32",
        action="store_true",
        help="select indexed F32 3D vehicle assets in an emulator-only PBVAR copy",
    )
    parser.add_argument(
        "--cache-unchanged",
        action="store_true",
        help="reuse the output archive when the staged tree and profile are unchanged",
    )
    args = parser.parse_args()
    try:
        size = archive_rootfs(
            args.rootfs_tree,
            args.output_archive,
            compressed=args.gzip,
            emulator_profile=args.emulator_profile,
            software_screen_variant=args.software_screen_variant,
            hmi_without_comms=args.hmi_without_comms,
            suppress_hmi=args.suppress_hmi,
            defer_otf_agent=args.defer_otf_agent,
            most_sipc_stack=args.most_sipc_stack,
            hmi_coding_id6l=args.hmi_coding_id6_light,
            hmi_coding_cid_1440=args.hmi_coding_cid_1440,
            hmi_coding_cid_touch=args.hmi_coding_cid_touch,
            hmi_bench_input=args.hmi_bench_input,
            hmi_resource_en_us=args.hmi_resource_en_us,
            hmi_coding_developer_menu=args.hmi_coding_developer_menu,
            hmi_coding_remote_hmi=args.hmi_coding_remote_hmi,
            hmi_coding_camera_rvc=args.hmi_coding_camera_rvc,
            hmi_variantregistry_f32=args.hmi_variantregistry_f32,
            cache_unchanged=args.cache_unchanged,
        )
    except (OSError, RuntimeError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    kind = "gzip-compressed PAX" if args.gzip else "PAX"
    print(f"Archived root tree ({kind}): {size:,} bytes at {args.output_archive.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
