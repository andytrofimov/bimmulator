#!/usr/bin/env python3
"""Record the exact native HMI boot inputs immediately before QEMU starts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"path": str(path), "exists": False}
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return {"path": str(path), "exists": True, "bytes": path.stat().st_size, "sha256": sha.hexdigest()}


def command_output(argv: list[str]) -> str | None:
    try:
        return subprocess.run(argv, text=True, capture_output=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-file", type=Path, required=True)
    parser.add_argument("--prepared-image", type=Path, required=True)
    parser.add_argument("--root-archive", type=Path)
    parser.add_argument("qemu_argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = list(args.qemu_argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        parser.error("the exact QEMU command and arguments are required")
    if args.output.exists():
        parser.error(f"refusing to replace an existing manifest: {args.output}")

    repo_root = Path(__file__).resolve().parents[1]
    profile_file = args.profile_file.resolve()
    profile = json.loads(profile_file.read_text())
    env = os.environ
    root = Path(env["IDRIVE_REALIZED_ROOTFS"]).resolve()
    cache_dir = Path(env["IDRIVE_CACHE_DIR"]).resolve()
    qemu_path = shutil.which(argv[0]) or argv[0]
    command_name = Path(argv[0]).name
    input_paths = {
        "profile": profile_file,
        "nix_lock": repo_root / "flake.lock",
        "launcher": repo_root / "run-emulator.sh",
        "rootfs_archive_builder": repo_root / "tools/archive-idrive-rootfs.py",
        "qnx_boot_embedder": repo_root / "tools/embed-qnx6-rootfs.py",
        "qnx_angle_provider_source": repo_root / "tools/qnx-angle-egl-provider.c",
        "guest_rpc_forwarder": repo_root / "tools/qemu-guestfwd-proxy.py",
        "angle_rpc_server_source": repo_root / "tools/angle-egl-rpc-server.cpp",
        "otf_capture_client": repo_root / "tools/otf-capture-client.py",
        "hmi_capture_helper": repo_root / "tools/capture-hmi-startup.py",
        "profile_launcher": repo_root / "tools/run-hmi-profile.py",
        "hmi_main3d": root / "opt/hmi/ID5/bin/HmiMain3D",
        "hmi_coding_library": root / "opt/hmi/ID5/lib/libhmicoding.so",
        "hmi_resource_library": root / "opt/hmi/ID5/lib/libhmidb.so",
        "qnx_pdebug": root / "bin/pdebug",
        "qnx_devc_pty": root / "bin/devc-pty",
        "qnx_angle_provider": Path(env.get("IDRIVE_ANGLE_EGL_PROVIDER", cache_dir / "libidrive-angle-provider.so")),
        "host_angle_server": Path(env.get("IDRIVE_ANGLE_EGL_SERVER_BIN", cache_dir / "angle-egl-rpc-server")),
        "vertex_shader_map": Path(env["IDRIVE_HMI_VERTEX_SHADER_MAP_MANIFEST"]),
        "fragment_shader_map": Path(env["IDRIVE_HMI_FRAGMENT_SHADER_MAP_MANIFEST"]),
        "prepared_ifs": args.prepared_image.resolve(),
        "qemu_binary": Path(qemu_path).resolve(),
    }
    root_archive = args.root_archive
    if root_archive is None and env.get("IDRIVE_ROOT_ARCHIVE"):
        root_archive = Path(env["IDRIVE_ROOT_ARCHIVE"])
    if root_archive is not None:
        input_paths["cached_root_archive"] = root_archive.resolve()
    variant_helper = env.get("IDRIVE_STARTER_VARIANT_HELPER")
    if variant_helper:
        input_paths["starter_variant_helper"] = Path(variant_helper)
    title_cache_helper = env.get("IDRIVE_HMI_TITLE_CACHE_HELPER")
    controller_library = env.get("IDRIVE_HMI_CONTROLLER_LIBRARY")
    if controller_library:
        input_paths["hmi_controller_library"] = Path(controller_library)
    if title_cache_helper:
        input_paths["hmi_title_cache_helper"] = Path(title_cache_helper)
    if env.get("IDRIVE_HMI_CID_POINTER") == "1":
        input_paths["cid_pointer_relay"] = repo_root / "tools/idrive-cid-input.py"

    settings = sorted(set(profile.get("settings", {})) | set(profile.get("paths", {})))
    settings.extend([
        "IDRIVE_CACHE_DIR", "IDRIVE_HMI_PROFILE_NAME", "IDRIVE_HMI_RUN_ID",
        "IDRIVE_HMI_RUN_DIR", "IDRIVE_HMI_RUN_MANIFEST",
        "IDRIVE_STARTER_VARIANT", "IDRIVE_HMI_LAYER_MANAGER", "IDRIVE_DISPLAY",
        "IDRIVE_STORAGE_DIAGNOSTICS", "IDRIVE_ROOTFS_EXTRA_MIB",
        "IDRIVE_DEBUG_SHELL", "IDRIVE_SERIAL0_SOCKET",
        "IDRIVE_HMI_TITLE_CACHE_PROBE",
        "IDRIVE_VNC", "IDRIVE_VNC_SOCKET", "IDRIVE_HMI_CID_PORT",
        "IDRIVE_HMI_CODING_CID_TOUCH",
        "IDRIVE_HMI_BENCH_INPUT",
        "IDRIVE_HMI_RESOURCE_EN_US",
        "IDRIVE_HMI_CID_POINTER",
    ])
    effective_config = {name: env.get(name) for name in sorted(set(settings))}
    try:
        status = command_output(["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=normal"])
        commit = command_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"])
        branch = command_output(["git", "-C", str(repo_root), "branch", "--show-current"])
        diff = subprocess.run(["git", "-C", str(repo_root), "diff", "--binary", "HEAD"], capture_output=True, check=True).stdout
        untracked_output = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard", "-z"],
            capture_output=True, check=True,
        ).stdout
        untracked = []
        for encoded_path in untracked_output.split(b"\0"):
            if not encoded_path:
                continue
            path = repo_root / os.fsdecode(encoded_path)
            record = digest(path)
            record["path"] = path.relative_to(repo_root).as_posix()
            untracked.append(record)
        untracked_bytes = json.dumps(untracked, sort_keys=True).encode()
        git_state = {
            "commit": commit,
            "branch": branch,
            "status_porcelain": status,
            "diff_sha256": sha_bytes(diff),
            "untracked_files": untracked,
            "working_tree_sha256": sha_bytes(diff + b"\0" + untracked_bytes),
        }
    except (OSError, subprocess.CalledProcessError):
        git_state = {"error": "git metadata could not be read"}

    manifest = {
        "schema": "idrive6-hmi-run-manifest-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": env.get("IDRIVE_HMI_RUN_ID"),
        "profile_name": profile.get("name"),
        "profile_purpose": profile.get("purpose"),
        "effective_configuration": effective_config,
        "hmi_launch": {
            "binary": "/opt/hmi/ID5/bin/HmiMain3D",
            "arguments": (
                ([f"-c={env.get('IDRIVE_HMI_COMM_MODULES', 'DSI,MOSTSubSystem')}"]
                 if env.get("IDRIVE_HMI_NO_COMMS") != "1" else [])
                + [
                    "-ro=/opt/hmi/data/ro/",
                    "-rw=/fs/sda0/opt/hmi/data/rw/",
                    "-sp=/fs/sda0/opt/hmi/data/rw/",
                    "-vp=/opt/hmi/data/ro/",
                    "-cp=/opt/hmi/data/ro/",
                    "-iba1=/mnt/data/iba/swe1/",
                    "-iba2=/mnt/data/iba/anim-all/swe2/",
                    "-h=10000",
                    "-z=4",
                ]
                + ([f"-lm={env['IDRIVE_HMI_LAYER_MANAGER'].strip().lower()}"]
                   if env.get("IDRIVE_HMI_LAYER_MANAGER", "").strip().lower() in {"sdl", "glfw"}
                   else [])
            ),
            "coding_overlay_profile": "+".join(
                overlay
                for enabled, overlay in (
                    (env.get("IDRIVE_HMI_CODING_ID6_LIGHT") == "1", "id6-light"),
                    (env.get("IDRIVE_HMI_CODING_CID_1440") == "1", "cid-1440x540"),
                    (env.get("IDRIVE_HMI_CODING_CID_TOUCH") == "1", "cid-touch"),
                    (env.get("IDRIVE_HMI_CODING_DEVELOPER_MENU") == "1", "developer-menu"),
                    (env.get("IDRIVE_HMI_CODING_CAMERA_RVC") == "1", "f32-camera-rvc"),
                )
                if enabled
            ) or None,
            "vehicle_asset_overlay_profile": (
                "f32-variantregistry"
                if env.get("IDRIVE_HMI_VARIANTREGISTRY_F32") == "1"
                else None
            ),
            "bench_input_overlay": env.get("IDRIVE_HMI_BENCH_INPUT") == "1",
            "initial_resource_language": "en-US" if env.get("IDRIVE_HMI_RESOURCE_EN_US") == "1" else None,
        },
        "host": {"platform": sys.platform, "python": sys.version.split()[0], "nix": command_output(["nix", "--version"])},
        "qemu": {"command": qemu_path, "version": command_output([qemu_path, "--version"])},
        "git": git_state,
        "qemu_argv": argv,
        "output_directory": env.get("IDRIVE_HMI_RUN_DIR"),
        "artifacts": {name: digest(path) for name, path in input_paths.items()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_name(args.output.name + ".tmp")
    temp.write_text(json.dumps(manifest, indent=2) + "\n")
    temp.replace(args.output)
    print(f"HMI run manifest written: {args.output}")
    print(f"HMI run manifest input artifacts: {len(input_paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
