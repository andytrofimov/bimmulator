"""Firmware-free integration checks for a built host EGL server (protocol 4).

Set IDRIVE_TEST_EGL_SERVER to opt in; no VM or existing server is used.
"""
import ctypes
import mmap
import os
import platform
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest


HEADER = struct.Struct(">4sHH6I")


def words(*values):
    return struct.pack(">" + "I" * len(values), *values)


class EGLServerFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary = os.environ.get("IDRIVE_TEST_EGL_SERVER")
        if not binary:
            raise unittest.SkipTest("set IDRIVE_TEST_EGL_SERVER to a built host EGL RPC server")
        cls.binary = str(Path(binary).resolve(strict=True))

    def start_server(self, arguments, extra_environment=None):
        self.log = tempfile.TemporaryFile(mode="w+b")
        self.addCleanup(self.log.close)
        environment = os.environ.copy()
        # The Mesa backend must work without X11/Wayland, even for GUI QEMU runs.
        environment.pop("DISPLAY", None)
        environment.pop("WAYLAND_DISPLAY", None)
        environment["LIBGL_ALWAYS_SOFTWARE"] = "1"
        environment.update(extra_environment or {})
        self.process = subprocess.Popen(
            [self.binary, *arguments], env=environment,
            stdout=self.log, stderr=self.log,
        )
        self.addCleanup(self.stop_server)
        self.sequence = 0

    def setUp(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            self.port = reservation.getsockname()[1]
        self.start_server(["--port", str(self.port)])
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                break
            try:
                with self.connect():
                    return
            except OSError:
                time.sleep(0.02)
        self.log.seek(0)
        self.fail("host EGL server did not start:\n" + self.log.read().decode(errors="replace"))

    def stop_server(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def connect(self):
        return socket.create_connection(("127.0.0.1", self.port), timeout=5)

    def receive(self, connection, size):
        data = bytearray()
        while len(data) < size:
            block = connection.recv(size - len(data))
            self.assertTrue(block, "unexpected EOF from host EGL server")
            data.extend(block)
        return bytes(data)

    def request(self, connection, opcode, a=0, b=0, c=0, payload=b"", *,
                magic=b"I6ER", version=4, length=None, sequence=None, client=1):
        self.sequence += 1
        sequence = self.sequence if sequence is None else sequence
        connection.sendall(HEADER.pack(magic, version, opcode, client, a, b, c, sequence,
                                       len(payload) if length is None else length) + payload)
        reply = HEADER.unpack(self.receive(connection, HEADER.size))
        self.assertEqual(reply[:2], (b"I6EA", 4))
        self.assertEqual(reply[-1], sequence)
        self.assertLessEqual(reply[-2], 16 * 1024 * 1024)
        return reply, self.receive(connection, reply[-2])

    def ok(self, connection, opcode, *args, **kwargs):
        reply, payload = self.request(connection, opcode, *args, **kwargs)
        self.assertEqual(reply[2:4], (0, 0), f"RPC opcode {opcode} failed: {reply}")
        return reply[4:7], payload

    def context(self, connection, *, window=False, stencil=False, client=1):
        def ok(opcode, *args, **kwargs):
            return self.ok(connection, opcode, *args, client=client, **kwargs)

        ok(1)  # INITIALIZE
        # RGBA8, depth24, ES2, pbuffer. This also exercises the baseline's
        # window-to-pbuffer config adaptation used by the QNX Screen bridge.
        attrs = words(0x3033, 4, 0x3040, 4, 0x3024, 8, 0x3023, 8,
                      0x3022, 8, 0x3021, 8, 0x3025, 24,
                      *([0x3026, 8] if stencil else []), 0x3038)
        values, configs = ok(5, b=1, payload=attrs)
        self.assertGreater(values[0], 0)
        config, = struct.unpack(">I", configs)
        if window:
            values, _ = ok(20, config, 2, 2)  # CREATE_WINDOW_SURFACE
        else:
            values, _ = ok(7, config, payload=words(0x3057, 2, 0x3056, 2, 0x3038))
        surface = values[0]
        values, _ = ok(8, config, payload=words(0x3098, 2, 0x3038))
        ok(9, surface, surface, values[0])
        return surface


class EGLServerTests(EGLServerFixture):
    def test_initialize_and_terminate(self):
        with self.connect() as connection:
            values, _ = self.ok(connection, 1)
            self.assertGreaterEqual(values[0], 1)
            _, vendor = self.ok(connection, 3, 0x3053)  # EGL_VENDOR
            self.assertTrue(vendor.rstrip(b"\0"))
            self.ok(connection, 2)
            self.assertEqual(connection.recv(1), b"")

    def test_pbuffer_clear_and_readback(self):
        with self.connect() as connection:
            self.context(connection)
            self.ok(connection, 17, payload=struct.pack(">4f", 1, 0, 0, 1))
            self.ok(connection, 18, 0x4000)  # GL_COLOR_BUFFER_BIT
            _, pixels = self.ok(connection, 19, payload=words(0, 0, 2, 2, 0x1908, 0x1401))
            self.assertEqual(pixels, b"\xff\0\0\xff" * 4)
            self.ok(connection, 2)

    def test_gl_requires_current_context_and_reports_invalid_enum(self):
        with self.connect() as connection:
            reply, _ = self.request(connection, 18, 0x4000)
            self.assertEqual(reply[2:4], (1, 0x0502))  # GL_INVALID_OPERATION
            self.context(connection)
            reply, _ = self.request(connection, 23, 0xffffffff)  # GL_ENABLE
            self.assertEqual(reply[2:4], (1, 0x0500))  # GL_INVALID_ENUM
            self.ok(connection, 18, 0x4000)  # The previous error must not leak.
            self.ok(connection, 2)

    def test_bad_attributes_and_unknown_opcode(self):
        with self.connect() as connection:
            for opcode, payload in ((5, words(0x3033)), (0xffff, b"")):
                with self.subTest(opcode=opcode):
                    reply, _ = self.request(connection, opcode, payload=payload)
                    self.assertEqual(reply[2:4], (1, 0x300c))  # EGL_BAD_PARAMETER
            self.ok(connection, 1)
            self.ok(connection, 2)

    def test_invalid_headers_are_rejected_and_connection_closed(self):
        for options in ({"magic": b"BAD!"}, {"version": 3}, {"sequence": 0},
                        {"length": 16 * 1024 * 1024 + 1}):
            with self.subTest(options=options), self.connect() as connection:
                reply, payload = self.request(connection, 1, **options)
                self.assertEqual(reply[2:4], (1, 0x300c))
                self.assertEqual(payload, b"")
                self.assertEqual(connection.recv(1), b"")
        with self.connect() as connection:
            self.ok(connection, 1)
            self.ok(connection, 2)

    def test_truncated_frame_does_not_stop_listener(self):
        for frame in (b"I6ER", HEADER.pack(b"I6ER", 4, 5, 1, 0, 1, 0, 1, 4) + b"\0"):
            with self.subTest(frame=frame), self.connect() as connection:
                connection.sendall(frame)
                connection.shutdown(socket.SHUT_WR)
                self.assertEqual(connection.recv(1), b"")
        with self.connect() as connection:
            self.ok(connection, 1)
            self.ok(connection, 2)


class EGLStateTests(EGLServerFixture):
    """Own synthetic shaders exercise actual GLES state and rasterization."""

    def integer(self, connection, name):
        _, data = self.ok(connection, 25, name)
        return struct.unpack(">i", data)[0]

    def pixels(self, connection):
        _, data = self.ok(connection, 19, payload=words(0, 0, 2, 2, 0x1908, 0x1401))
        return data

    def triangle(self, connection):
        shaders = []
        sources = (
            (0x8b31, b"attribute vec2 position; uniform float z; void main() { gl_Position = vec4(position,z,1.0); }"),
            (0x8b30, b"precision mediump float; uniform vec4 color; void main() { gl_FragColor = color; }"),
        )
        for kind, source in sources:
            values, _ = self.ok(connection, 30, kind)
            shader = values[0]
            payload = words(len(source)) + source
            self.ok(connection, 34, shader, 1, len(payload), payload=payload)
            self.ok(connection, 39, shader)
            values, _ = self.ok(connection, 40, shader, 0x8b81)
            self.assertEqual(values[0], 1)
            shaders.append(shader)
        values, _ = self.ok(connection, 42)
        program = values[0]
        for shader in shaders:
            self.ok(connection, 44, program, shader)
        self.ok(connection, 45, program)
        values, _ = self.ok(connection, 43, program, 0x8b82)
        self.assertEqual(values[0], 1)
        self.ok(connection, 50, program)
        values, _ = self.ok(connection, 48, program, 8, payload=b"position")
        position = values[0]
        _, data = self.ok(connection, 28, 1)
        buffer, = struct.unpack(">I", data)
        self.ok(connection, 31, 0x8892, buffer)
        vertices = struct.pack("=6f", -1, -1, 3, -1, -1, 3)
        self.ok(connection, 35, 0x8892, len(vertices), 0x88e4, payload=vertices)
        self.ok(connection, 53, position, 2, 0x1406, payload=words(0, 0, 0))
        self.ok(connection, 51, position)
        self.ok(connection, 16, payload=words(0, 0, 2, 2))
        locations = []
        for name in (b"color", b"z"):
            values, _ = self.ok(connection, 49, program, len(name), payload=name)
            locations.append(values[0])
        return locations

    def draw(self, connection, locations, color, z=0):
        self.ok(connection, 64, locations[0], 1, 4, payload=struct.pack(">4f", *color))
        self.ok(connection, 64, locations[1], 1, 1, payload=struct.pack(">f", z))
        self.ok(connection, 56, 4, 0, 3)

    def test_front_back_stencil_blend_depth_and_color_state(self):
        with self.connect() as connection:
            self.context(connection, stencil=True)
            self.ok(connection, 69, 0x0404, 0x0201, 37, payload=words(0x5a))
            self.ok(connection, 69, 0x0405, 0x0206, 12, payload=words(0xa5))
            self.ok(connection, 70, 0x0404, 0x3c)
            self.ok(connection, 70, 0x0405, 0xc3)
            self.ok(connection, 71, 0x0405, 0x1e00, 0x1e02, payload=words(0x1e01))
            self.ok(connection, 72, 3)
            self.ok(connection, 73, 0x800a, 0x800b)
            self.ok(connection, 62, 0x0203)
            self.ok(connection, 63, 0)
            state = {0x0b92: 0x0201, 0x0b97: 37, 0x0b93: 0x5a, 0x0b98: 0x3c,
                     0x8800: 0x0206, 0x8ca3: 12, 0x8ca4: 0xa5, 0x8ca5: 0xc3,
                     0x8801: 0x1e00, 0x8802: 0x1e02, 0x8803: 0x1e01,
                     0x0b91: 3, 0x8009: 0x800a, 0x883d: 0x800b,
                     0x0b74: 0x0203, 0x0b72: 0}
            for name, expected in state.items():
                with self.subTest(name=hex(name)):
                    self.assertEqual(self.integer(connection, name), expected)
            self.ok(connection, 17, payload=struct.pack(">4f", 0.25, 0.5, 0.75, 1))
            _, data = self.ok(connection, 27, 0x0c22)
            self.assertEqual(struct.unpack(">4f", data), (0.25, 0.5, 0.75, 1))
            self.ok(connection, 2)

    def test_state_rejects_foreign_client_without_mutating_current_owner(self):
        with self.connect() as connection:
            self.context(connection, stencil=True)
            self.ok(connection, 72, 3)
            # Client 2 has never initialized or made a context current. The
            # dispatch thread's client-1 context does not authorize its calls.
            reply, _ = self.request(connection, 72, 11, client=2)
            self.assertEqual(reply[2:4], (1, 0x0502))
            self.assertEqual(self.integer(connection, 0x0b91), 3)
            self.ok(connection, 1, client=2)
            calls = ((69, 0x0408, 0x0201, 9, words(0x5a)),
                     (70, 0x0408, 0x3c, 0, b""),
                     (71, 0x0408, 0x1e01, 0x1e02, words(0x1e01)),
                     (72, 11, 0, 0, b""), (73, 0x800a, 0x800b, 0, b""))
            names = (0x0b92, 0x0b97, 0x0b93, 0x0b98, 0x0b94, 0x0b95,
                     0x0b96, 0x0b91, 0x8009, 0x883d)
            initial = {name: self.integer(connection, name) for name in names}
            for opcode, a, b, c, payload in calls:
                with self.subTest(opcode=opcode):
                    reply, _ = self.request(connection, opcode, a, b, c, payload, client=2)
                    self.assertEqual(reply[2:4], (1, 0x0502))
                    for name, expected in initial.items():
                        self.assertEqual(self.integer(connection, name), expected)
            self.ok(connection, 72, 5)  # Owner remains usable after refusals.
            self.assertEqual(self.integer(connection, 0x0b91), 5)
            self.ok(connection, 2)

    def test_state_owner_switch_failed_bind_unbind_and_deferred_destroy(self):
        with self.connect() as connection:
            first = self.context(connection, stencil=True)
            self.ok(connection, 72, 3)
            second = self.context(connection, stencil=True, client=2)
            self.ok(connection, 72, 11, client=2)
            reply, _ = self.request(connection, 72, 99)
            self.assertEqual(reply[2:4], (1, 0x0502))
            # A failed client-1 bind cannot steal the dispatch thread's owner.
            reply, _ = self.request(connection, 9, first, first, 999)
            self.assertEqual(reply[2:4], (1, 0x3006))
            self.ok(connection, 72, 12, client=2)
            _, data = self.ok(connection, 25, 0x0b91, client=2)
            self.assertEqual(struct.unpack(">i", data)[0], 12)
            self.ok(connection, 9, client=2)  # Successful unbind clears ownership.
            for client in (1, 2):
                reply, _ = self.request(connection, 72, 99, client=client)
                self.assertEqual(reply[2:4], (1, 0x0502))
            # Each fresh client has local context ID 1, despite distinct EGL handles.
            self.ok(connection, 9, first, first, 1)
            self.assertEqual(self.integer(connection, 0x0b91), 3)
            self.ok(connection, 11, 1)  # EGL defers destruction of a current context.
            self.ok(connection, 72, 7)
            self.assertEqual(self.integer(connection, 0x0b91), 7)
            reply, _ = self.request(connection, 9, first, first, 1)
            self.assertEqual(reply[2:4], (1, 0x3006))  # Removed public handle.
            self.ok(connection, 72, 8)  # Failed rebind keeps deferred current owner.
            self.ok(connection, 9)
            reply, _ = self.request(connection, 72, 99)
            self.assertEqual(reply[2:4], (1, 0x0502))
            self.ok(connection, 9, second, second, 1, client=2)
            self.ok(connection, 72, 13, client=2)
            self.ok(connection, 2, client=2)
        with self.connect() as connection:  # TERMINATE closes the old TCP transport.
            reply, _ = self.request(connection, 72, 99, client=2)
            self.assertEqual(reply[2:4], (1, 0x0502))
            self.ok(connection, 2)

    def test_foreign_termination_preserves_current_state_owner(self):
        with self.connect() as connection:
            self.context(connection, stencil=True)
            self.ok(connection, 72, 3)
            self.ok(connection, 1, client=2)
            self.ok(connection, 2, client=2)
        # TERMINATE closes TCP, but a new transport with client 1 keeps its
        # bound context; cleaning up client 2 must not unbind that context.
        with self.connect() as connection:
            self.ok(connection, 72, 5)
            self.assertEqual(self.integer(connection, 0x0b91), 5)
            self.ok(connection, 2)

    def test_state_payload_enum_no_context_and_recovery(self):
        valid = ((69, 0x0408, 0x0207, 0, words(0xff)),
                 (70, 0x0408, 0xff, 0, b""),
                 (71, 0x0408, 0x1e00, 0x1e00, words(0x1e00)),
                 (72, 0, 0, 0, b""), (73, 0x8006, 0x8006, 0, b""))
        with self.connect() as connection:
            for opcode, a, b, c, payload in valid:
                with self.subTest(no_context=opcode):
                    reply, _ = self.request(connection, opcode, a, b, c, payload)
                    self.assertEqual(reply[2:4], (1, 0x0502))
            self.context(connection, stencil=True)
            for opcode, a, b, c, payload in valid:
                for malformed in (b"\0", payload + words(0)):
                    with self.subTest(opcode=opcode, malformed=malformed):
                        reply, _ = self.request(connection, opcode, a, b, c, malformed)
                        self.assertEqual(reply[2:4], (1, 0x0501))
                        self.ok(connection, opcode, a, b, c, payload)
            for opcode, a, b in ((70, 0x0408, 0xff), (72, 0, 0), (73, 0x8006, 0x8006)):
                reply, _ = self.request(connection, opcode, a, b, 1)
                self.assertEqual(reply[2:4], (1, 0x0501))
            reply, _ = self.request(connection, 72, 0, 1)
            self.assertEqual(reply[2:4], (1, 0x0501))
            for opcode, a, b, c, payload in valid:
                if opcode == 72:
                    continue
                reply, _ = self.request(connection, opcode, 0xdead, b, c, payload)
                self.assertEqual(reply[2:4], (1, 0x0500))
                self.ok(connection, opcode, a, b, c, payload)
            self.ok(connection, 72, 0xffffffff)
            self.assertEqual(self.integer(connection, 0x0b91), -1)
            self.ok(connection, 18, 0x4000)
            self.ok(connection, 2)

    def test_stencil_masks_clear_operations_and_depth_change_real_pixels(self):
        with self.connect() as connection:
            self.context(connection, stencil=True)
            locations = self.triangle(connection)
            self.ok(connection, 17, payload=struct.pack(">4f", 0, 0, 0, 1))
            self.ok(connection, 72, 0)
            self.ok(connection, 18, 0x4000 | 0x0400 | 0x0100)
            self.ok(connection, 23, 0x0b90)
            self.ok(connection, 69, 0x0408, 0x0202, 1, payload=words(0xff))
            self.draw(connection, locations, (1, 0, 0, 1))
            self.assertEqual(self.pixels(connection), b"\0\0\0\xff" * 4)
            # Masked clear writes only bit 0, so the stencil becomes 1, not 3.
            self.ok(connection, 70, 0x0408, 1)
            self.ok(connection, 72, 3)
            self.ok(connection, 18, 0x0400)
            self.draw(connection, locations, (1, 0, 0, 1))
            self.assertEqual(self.pixels(connection), b"\xff\0\0\xff" * 4)
            self.ok(connection, 70, 0x0408, 0xff)
            self.ok(connection, 69, 0x0408, 0x0207, 2, payload=words(0xff))
            self.ok(connection, 71, 0x0408, 0x1e00, 0x1e00, payload=words(0x1e01))
            self.draw(connection, locations, (0, 1, 0, 1))
            self.ok(connection, 69, 0x0408, 0x0202, 1, payload=words(0xff))
            self.draw(connection, locations, (0, 0, 1, 1))
            self.assertEqual(self.pixels(connection), b"\0\xff\0\xff" * 4)
            self.ok(connection, 69, 0x0408, 0x0202, 2, payload=words(0xff))
            self.ok(connection, 71, 0x0408, 0x1e00, 0x1e00, payload=words(0x1e00))
            self.draw(connection, locations, (0, 0, 1, 1))
            self.assertEqual(self.pixels(connection), b"\0\0\xff\xff" * 4)
            self.ok(connection, 24, 0x0b90)
            self.ok(connection, 23, 0x0b71)
            self.ok(connection, 62, 0x0201)
            self.draw(connection, locations, (1, 0, 0, 1), z=0)
            self.draw(connection, locations, (0, 1, 0, 1), z=0.5)
            self.assertEqual(self.pixels(connection), b"\xff\0\0\xff" * 4)
            self.ok(connection, 63, 0)
            self.draw(connection, locations, (0, 0, 1, 1), z=-0.5)
            self.draw(connection, locations, (0, 1, 0, 1), z=-0.25)
            self.assertEqual(self.pixels(connection), b"\0\xff\0\xff" * 4)
            self.ok(connection, 2)

    def test_separate_blend_equations_change_real_rgba_pixels(self):
        with self.connect() as connection:
            self.context(connection)
            locations = self.triangle(connection)
            self.ok(connection, 17, payload=struct.pack(">4f", 0.25, 0.5, 0.75, 0.75))
            self.ok(connection, 18, 0x4000)
            self.ok(connection, 23, 0x0be2)
            self.ok(connection, 59, 1, 1, 1, payload=words(1))
            self.ok(connection, 73, 0x800a, 0x800b)
            self.draw(connection, locations, (0.75, 0.75, 1, 0.25))
            pixels = self.pixels(connection)
            for pixel in range(4):
                for actual, expected in zip(pixels[pixel * 4:pixel * 4 + 4], (128, 64, 64, 128)):
                    self.assertLessEqual(abs(actual - expected), 2)
            self.ok(connection, 2)


class EGLShaderMapTests(EGLServerFixture):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="idrive-shader-test-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.marker = b"synthetic host-test shader identifier, not native firmware"
        self.native = root / "synthetic.shader"
        self.source = root / "synthetic.vert"
        self.native.write_bytes(self.marker)
        self.source.write_text("#version 300 es\nvoid main() { gl_Position = vec4(0.0, 0.0, 0.0, 1.0); }\n")
        super().setUp()

    def start_server(self, arguments, extra_environment=None):
        super().start_server([*arguments, "--shader-map", str(self.native), str(self.source)],
                             extra_environment)

    def test_essl300_map_promotes_es2_request_and_compiles_synthetic_shader(self):
        with self.connect() as connection:
            self.context(connection)  # Requests ES2, as the baseline QNX provider does.
            _, version = self.ok(connection, 14, 0x1f02)  # GL_VERSION
            self.assertTrue(version.startswith(b"OpenGL ES 3."), version)
            values, _ = self.ok(connection, 30, 0x8b31)  # GL_VERTEX_SHADER
            shader = values[0]
            self.ok(connection, 33, 1, 0, len(self.marker), payload=words(shader) + self.marker)
            values, _ = self.ok(connection, 40, shader, 0x8b81)  # GL_COMPILE_STATUS
            self.assertEqual(values[0], 1)
            self.ok(connection, 2)
        self.log.seek(0)
        self.assertIn(b"ANGLE_CONTEXT_GLES3_PROMOTION reason=essl300-shader-map", self.log.read())


@unittest.skipUnless(platform.system() == "Linux" and platform.machine() == "x86_64",
                     "mailbox fixture uses x86_64 aligned native-word memory ordering")
class EGLMailboxTests(EGLServerFixture):
    """Exercise the release transport with real shared mappings, not TCP."""
    MAILBOX_BYTES = 17 * 1024 * 1024
    FRAME_OFFSET = 64
    IDLE, REQUEST, RESPONSE, FAILED = 0, 2, 4, 5

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="idrive-mailbox-test-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        mailbox = root / "mailbox"
        self.ram = root / "guest-ram"
        with mailbox.open("w+b") as stream:
            stream.truncate(self.MAILBOX_BYTES)
            self.mapping = mmap.mmap(stream.fileno(), self.MAILBOX_BYTES)
        self.addCleanup(self.mapping.close)
        self.ram.write_bytes(b"\xa5" * 4096)
        self.start_server(["--mailbox-file", str(mailbox), "--guest-ram-file", str(self.ram)], {
            "IDRIVE_ANGLE_EGL_BATCH": "1",
            "IDRIVE_ANGLE_EGL_IMMEDIATE_POST": "1",
            "IDRIVE_ANGLE_EGL_FAST_WAIT": "1",
        })
        self.wait_word(0, 0x424d3649)  # READY magic, published after features.
        self.assertEqual(self.word(4), self.IDLE)
        self.assertEqual(self.word(8), 1 | 2 | 8 | 16)

    def word(self, offset, value=None):
        # Native aligned 32-bit loads/stores are atomic on x86_64. Its store
        # ordering publishes frame bytes before REQUEST, and reading RESPONSE
        # observes the server's preceding frame writes. Do not use this fixture
        # as an implementation of the guest's atomics on other architectures.
        word = ctypes.c_uint32.from_buffer(self.mapping, offset)
        if value is not None:
            word.value = value
        return word.value

    def wait_word(self, offset, expected):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.word(offset) == expected:
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.001)
        self.log.seek(0)
        self.fail(f"mailbox word {offset} did not reach {expected}:\n" +
                  self.log.read().decode(errors="replace"))

    def publish(self, frame):
        self.assertEqual(self.word(4), self.IDLE)
        self.assertLessEqual(len(frame), self.MAILBOX_BYTES - self.FRAME_OFFSET)
        self.mapping[self.FRAME_OFFSET:self.FRAME_OFFSET + len(frame)] = frame
        self.word(4, self.REQUEST)

    def request(self, connection, opcode, a=0, b=0, c=0, payload=b"", *, client=1):
        self.sequence += 1
        self.publish(HEADER.pack(b"I6ER", 4, opcode, client, a, b, c, self.sequence, len(payload)) + payload)
        self.wait_word(4, self.RESPONSE)
        reply = HEADER.unpack_from(self.mapping, self.FRAME_OFFSET)
        self.assertEqual(reply[:2], (b"I6EA", 4))
        self.assertEqual(reply[-1], self.sequence)
        self.assertLessEqual(reply[-2], 16 * 1024 * 1024)
        start = self.FRAME_OFFSET + HEADER.size
        data = self.mapping[start:start + reply[-2]]
        self.word(4, self.IDLE)
        return reply, data

    def test_window_swap_writes_shared_ram_and_rejects_out_of_bounds(self):
        surface = self.context(None, window=True)
        self.ok(None, 17, payload=struct.pack(">4f", 1, 0, 0, 1))
        self.ok(None, 18, 0x4000)
        _, pixels = self.ok(None, 19, payload=words(0, 0, 2, 2, 0x1908, 0x1401))
        self.assertEqual(pixels, b"\xff\0\0\xff" * 4)
        # QNX Screen presents to shared physical RAM, not an RPC pixel payload.
        # Check BGRA conversion, row padding, offset and guard bytes on disk.
        values, data = self.ok(None, 21, surface, 2, 2, payload=words(12, 8, 0x80000040, 0))
        self.assertEqual(values[2], 24)
        self.assertEqual(data, b"")
        frame = (b"\0\0\xff\xff" * 2 + b"\0" * 4) * 2
        expected = b"\xa5" * 64 + frame + b"\xa5" * (4096 - 64 - len(frame))
        self.assertEqual(self.ram.read_bytes(), expected)
        for stride, address in ((7, 0x80000040), (12, 0x80000ff0), (12, 0x7fffffff)):
            with self.subTest(stride=stride, address=address):
                reply, _ = self.request(None, 21, surface, 2, 2, payload=words(stride, 8, address, 0))
                self.assertEqual(reply[2:4], (1, 0x300c))  # EGL_BAD_PARAMETER
                self.assertEqual(self.ram.read_bytes(), expected)
        self.ok(None, 2)

    def test_batch_clear_readback_and_error_recovery(self):
        reply, _ = self.request(None, 18, 0x4000)
        self.assertEqual(reply[2:4], (1, 0x0502))  # No current context.
        self.context(None)
        self.ok(None, 17, payload=struct.pack(">4f", 0, 1, 0, 1))
        viewport = HEADER.pack(b"I6ER", 4, 16, 1, 0, 0, 0, 101, 16) + words(0, 0, 2, 2)
        clear = HEADER.pack(b"I6ER", 4, 18, 1, 0x4000, 0, 0, 102, 0)
        values, _ = self.ok(None, 68, payload=viewport + clear)
        self.assertEqual(values[0], 0)
        _, pixels = self.ok(None, 19, payload=words(0, 0, 2, 2, 0x1908, 0x1401))
        self.assertEqual(pixels, b"\0\xff\0\xff" * 4)
        invalid_enum = HEADER.pack(b"I6ER", 4, 23, 1, 0xffffffff, 0, 0, 103, 0)
        values, _ = self.ok(None, 68, payload=invalid_enum)
        self.assertEqual(values[0], 0x0500)  # Batch reports the first GL error.
        wrong_client = HEADER.pack(b"I6ER", 4, 18, 2, 0x4000, 0, 0, 104, 0)
        reply, _ = self.request(None, 68, payload=wrong_client)
        self.assertEqual(reply[2:4], (1, 0x300c))
        values, _ = self.ok(None, 68, payload=clear)
        self.assertEqual(values[0], 0)  # Neither error poisoned the mailbox.
        self.ok(None, 2)

    def test_state_roundtrip_and_nested_version_rejection(self):
        self.context(None, stencil=True)
        self.ok(None, 69, 0x0408, 0x0202, 7, payload=words(0x5a))
        self.ok(None, 70, 0x0408, 0x3c)
        self.ok(None, 71, 0x0408, 0x1e00, 0x1e02, payload=words(0x1e01))
        self.ok(None, 72, 3)
        self.ok(None, 73, 0x800a, 0x800b)
        for name, expected in ((0x0b97, 7), (0x8ca3, 7), (0x0b98, 0x3c),
                               (0x0b96, 0x1e01), (0x0b91, 3),
                               (0x8009, 0x800a), (0x883d, 0x800b)):
            _, data = self.ok(None, 25, name)
            self.assertEqual(struct.unpack(">I", data)[0], expected)
        old_clear = HEADER.pack(b"I6ER", 3, 18, 1, 0x4000, 0, 0, 101, 0)
        reply, _ = self.request(None, 68, payload=old_clear)
        self.assertEqual(reply[2:4], (1, 0x300c))
        # New state calls deliberately remain synchronous/non-batchable.
        state = HEADER.pack(b"I6ER", 4, 72, 1, 11, 0, 0, 102, 0)
        reply, _ = self.request(None, 68, payload=state)
        self.assertEqual(reply[2:4], (1, 0x300c))
        _, data = self.ok(None, 25, 0x0b91)
        self.assertEqual(struct.unpack(">I", data)[0], 3)
        self.ok(None, 18, 0x4000)
        self.assertEqual(self.ram.read_bytes(), b"\xa5" * 4096)
        self.ok(None, 2)

    def test_version_three_header_fails_mailbox_without_touching_ram(self):
        self.publish(HEADER.pack(b"I6ER", 3, 1, 1, 0, 0, 0, 1, 0))
        self.wait_word(4, self.FAILED)
        self.assertEqual(self.process.wait(timeout=5), 1)
        self.assertEqual(self.ram.read_bytes(), b"\xa5" * 4096)
        self.log.seek(0)
        self.assertIn(b"ANGLE_EGL_MAILBOX_FAIL stage=request-header", self.log.read())


if __name__ == "__main__":
    unittest.main()
