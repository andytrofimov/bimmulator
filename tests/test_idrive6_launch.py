import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
launcher = runpy.run_path(str(TOOLS / "idrive6-launch.py"))
checked_config = launcher["checked_config"]


class LaunchConfigTests(unittest.TestCase):
    def config(self, host=("Darwin", "arm64"), **options):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            file = project / "idrive6.toml"
            file.touch()
            output = json.dumps({"psdzdata": str(root / "psdzdata"), **options})
            with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=output)), \
                    patch("platform.system", return_value=host[0]), \
                    patch("platform.machine", return_value=host[1]):
                return checked_config(project, file, "nix")

    def test_module_selection_defaults_to_both_ecus(self):
        self.assertEqual(self.config()["modules"], ["head-unit", "6wb"])

    def test_module_selection_can_start_either_ecu(self):
        for module in ("head-unit", "6wb"):
            self.assertEqual(self.config(modules=[module])["modules"], [module])

    def test_invalid_module_selections_fail_validation(self):
        for modules in ("6wb", [], ["hud"], ["6wb", "6wb"], [{}]):
            with self.subTest(modules=modules), self.assertRaisesRegex(ValueError, "modules must select"):
                self.config(modules=modules)

    def test_host_display_defaults_and_overrides(self):
        for host, native in ((("Darwin", "arm64"), "cocoa"), (("Linux", "x86_64"), "gtk")):
            with self.subTest(host=host):
                self.assertEqual(self.config(host)["display"], native)
                for display in (native, "none"):
                    self.assertEqual(self.config(host, display=display)["display"], display)

    def test_display_from_other_host_is_rejected(self):
        for host, display in ((("Darwin", "arm64"), "gtk"), (("Linux", "x86_64"), "cocoa"),
                              (("Linux", "x86_64"), "sdl"), (("Linux", "x86_64"), None),
                              (("Linux", "x86_64"), []), (("Darwin", "arm64"), {})):
            with self.subTest(host=host, display=display), self.assertRaisesRegex(ValueError, "display must be"):
                self.config(host, display=display)

    def test_unsupported_host_is_rejected_even_headless(self):
        for host in (("Darwin", "x86_64"), ("Linux", "aarch64"), ("Windows", "AMD64")):
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, "Supported hosts"):
                self.config(host, display="none")

    def test_head_unit_environment_preserves_selected_display_and_server(self):
        for host, display in ((("Darwin", "arm64"), "cocoa"), (("Linux", "x86_64"), "gtk"),
                              (("Linux", "x86_64"), "none")):
            with self.subTest(host=host, display=display):
                config = self.config(host, display=display)
                with patch.dict(os.environ, {"IDRIVE_ANGLE_SERVER": "/fixture/host-server"}):
                    command, env = launcher["head_unit_command"](Path("/project"), config, Path("/firmware"))
                self.assertEqual(env["IDRIVE_DISPLAY"], display)
                self.assertEqual(env["IDRIVE_ANGLE_EGL_SERVER_BIN"], "/fixture/host-server")
                self.assertEqual(env["IDRIVE_QEMU_CPUS"], "2")
                self.assertEqual(command[1], "/project/tools/run-hmi-profile.py")
                with patch.dict(os.environ, {"IDRIVE_ANGLE_SERVER": "", "IDRIVE_ANGLE_EGL_SERVER_BIN": "/fixture/direct-server"}):
                    _, direct = launcher["head_unit_command"](Path("/project"), config, Path("/firmware"))
                self.assertEqual(direct["IDRIVE_ANGLE_EGL_SERVER_BIN"], "/fixture/direct-server")

    def test_kombi_uses_sdl_for_either_native_gui_and_none_for_headless(self):
        for display, expected in (("cocoa", "sdl"), ("gtk", "sdl"), ("none", "none")):
            with self.subTest(display=display), tempfile.TemporaryDirectory(prefix="6wb-test-") as directory:
                cache = Path(directory)
                run = cache / "run"
                run.mkdir()
                # Sparse RAM and a local management socket let the real session
                # setup reach its Popen argument composition without a guest.
                with (run / "vehicle.ram").open("wb") as ram:
                    ram.truncate(launcher["RAM_SIZE"])
                with socket.socket(socket.AF_UNIX) as qmp:
                    qmp.bind(str(run / "qmp.sock"))
                    kombi = Mock()
                    kombi.poll.return_value = 0
                    simulator = Mock()
                    with patch("tempfile.mkdtemp", return_value=str(run)), \
                            patch("subprocess.Popen", side_effect=[kombi, simulator]) as popen, \
                            patch.dict(launcher["run_kombi_session"].__globals__, {"stop_process": Mock(), "child_status": lambda process: process.poll()}):
                        status = launcher["run_kombi_session"](
                            Path("/project"), cache, {"display": display},
                            (Path("gss"), Path("config"), Path("graphics")), None,
                        )
                    self.assertEqual(status, 0)
                    args = popen.call_args_list[0].args[0]
                    self.assertEqual(args[args.index("--display") + 1], expected)
