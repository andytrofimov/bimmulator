#!/usr/bin/env python3
"""Launch a named iDrive HMI profile with isolated, versioned output paths."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys


RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
ENV_NAME_RE = re.compile(r"^IDRIVE_[A-Z0-9_]+$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path, help="profile JSON path")
    parser.add_argument("--run-id", help="unique run ID; defaults to a UTC timestamp")
    parser.add_argument(
        "--set", dest="overrides", action="append", default=[], metavar="NAME=VALUE",
        help="override a setting or path already declared by the profile",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    profile_path = args.profile if args.profile.is_absolute() else repo_root / args.profile
    profile_path = profile_path.resolve()
    try:
        profile = json.loads(profile_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        parser.error(f"cannot read profile {profile_path}: {error}")
    if profile.get("schema") != "idrive6-hmi-launch-profile-v1":
        parser.error("unsupported HMI launch profile schema")
    settings = profile.get("settings")
    paths = profile.get("paths")
    if not isinstance(settings, dict) or not isinstance(paths, dict):
        parser.error("profile must contain settings and paths objects")
    allowed_overrides = set(settings) | set(paths)
    overrides: dict[str, str] = {}
    for item in args.overrides:
        name, separator, value = item.partition("=")
        if not separator or not ENV_NAME_RE.fullmatch(name) or name not in allowed_overrides:
            parser.error(f"override must name a setting or path in the profile: {item!r}")
        overrides[name] = value

    cache_dir = Path(os.environ.get("IDRIVE_CACHE_DIR", repo_root / "build/idrive6-cache"))
    cache_dir = cache_dir.expanduser().resolve()
    run_id = args.run_id or os.environ.get("IDRIVE_HMI_RUN_ID")
    if not run_id:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not RUN_ID_RE.fullmatch(run_id):
        parser.error("run ID may contain only letters, digits, dot, underscore and hyphen")
    run_dir = cache_dir / "runs" / run_id
    try:
        run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f"run output directory already exists: {run_dir}")

    replacements = {
        "repo_root": str(repo_root),
        "cache_dir": str(cache_dir),
        "run_dir": str(run_dir),
        "run_id": run_id,
    }
    env = os.environ.copy()
    env["IDRIVE_CACHE_DIR"] = str(cache_dir)
    for source in (settings, paths):
        for name, value in source.items():
            if not isinstance(name, str) or not ENV_NAME_RE.fullmatch(name):
                parser.error(f"invalid profile environment name: {name!r}")
            if not isinstance(value, str):
                parser.error(f"profile value for {name} must be a string")
            try:
                env[name] = value.format_map(replacements)
            except KeyError as error:
                parser.error(f"unknown profile path placeholder in {name}: {error}")
    env.update(overrides)
    env.update({
        "IDRIVE_HMI_PROFILE_NAME": profile["name"],
        "IDRIVE_HMI_PROFILE_FILE": str(profile_path),
        "IDRIVE_HMI_RUN_ID": run_id,
        "IDRIVE_HMI_RUN_DIR": str(run_dir),
        "IDRIVE_HMI_RUN_MANIFEST": str(run_dir / "run-manifest.json"),
    })

    qmp_socket_template = paths.get("IDRIVE_QEMU_QMP_SOCKET", "")
    qmp_socket = env.get("IDRIVE_QEMU_QMP_SOCKET", "")
    qmp_path_limit = 104 if sys.platform == "darwin" else 108 if sys.platform.startswith("linux") else None
    if (
        qmp_path_limit is not None
        and "{run_dir}" in qmp_socket_template
        and "IDRIVE_QEMU_QMP_SOCKET" not in overrides
        and len(os.fsencode(qmp_socket)) >= qmp_path_limit
    ):
        short_name = hashlib.sha256(os.fsencode(qmp_socket)).hexdigest()[:12]
        env["IDRIVE_QEMU_QMP_SOCKET"] = f"/tmp/idrive6-qmp-{short_name}.sock"
        print(
            f"QMP socket path exceeds the host's {qmp_path_limit}-byte limit; using "
            f"{env['IDRIVE_QEMU_QMP_SOCKET']}",
            flush=True,
        )

    realized_root = Path(env["IDRIVE_ROOTFS_TREE"])
    if not realized_root.is_dir():
        parser.error(
            f"cached realized root is missing: {realized_root}; materialize it once with the repository staging workflow"
        )
    print(f"HMI profile: {profile['name']}", flush=True)
    print(f"Run ID: {run_id}", flush=True)
    print(f"Run artifacts: {run_dir}", flush=True)
    print(f"Pre-QEMU manifest: {env['IDRIVE_HMI_RUN_MANIFEST']}", flush=True)
    emulator = repo_root / "run-emulator.sh"
    os.execvpe(str(emulator), [str(emulator)], env)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
