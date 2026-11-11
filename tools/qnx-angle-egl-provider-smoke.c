/* Exercises the QNX public EGL/GLES frontends with the host-ANGLE provider. */
typedef int EGLint;
typedef unsigned int EGLBoolean;
typedef unsigned int EGLenum;
typedef void *EGLDisplay;
typedef void *EGLConfig;
typedef void *EGLSurface;
typedef void *EGLContext;

extern EGLDisplay eglGetDisplay(void *);
extern EGLBoolean eglInitialize(EGLDisplay, EGLint *, EGLint *);
extern EGLBoolean eglTerminate(EGLDisplay);
extern const char *eglQueryString(EGLDisplay, EGLint);
extern EGLBoolean eglChooseConfig(EGLDisplay, const EGLint *, EGLConfig *, EGLint, EGLint *);
extern EGLBoolean eglGetConfigAttrib(EGLDisplay, EGLConfig, EGLint, EGLint *);
extern EGLBoolean eglBindAPI(EGLenum);
extern EGLSurface eglCreatePbufferSurface(EGLDisplay, EGLConfig, const EGLint *);
extern EGLBoolean eglDestroySurface(EGLDisplay, EGLSurface);
extern EGLContext eglCreateContext(EGLDisplay, EGLConfig, EGLContext, const EGLint *);
extern EGLBoolean eglDestroyContext(EGLDisplay, EGLContext);
extern EGLBoolean eglMakeCurrent(EGLDisplay, EGLSurface, EGLSurface, EGLContext);
extern EGLBoolean eglQueryContext(EGLDisplay, EGLContext, EGLint, EGLint *);
extern EGLBoolean eglQuerySurface(EGLDisplay, EGLSurface, EGLint, EGLint *);
extern EGLBoolean eglSwapBuffers(EGLDisplay, EGLSurface);
extern EGLint eglGetError(void);
extern EGLContext eglGetCurrentContext(void);
extern EGLDisplay eglGetCurrentDisplay(void);
extern const unsigned char *glGetString(unsigned int);
extern unsigned int glGetError(void);
extern void glGetIntegerv(unsigned int, int *);
extern void glStencilFuncSeparate(unsigned int, unsigned int, int, unsigned int);
extern void glStencilMaskSeparate(unsigned int, unsigned int);
extern void glStencilOpSeparate(unsigned int, unsigned int, unsigned int, unsigned int);
extern void glStencilFunc(unsigned int, int, unsigned int);
extern void glStencilMask(unsigned int);
extern void glStencilOp(unsigned int, unsigned int, unsigned int);
extern void glClearStencil(int);
extern void glBlendEquationSeparate(unsigned int, unsigned int);
extern void glBlendEquation(unsigned int);
extern void glViewport(int, int, int, int);
extern void glClearColor(float, float, float, float);
extern void glClear(unsigned int);
extern void glReadPixels(int, int, int, int, unsigned int, unsigned int, void *);
extern int puts(const char *);
extern int fflush(void *);
extern void _exit(int);

enum {
    EGL_FALSE = 0,
    EGL_TRUE = 1,
    EGL_SUCCESS = 0x3000,
    EGL_VENDOR = 0x3053,
    EGL_VERSION = 0x3054,
    EGL_CONFIG_ID = 0x3028,
    EGL_RED_SIZE = 0x3024,
    EGL_GREEN_SIZE = 0x3023,
    EGL_BLUE_SIZE = 0x3022,
    EGL_ALPHA_SIZE = 0x3021,
    EGL_DEPTH_SIZE = 0x3025,
    EGL_SURFACE_TYPE = 0x3033,
    EGL_RENDERABLE_TYPE = 0x3040,
    EGL_WIDTH = 0x3057,
    EGL_HEIGHT = 0x3056,
    EGL_CONTEXT_CLIENT_TYPE = 0x3097,
    EGL_CONTEXT_CLIENT_VERSION = 0x3098,
    EGL_OPENGL_ES_API = 0x30a0,
    EGL_PBUFFER_BIT = 0x0001,
    EGL_OPENGL_ES2_BIT = 0x0004,
    EGL_NONE = 0x3038,
    GL_VERSION = 0x1f02,
    GL_COLOR_BUFFER_BIT = 0x00004000,
    GL_RGBA = 0x1908,
    GL_UNSIGNED_BYTE = 0x1401,
    GL_NO_ERROR = 0
};

static void print_hex(const char *label, unsigned int value)
{
    static const char digits[] = "0123456789abcdef";
    char out[64];
    unsigned int i = 0;
    while (label[i] && i < 40) { out[i] = label[i]; i++; }
    out[i++] = '='; out[i++] = '0'; out[i++] = 'x';
    for (int shift = 28; shift >= 0; shift -= 4) out[i++] = digits[(value >> shift) & 15];
    out[i] = '\0';
    puts(out);
}

__attribute__((noreturn)) static void finish(int status)
{
    fflush((void *)0);
    _exit(status);
    for (;;) { }
}

__attribute__((noreturn)) static void fail(const char *stage)
{
    puts(stage);
    print_hex("EGL error", (unsigned int)eglGetError());
    finish(1);
}

void _start(void)
{
    EGLint major = 0, minor = 0, count = 0, depth = 0;
    EGLint client_type = 0, client_version = 0, width = 0, height = 0;
    EGLConfig config = (EGLConfig)0;
    EGLDisplay display = eglGetDisplay((void *)0);
    if (!display) fail("ANGLE EGL provider smoke: eglGetDisplay failed");
    if (!eglInitialize(display, &major, &minor)) fail("ANGLE EGL provider smoke: eglInitialize failed");
    if (!eglBindAPI(EGL_OPENGL_ES_API)) fail("ANGLE EGL provider smoke: eglBindAPI failed");
    puts("ANGLE EGL provider smoke: initialized host-backed display");
    print_hex("EGL major", (unsigned int)major);
    print_hex("EGL minor", (unsigned int)minor);
    puts(eglQueryString(display, EGL_VENDOR));
    puts(eglQueryString(display, EGL_VERSION));

    static const EGLint config_attributes[] = {
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8,
        EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
        EGL_DEPTH_SIZE, 24, 0x3026 /* EGL_STENCIL_SIZE */, 8, EGL_NONE
    };
    if (!eglChooseConfig(display, config_attributes, &config, 1, &count) || count != 1)
        fail("ANGLE EGL provider smoke: eglChooseConfig failed");
    if (!eglGetConfigAttrib(display, config, EGL_DEPTH_SIZE, &depth) || depth < 24)
        fail("ANGLE EGL provider smoke: depth24 config missing");
    print_hex("EGL depth bits", (unsigned int)depth);

    static const EGLint surface_attributes[] = { EGL_WIDTH, 64, EGL_HEIGHT, 64, EGL_NONE };
    EGLSurface surface = eglCreatePbufferSurface(display, config, surface_attributes);
    if (!surface) fail("ANGLE EGL provider smoke: eglCreatePbufferSurface failed");
    static const EGLint context_attributes[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    EGLContext context = eglCreateContext(display, config, (EGLContext)0, context_attributes);
    if (!context) fail("ANGLE EGL provider smoke: eglCreateContext failed");
    if (!eglMakeCurrent(display, surface, surface, context))
        fail("ANGLE EGL provider smoke: eglMakeCurrent failed");
    if (eglGetCurrentContext() != context || eglGetCurrentDisplay() != display)
        fail("ANGLE EGL provider smoke: QNX current-context state mismatch");
    if (!eglQueryContext(display, context, EGL_CONTEXT_CLIENT_TYPE, &client_type))
        fail("ANGLE EGL provider smoke: client type query failed");
    if (!eglQueryContext(display, context, EGL_CONTEXT_CLIENT_VERSION, &client_version))
        fail("ANGLE EGL provider smoke: client version query failed");
    print_hex("EGL context client type", (unsigned int)client_type);
    print_hex("EGL context client version", (unsigned int)client_version);
    if (client_type != EGL_OPENGL_ES_API || client_version < 2)
        fail("ANGLE EGL provider smoke: context query mismatch");
    if (!eglQuerySurface(display, surface, EGL_WIDTH, &width) || width != 64 ||
        !eglQuerySurface(display, surface, EGL_HEIGHT, &height) || height != 64)
        fail("ANGLE EGL provider smoke: pbuffer query mismatch");

    const unsigned char *version = glGetString(GL_VERSION);
    static const char prefix[] = "OpenGL ES ";
    for (unsigned int i = 0; i < sizeof(prefix) - 1; ++i)
        if (!version || version[i] != (unsigned char)prefix[i])
            fail("ANGLE EGL provider smoke: QNX GLES table/version check failed");
    puts("QNX GLES GL_VERSION:");
    puts((const char *)version);
    int actual_state = 0;
    glStencilFuncSeparate(0x0404, 0x0201, 37, 0x5a);
    glStencilFuncSeparate(0x0405, 0x0206, 12, 0xa5);
    glStencilMaskSeparate(0x0404, 0x3c);
    glStencilMaskSeparate(0x0405, 0xc3);
    glStencilOpSeparate(0x0405, 0x1e00, 0x1e02, 0x1e01);
    glClearStencil(3);
    glBlendEquationSeparate(0x800a, 0x800b);
    static const unsigned int state_names[] = {0x0b92,0x0b97,0x0b93,0x0b98,0x8800,
                                       0x8ca3,0x8ca4,0x8ca5,0x8801,0x8802,0x8803,
                                       0x0b91,0x8009,0x883d};
    static const int state_values[] = {0x0201,37,0x5a,0x3c,0x0206,12,0xa5,0xc3,
                               0x1e00,0x1e02,0x1e01,3,0x800a,0x800b};
    for (unsigned int i=0; i<sizeof(state_names)/sizeof(state_names[0]); ++i) {
        glGetIntegerv(state_names[i], &actual_state);
        if (actual_state != state_values[i]) {
            print_hex("GL state mismatch name",state_names[i]);
            print_hex("GL state actual",(unsigned int)actual_state);
            fail("ANGLE EGL provider smoke: real stencil/blend state mismatch");
        }
    }
    if (glGetError() != GL_NO_ERROR) fail("ANGLE EGL provider smoke: stencil/blend error");
    glStencilMaskSeparate(0xdead, 0xff);
    glClearStencil(0); /* A successful state call must preserve the pending error. */
    if (glGetError() != 0x0500) fail("ANGLE EGL provider smoke: invalid stencil face not rejected");
    glStencilFunc(0x0207,0,0xffffffffu);
    glStencilMask(0xffffffffu);
    glStencilOp(0x1e00,0x1e00,0x1e00);
    glBlendEquation(0x8006);
    if (glGetError() != GL_NO_ERROR) fail("ANGLE EGL provider smoke: stencil aliases failed");
    puts("ANGLE_EGL_PROVIDER_STENCIL_BLEND_OK real-state=14 invalid-enum=checked pending-error=preserved");
    glViewport(0, 0, 64, 64);
    glClearColor(0.2f, 0.6f, 0.9f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    unsigned char pixels[16] = {0};
    glReadPixels(0, 0, 2, 2, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    const unsigned char expected[4] = {51, 153, 230, 255};
    for (unsigned int pixel = 0; pixel < 4; ++pixel) {
        for (unsigned int channel = 0; channel < 4; ++channel) {
            const unsigned int actual = pixels[pixel * 4u + channel];
            const unsigned int target = expected[channel];
            if (actual > target + 2u || actual + 2u < target)
                fail("ANGLE EGL provider smoke: ANGLE pbuffer pixel mismatch");
        }
    }
    print_hex("Readback RGBA", ((unsigned int)pixels[0] << 24) |
                                 ((unsigned int)pixels[1] << 16) |
                                 ((unsigned int)pixels[2] << 8) | pixels[3]);
    puts("ANGLE_EGL_PROVIDER_DRAW_OK glViewport=64x64 glClearColor=0.2,0.6,0.9,1 glReadPixels=2x2-RGBA8");
    if (glGetError() != GL_NO_ERROR) fail("ANGLE EGL provider smoke: glGetError was nonzero");
    if (!eglSwapBuffers(display, surface)) fail("ANGLE EGL provider smoke: pbuffer swap failed");
    puts("ANGLE_EGL_PROVIDER_OK display=config=depth24 context=pbuffer make-current=QNX-TLS glGetString=host-ANGLE");

    if (!eglMakeCurrent(display, (EGLSurface)0, (EGLSurface)0, (EGLContext)0))
        fail("ANGLE EGL provider smoke: unbind failed");
    glClearStencil(0);
    if (glGetError() != 0x0502)
        fail("ANGLE EGL provider smoke: state call without context not rejected");
    if (!eglDestroyContext(display, context)) fail("ANGLE EGL provider smoke: destroy context failed");
    if (!eglDestroySurface(display, surface)) fail("ANGLE EGL provider smoke: destroy surface failed");
    if (!eglTerminate(display)) fail("ANGLE EGL provider smoke: terminate failed");
    finish(0);
}
