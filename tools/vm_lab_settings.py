"""Host-only pending VM settings. No guest access, commands or environment mutation.

The server supplies both paths; HTTP payloads can supply only {"values": {...}}.
Use a dedicated owner-only directory inside the launcher's private cache. Reading
pending settings does NOT prove those options are active in an existing guest.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import threading


GROUPS = [
    {"id": "mocks", "label": "Mocks", "submenu": "ConnectedDrive"},
    {"id": "coding", "label": "Coding", "submenu": "Head unit · ID6 Light"},
]
SCHEMA = {
    "connecteddrive_service": {"type": "boolean", "default": False, "group": "mocks",
                              "label": "ConnectedDrive services", "available": False},
    "connecteddrive_availability": {"type": "boolean", "default": False, "group": "mocks",
                                   "label": "ConnectedDrive availability", "available": False,
                                   "requires": "connecteddrive_service"},
    "developer_menu": {"type": "boolean", "default": True, "group": "coding",
                       "label": "Developer menu"},
    "reverse_camera": {"type": "boolean", "default": True, "group": "coding",
                       "label": "Reverse camera (RVC)", "requires": "f32_resources"},
    "f32_resources": {"type": "boolean", "default": True, "group": "coding",
                      "label": "F32 resources / VariantRegistry (3D)"},
}
DEFAULTS = {key: item["default"] for key, item in SCHEMA.items()}
# Fixed names only. The launcher, not the browser, controls all provisioning paths.
LAUNCH_ENV = {
    "connecteddrive_service": "IDRIVE_VM_CONNECTEDDRIVE_MOCK",
    "connecteddrive_availability": "IDRIVE_VM_CONNECTEDDRIVE_AVAILABILITY_MOCK",
    "developer_menu": "IDRIVE_HMI_CODING_DEVELOPER_MENU",
    "reverse_camera": "IDRIVE_HMI_CODING_CAMERA_RVC",
    "f32_resources": "IDRIVE_HMI_VARIANTREGISTRY_F32",
}


def validate_values(values):
    """Require a complete canonical object; no patches or arbitrary launch keys."""
    if type(values) is not dict or set(values) != set(SCHEMA):
        raise ValueError("expected exactly the supported settings keys")
    result = {}
    for key, item in SCHEMA.items():
        value = values[key]
        if type(value) is not bool:
            raise ValueError(f"{key}: expected boolean")
        result[key] = value
    for key, item in SCHEMA.items():
        dependency = item.get("requires")
        if dependency and result[key] and not result[dependency]:
            raise ValueError(f"{key} requires {dependency}")
    for key in ("connecteddrive_service", "connecteddrive_availability"):
        if result[key]:
            raise ValueError(f"UNAVAILABLE_CAPABILITY: {key} is unsupported in this release")
    return result


def validate_payload(payload):
    if type(payload) is not dict or set(payload) != {"values"}:
        raise ValueError("expected JSON {values: complete supported settings}")
    return validate_values(payload["values"])


def launch_values(values):
    """Return only fixed native variable names and literal 0/1 values."""
    return {LAUNCH_ENV[key]: "1" if value else "0"
            for key, value in validate_values(values).items()}


def decode_json(data):
    """Reject duplicate keys as malformed, including nested values objects."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


class SettingsStore:
    def __init__(self, path, private_dir, active_values=None):
        # Never expand a browser string or resolve a symlink into an authority.
        self.directory = Path(private_dir)
        self.path = Path(path)
        if (not self.directory.is_absolute() or not self.path.is_absolute()
                or self.path.parent != self.directory or self.path.name in ("", ".", "..")
                or self.directory.resolve() != self.directory):
            raise ValueError("settings path must be a direct child of the fixed absolute private directory")
        self._check_directory()
        self.active = None if active_values is None else validate_values(active_values)
        self.lock = threading.RLock()

    def _check_directory(self):
        info = self.directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or self.directory.resolve() != self.directory
                or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise ValueError("settings directory must be owned, private and not symlinked")

    def _read(self):
        self._check_directory()
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return DEFAULTS.copy(), False
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077
                    or info.st_size > 4096):
                raise ValueError("unsafe settings file")
            data = decode_json(stream.read(4097))
        if type(data) is not dict or set(data) != {"version", "values"} or type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("unsupported settings document")
        return validate_values(data["values"]), True

    def load(self, *, require_saved=False):
        with self.lock:
            values, saved = self._read()
            if require_saved and not saved:
                raise ValueError("boot settings snapshot is missing")
            return values

    def snapshot(self):
        with self.lock:
            values, saved = self._read()
            return {"values": values, "groups": GROUPS, "schema": SCHEMA,
                    "restart_required": values != self.active if self.active is not None else saved,
                    "application": "next_vm_start", "active_known": self.active is not None,
                    "boot_values": None if self.active is None else self.active.copy(),
                    "pending_saved": saved}

    def save(self, payload):
        values = validate_payload(payload)
        with self.lock:
            self._read()  # Refuse to replace unsafe, malformed or foreign files.
            fd, name = tempfile.mkstemp(prefix=".pending-", dir=self.directory)
            source = Path(name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump({"version": 1, "values": values}, stream, ensure_ascii=False)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                self._check_directory()
                # Verify the exact absolute replacement endpoints immediately before replace.
                if (source.resolve() != source or source.parent != self.directory
                        or self.path.parent.resolve() != self.directory
                        or self.path.is_symlink() or self.path.resolve() != self.path):
                    raise ValueError("unsafe atomic settings target")
                os.replace(source, self.path)
                directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if source.exists():
                    if source.resolve() != source or source.parent != self.directory:
                        raise ValueError("unsafe temporary cleanup target")
                    source.unlink()
            return self.snapshot()
