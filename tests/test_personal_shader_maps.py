"""Host-only tests: real map validator, synthetic native payloads, own GLSL.

No firmware or recorded vendor payload is opened. Synthetic payload pins replace
ONLY native-input hashes in disposable manifests; shipped ESSL pins stay intact.
"""
import copy
import ctypes as C
import ctypes.util
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = Path('tools/shaders/native-reconstructions')
VALIDATOR = ROOT / 'tools/prepare-hmi-native-essl-map.py'
MAPS = {stage: json.loads((ROOT / MAP_DIR / f'hmi-linux-native-{stage}-v1.json').read_text())
        for stage in ('vertex', 'fragment')}


class MapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='own-shader-map-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.rootfs = self.base / 'rootfs'
        self.manifest = self.base / 'map.json'

    def fixture(self, stage='vertex'):
        data = copy.deepcopy(MAPS[stage])
        for row in data['mappings']:
            payload = ('SYNTHETIC HOST TEST ONLY:' + row['asset_path']).encode()
            asset = self.rootfs / 'opt/hmi/ID5/data/ro' / row['asset_path']
            asset.parent.mkdir(parents=True, exist_ok=True)
            asset.write_bytes(payload)
            row['shader_sha256'] = hashlib.sha256(payload).hexdigest()
            source = self.repo / row['source_path']
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes((ROOT / row['source_path']).read_bytes())
        return data

    def validate(self, data):
        self.manifest.write_text(json.dumps(data))
        return subprocess.run([sys.executable, str(VALIDATOR), str(self.manifest),
                               str(self.rootfs), str(self.repo)],
                              capture_output=True, text=True)

    def test_complete_maps_use_real_reader(self):
        for stage, count in [('vertex', 34), ('fragment', 36)]:
            with self.subTest(stage=stage):
                result = self.validate(self.fixture(stage))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(result.stdout.splitlines()), count)
                self.assertIn(f'validated {count} exact HMI {stage}', result.stderr)

    def test_all_shipped_source_pins_and_portable_paths(self):
        spec = importlib.util.spec_from_file_location('actual_map_reader', VALIDATOR)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        for data in MAPS.values():
            hashes = set()
            for row in data['mappings']:
                for field in ('source_path', 'asset_path'):
                    reader.safe_relative(row[field], field)
                self.assertEqual(hashlib.sha256((ROOT / row['source_path']).read_bytes()).hexdigest(),
                                 row['source_essl_sha256'])
                if row.get('shader_sha256'):
                    self.assertNotIn(row['shader_sha256'], hashes)
                    hashes.add(row['shader_sha256'])

    def test_native_pin_fails_closed_without_partial_output(self):
        data = self.fixture()
        row = data['mappings'][-1]
        (self.rootfs / 'opt/hmi/ID5/data/ro' / row['asset_path']).write_bytes(b'wrong synthetic')
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('staged HMI shader hash changed', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_source_pin_fails_closed(self):
        data = self.fixture('fragment')
        (self.repo / data['mappings'][-1]['source_path']).write_text('void main() {}')
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('reconstructed ESSL hash changed', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_missing_source_fails_closed(self):
        data = self.fixture()
        data['mappings'][-1]['source_path'] = 'missing-own-source.glsl'
        result = self.validate(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('reconstructed shader source is missing', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_unsafe_paths_rejected(self):
        for field in ('source_path', 'asset_path'):
            for value in ('../escape', '/absolute', 'bad\tpath', 'bad\npath'):
                with self.subTest(field=field, value=value):
                    data = self.fixture()
                    data['mappings'][0][field] = value
                    result = self.validate(data)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('unsafe', result.stderr)
                    self.assertEqual(result.stdout, '')

    def test_cross_stage_delta_rejected(self):
        data = self.fixture()
        base = self.repo / 'base.json'
        base.write_text(json.dumps(data))
        delta = {'schema': 'idrive6-hmi-exact-fragment-map-delta-v1',
                 'base_manifest': 'base.json',
                 'base_manifest_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
                 'replacements': [data['mappings'][0]]}
        result = self.validate(delta)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('same shader stage', result.stderr)


class HostGlesTests(unittest.TestCase):
    """Optional existing system Mesa, surfaceless ES3; no server or VM."""
    def test_compile_and_link_own_pairs(self):
        egl_name, gl_name = C.util.find_library('EGL'), C.util.find_library('GLESv2')
        if not egl_name or not gl_name:
            self.skipTest('existing host EGL/GLES libraries unavailable')
        # Software-only host context; never touches a guest or physical HU.
        old_software = os.environ.get('LIBGL_ALWAYS_SOFTWARE')
        def restore_environment():
            if old_software is None:
                os.environ.pop('LIBGL_ALWAYS_SOFTWARE', None)
            else:
                os.environ['LIBGL_ALWAYS_SOFTWARE'] = old_software
        self.addCleanup(restore_environment)
        os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'
        egl, gl = C.CDLL(egl_name), C.CDLL(gl_name)
        def bind(lib, name, restype, args):
            fn = getattr(lib, name)
            fn.restype, fn.argtypes = restype, args
            return fn
        ptr, integer, uint = C.c_void_p, C.c_int, C.c_uint
        platform = bind(egl, 'eglGetPlatformDisplay', ptr, [uint, ptr, C.POINTER(integer)])
        display = platform(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
        initialize = bind(egl, 'eglInitialize', uint, [ptr, C.POINTER(integer), C.POINTER(integer)])
        if not initialize(display, None, None):
            self.skipTest('existing host surfaceless EGL unavailable')
        terminate = bind(egl, 'eglTerminate', uint, [ptr])
        self.addCleanup(terminate, display)
        self.assertTrue(bind(egl, 'eglBindAPI', uint, [uint])(0x30A0))
        attrs = (integer * 9)(0x3033, 1, 0x3040, 0x40, 0x3024, 8, 0x3025, 8, 0x3038)
        config, count = ptr(), integer()
        self.assertTrue(bind(egl, 'eglChooseConfig', uint,
                             [ptr, C.POINTER(integer), C.POINTER(ptr), integer, C.POINTER(integer)])
                        (display, attrs, C.byref(config), 1, C.byref(count)))
        self.assertGreater(count.value, 0)
        context = bind(egl, 'eglCreateContext', ptr, [ptr, ptr, ptr, C.POINTER(integer)])(
            display, config, None, (integer * 3)(0x3098, 3, 0x3038))
        self.assertTrue(context)
        destroy = bind(egl, 'eglDestroyContext', uint, [ptr, ptr])
        self.addCleanup(destroy, display, context)
        current = bind(egl, 'eglMakeCurrent', uint, [ptr, ptr, ptr, ptr])
        self.assertTrue(current(display, None, None, context))
        self.addCleanup(current, display, None, None, None)
        create = bind(gl, 'glCreateShader', uint, [uint])
        source = bind(gl, 'glShaderSource', None, [uint, integer, C.POINTER(C.c_char_p), C.POINTER(integer)])
        compile_shader = bind(gl, 'glCompileShader', None, [uint])
        shader_iv = bind(gl, 'glGetShaderiv', None, [uint, uint, C.POINTER(integer)])
        shader_log = bind(gl, 'glGetShaderInfoLog', None, [uint, integer, C.POINTER(integer), C.c_char_p])
        delete_shader = bind(gl, 'glDeleteShader', None, [uint])
        create_program = bind(gl, 'glCreateProgram', uint, [])
        attach = bind(gl, 'glAttachShader', None, [uint, uint])
        link = bind(gl, 'glLinkProgram', None, [uint])
        program_iv = bind(gl, 'glGetProgramiv', None, [uint, uint, C.POINTER(integer)])
        program_log = bind(gl, 'glGetProgramInfoLog', None, [uint, integer, C.POINTER(integer), C.c_char_p])
        delete_program = bind(gl, 'glDeleteProgram', None, [uint])
        output_location = bind(gl, 'glGetFragDataLocation', integer, [uint, C.c_char_p])
        compiled = {}
        def shader(path, stage):
            if path in compiled:
                return compiled[path]
            obj = create(stage)
            self.addCleanup(delete_shader, obj)
            text = C.c_char_p((ROOT / path).read_bytes())
            source(obj, 1, C.byref(text), None)
            compile_shader(obj)
            ok, log = integer(), C.create_string_buffer(8192)
            shader_iv(obj, 0x8B81, C.byref(ok))
            shader_log(obj, len(log), None, log)
            self.assertTrue(ok.value, f'{path}: {log.value.decode()}')
            compiled[path] = obj
            return obj
        fresh = MAP_DIR / 'native-linux-v1'
        pairs = [
            (fresh / 'Text_ColorFading_vertex_fadeVertical_uv_projection.glsl', fresh / 'Text_fragment_fade_nativeB.glsl'),
            (fresh / 'Image_vertex_fadeVertical.glsl', fresh / 'Image_fragment_fade.glsl'),
            (fresh / 'Image_vertex_fadeVertical.glsl', fresh / 'ImageLuminanceAlpha_fragment.glsl'),
            (MAP_DIR / 'hmi-vertex/66a41b5e9c5848b1.glsl', fresh / 'MatLine_fragment_nativeB.glsl'),
        ]
        for vertex, fragment in pairs:
            with self.subTest(fragment=fragment.name):
                program = create_program()
                self.addCleanup(delete_program, program)
                attach(program, shader(vertex, 0x8B31))
                attach(program, shader(fragment, 0x8B30))
                link(program)
                ok, log = integer(), C.create_string_buffer(8192)
                program_iv(program, 0x8B82, C.byref(ok))
                program_log(program, len(log), None, log)
                self.assertTrue(ok.value, log.value.decode())
                self.assertEqual(output_location(program, b'bmwFragmentColor'), 0)


if __name__ == '__main__':
    unittest.main()
