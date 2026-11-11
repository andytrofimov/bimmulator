"""Compile the production state serializer with a recording transport seam.

Complements test_egl_rpc_server's real GLES rasterization tests; this is not
QNX ABI, packaging, or native-runtime evidence. No firmware/SDK is used.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EGLProviderStateTests(unittest.TestCase):
    def test_production_c_state_serialization_aliases_and_pending_errors(self):
        compiler = os.environ.get("CXX", "cc")
        if not shutil.which(compiler):
            self.skipTest("a host C compiler is required for the production serializer check")
        source = (ROOT / "tools/qnx-angle-egl-provider.c").read_text()
        start = source.index("/* Real stencil/blend state forwarding.")
        end = source.index("void glGetBooleanv", start)
        state_functions = source[start:end]
        result_start = source.index("struct RpcResult {")
        result_end = source.index("};", result_start) + 2
        prelude = r'''
#include <assert.h>
#include <string.h>
#include "angle-egl-rpc.h"
#define EGL_NO_CONTEXT 0
#define GL_NO_ERROR 0
#define GL_INVALID_OPERATION 0x0502
static unsigned int g_current_context, g_gl_error;
static unsigned int calls, opcode, a, b, c, bytes, wire_error;
static unsigned char wire[4];
static int success = 1;
'''
        transport = r'''
static int rpc(unsigned int op, unsigned int x, unsigned int y,
               unsigned int z, const unsigned char *payload,
               unsigned int size, struct RpcResult *reply)
{
    assert(size <= sizeof(wire));
    ++calls; opcode = op; a = x; b = y; c = z; bytes = size;
    if (size) memcpy(wire, payload, size);
    memset(reply, 0, sizeof(*reply));
    reply->error = wire_error;
    return success;
}
'''
        checks = r'''
int main(void)
{
    assert(IDRIVE_ANGLE_EGL_RPC_VERSION == 4);
    for (unsigned int op = 69; op <= 73; ++op)
        assert(!idrive_angle_egl_rpc_batchable(op));
    glStencilFuncSeparate(0x0404, 0x0201, -2, 0x12345678);
    glStencilMaskSeparate(0x0405, 0x87654321);
    glStencilOpSeparate(0x0408, 0x1e00, 0x1e02, 0x1e01);
    glClearStencil(-3); glBlendEquationSeparate(0x800a, 0x800b);
    assert(calls == 0 && g_gl_error == GL_INVALID_OPERATION);
    g_gl_error = 0x0501;
    glClearStencil(0);
    assert(calls == 0 && g_gl_error == 0x0501);
    g_current_context = 1; g_gl_error = 0;
    glStencilFuncSeparate(0x0404, 0x0201, -2, 0x12345678);
    assert(opcode == 69 && a == 0x0404 && b == 0x0201 && c == 0xfffffffe);
    assert(bytes == 4 && memcmp(wire, "\x12\x34\x56\x78", 4) == 0);
    glStencilMaskSeparate(0x0405, 0x87654321);
    assert(opcode == 70 && a == 0x0405 && b == 0x87654321 && !c && !bytes);
    glStencilOpSeparate(0x0405, 0x1e00, 0x1e02, 0x1e01);
    assert(opcode == 71 && a == 0x0405 && b == 0x1e00 && c == 0x1e02);
    assert(bytes == 4 && memcmp(wire, "\0\0\x1e\x01", 4) == 0);
    glClearStencil(-3);
    assert(opcode == 72 && a == 0xfffffffd && !b && !c && !bytes);
    glBlendEquationSeparate(0x800a, 0x800b);
    assert(opcode == 73 && a == 0x800a && b == 0x800b && !c && !bytes);
    glStencilFunc(0x0207, -1, 0xa5a5a5a5);
    assert(opcode == 69 && a == 0x0408 && b == 0x0207 && c == 0xffffffff);
    assert(idrive_angle_egl_rpc_u32(wire) == 0xa5a5a5a5);
    glStencilMask(0x5a);
    assert(opcode == 70 && a == 0x0408 && b == 0x5a);
    glStencilOp(0x1e00, 0x1e02, 0x1e01);
    assert(opcode == 71 && a == 0x0408 && b == 0x1e00 && c == 0x1e02);
    assert(idrive_angle_egl_rpc_u32(wire) == 0x1e01);
    glBlendEquation(0x8006);
    assert(opcode == 73 && a == 0x8006 && b == 0x8006);
    assert(!g_gl_error);
    success = 0; wire_error = 0x0500;
    glStencilMaskSeparate(0xdead, 0xff);
    assert(g_gl_error == 0x0500);
    success = 1;
    glClearStencil(3);
    assert(g_gl_error == 0x0500); /* Successful RPC cannot erase first error. */
    success = 0; wire_error = 0x0501;
    glClearStencil(3);
    assert(g_gl_error == 0x0500); /* Later failure cannot replace first error. */
    g_gl_error = 0; wire_error = 0;
    glClearStencil(3);
    assert(g_gl_error == GL_INVALID_OPERATION); /* Transport failure fallback. */
    g_gl_error = 0; success = 1;
    glClearStencil(3);
    assert(!g_gl_error);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="idrive-provider-state-") as directory:
            path = Path(directory)
            program = path / "state.c"
            program.write_text(prelude + source[result_start:result_end] + transport +
                               state_functions + checks)
            executable = path / "state"
            result = subprocess.run(
                [compiler, "-x", "c", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I", str(ROOT / "tools"), str(program), "-o", str(executable)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
