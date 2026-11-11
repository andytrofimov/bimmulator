"""Host-only checks of the actual embed() HMI script builder; no guest inputs."""

import ast
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools/embed-qnx6-rootfs.py"
TREE = ast.parse(SOURCE.read_text())
EMBED = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "embed")
# The baseline has no separate build_stage2_script(): compile its actual HMI
# builder block verbatim, avoiding the surrounding IFS/firmware I/O entirely.
BLOCK = next(n for n in EMBED.body if isinstance(n, ast.If)
             and ast.unparse(n.test) == "os.environ.get('IDRIVE_HMI_FORCE_START') == '1'")
BUILDER = compile(ast.Module(body=[BLOCK], type_ignores=[]), str(SOURCE), "exec")


def build_script(flags):
    scope = dict(os=os, re=re, software_screen_probe=True,
                 variant_helper="synthetic-helper", controller_library=None,
                 title_cache_helper=None, angle_hmi_surface_width="",
                 angle_hmi_surface_height="", angle_egl_hmi_preflight=False)
    env = dict(IDRIVE_HMI_FORCE_START="1", IDRIVE_ANGLE_EGL_HMI="1",
               IDRIVE_QEMU_CDC_NETWORK="1", **flags)
    with patch.dict(os.environ, env, clear=True):
        exec(BUILDER, scope)
    return scope["hmi_force_start"]


class NativeBootstrapTests(unittest.TestCase):
    def test_direct_bootstrap_order_and_bounded_failure(self):
        script = build_script(dict(IDRIVE_DIRECT_EHCI="1", IDRIVE_DIRECT_LAYER_MANAGER="1"))
        usb = script.index("/bin/io-usb -c -vvv -d hb-ehci-omap3")
        layer = script.index("/opt/sys/bin/LayerManagerService -w1440 -h540 -d:1")
        self.assertLess(script.index("while [ ! -e /dev/screen ]"), usb)
        self.assertLess(script.index("done\nexport MALLOC_ARENA_SIZE"), usb)
        self.assertLess(usb, script.index("Waiting for QEMU CDC device"))
        self.assertLess(script.index("ANGLE RPC isolated network ready"), layer)
        self.assertLess(layer, script.index("exec /opt/hmi/ID5/bin/HmiMain3D"))
        self.assertIn("if [ ! -e /dev/io-usb/io-usb ]; then", script)
        self.assertIn("if [ ! -e /dev/layermanager ]; then", script)
        self.assertIn("while [ ! -e /dev/layermanager ] && [ $n -lt 30 ]; do /boot/bin/sleep 1; n=$((n + 1)); done", script)
        self.assertIn("if [ ! -e /dev/layermanager ]; then echo 'Direct LayerManagerService did not become ready' >/dev/ser1; exit 1; fi", script)
        self.assertIn("QEMU CDC device 0xa4a1 did not appear within 30 guest seconds", script)
        self.assertIn("libEGL_X.gpp.so:libGLESv2_X_FORWARD.gpp.so:libKD_X.gpp.so", script)

    def test_direct_flags_are_independent_explicit_opt_ins(self):
        for flags in ({}, dict(IDRIVE_DIRECT_EHCI="0", IDRIVE_DIRECT_LAYER_MANAGER="0")):
            script = build_script(flags)
            self.assertNotIn("/bin/io-usb -c", script)
            self.assertNotIn("/opt/sys/bin/LayerManagerService", script)
        self.assertNotIn("/opt/sys/bin/LayerManagerService", build_script(dict(IDRIVE_DIRECT_EHCI="1")))
        self.assertNotIn("/bin/io-usb -c", build_script(dict(IDRIVE_DIRECT_LAYER_MANAGER="1")))

    def test_f32_profile_enables_bootstrap_without_weakening_native_path(self):
        settings = json.loads((ROOT / "profiles/f32-x20511i-id6-light.json").read_text())["settings"]
        for key in ("IDRIVE_DIRECT_EHCI", "IDRIVE_DIRECT_LAYER_MANAGER",
                    "IDRIVE_HMI_FORCE_START", "IDRIVE_QEMU_CDC_NETWORK",
                    "IDRIVE_ANGLE_EGL_HMI", "IDRIVE_ANGLE_EGL_MAILBOX"):
            self.assertEqual(settings[key], "1", key)
        self.assertEqual(settings["IDRIVE_HMI_NO_COMMS"], "0")
        self.assertEqual(settings["IDRIVE_HMI_COMM_MODULES"], "DSI,MOSTSubSystem")
