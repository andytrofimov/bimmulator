/* QNX EGL provider routed through the verified 34-slot dispatcher ABI.
 * The stateful slice supports ANGLE-backed pbuffer and Screen window surfaces,
 * display/config/context and make-current, GL state queries, buffer/texture
 * uploads, source shader compile/link/reflection, VBO-backed attribute state,
 * draw calls and RGBA readback. Exact-mapped IMG shader binaries are translated
 * to ESSL and compiled on the host; unmatched proprietary binaries and
 * remaining unsupported GLES calls fail with GL errors.
 */
#include "angle-egl-rpc.h"

extern int printf(const char *format, ...);
extern int fflush(void *stream);
#define EGL_LOG(...) do { printf(__VA_ARGS__); fflush((void *)0); } while (0)
#if defined(IDRIVE_ANGLE_EGL_TRACE)
#define EGL_TRACE(...) EGL_LOG(__VA_ARGS__)
#else
#define EGL_TRACE(...) ((void)0)
#endif

#include <stddef.h>
#include <stdint.h>

#define AF_INET 2
#define SOCK_STREAM 1
#define IDRIVE_NETWORK_PORT 41416u

struct idrive_sockaddr_in {
    unsigned char length;
    unsigned char family;
    unsigned short port;
    unsigned int address;
    unsigned char zero[8];
};

extern int socket(int domain, int type, int protocol);
extern int connect(int fd, const void *address, unsigned int address_length);
extern int send(int fd, const void *data, unsigned int length, int flags);
extern int recv(int fd, void *data, unsigned int length, int flags);
extern int close(int fd);
extern char *getenv(const char *name);
extern int setenv(const char *name, const char *value, int overwrite);
extern int unsetenv(const char *name);
extern int pthread_key_create(unsigned int *key, void (*destructor)(void *));
extern void *pthread_getspecific(unsigned int key);
extern int pthread_setspecific(unsigned int key, const void *value);
extern int sched_yield(void);
extern int usleep(unsigned int microseconds);
extern uint64_t ClockCycles(void);
extern void *mmap_device_memory(void *, size_t, int, int, uint64_t);
extern void *malloc(size_t size);
extern void free(void *pointer);
extern int screen_get_window_property_iv(void *window, int property, int *value);
extern int screen_get_window_property_pv(void *window, int property, void **value);
extern int screen_set_window_property_iv(void *window, int property,
                                        const int *value);
extern int screen_destroy_window_buffers(void *window);
extern int screen_create_window_buffers(void *window, int count);
extern int screen_get_buffer_property_iv(void *buffer, int property, int *value);
extern int screen_get_buffer_property_llv(void *buffer, int property, int64_t *value);
extern int screen_post_window(void *window, void *buffer, int count,
                              const int *damage, int flags);
extern void *memcpy(void *destination, const void *source, unsigned int length);
extern void *memset(void *destination, int value, unsigned int length);
extern int memcmp(const void *left, const void *right, unsigned int length);
extern size_t strlen(const char *text);
extern int strcmp(const char *left, const char *right);

typedef int EGLint;
typedef unsigned int EGLBoolean;
typedef unsigned int EGLenum;
typedef void *EGLDisplay;
typedef void *EGLConfig;
typedef void *EGLSurface;
typedef void *EGLContext;
typedef void *EGLClientBuffer;
typedef void (*EGLProc)(void);

enum {
    EGL_FALSE = 0,
    EGL_TRUE = 1,
    EGL_SUCCESS = 0x3000,
    EGL_NOT_INITIALIZED = 0x3001,
    EGL_BAD_ACCESS = 0x3002,
    EGL_BAD_ALLOC = 0x3003,
    EGL_BAD_ATTRIBUTE = 0x3004,
    EGL_BAD_CONFIG = 0x3005,
    EGL_BAD_CONTEXT = 0x3006,
    EGL_BAD_CURRENT_SURFACE = 0x3007,
    EGL_BAD_DISPLAY = 0x3008,
    EGL_BAD_MATCH = 0x3009,
    EGL_BAD_NATIVE_PIXMAP = 0x300a,
    EGL_BAD_NATIVE_WINDOW = 0x300b,
    EGL_BAD_PARAMETER = 0x300c,
    EGL_BAD_SURFACE = 0x300d,
    EGL_NONE = 0x3038,
    EGL_RENDER_BUFFER = 0x3086,
    EGL_BACK_BUFFER = 0x3084,
    EGL_WIDTH = 0x3057,
    EGL_HEIGHT = 0x3056,
    EGL_OPENGL_ES_API = 0x30a0,
    EGL_CONTEXT_CLIENT_TYPE = 0x3097,
    EGL_CONTEXT_CLIENT_VERSION = 0x3098,
    EGL_DRAW = 0x3059,
    EGL_READ = 0x305a,
    EGL_VENDOR = 0x3053,
    EGL_VERSION = 0x3054,
    EGL_EXTENSIONS = 0x3055,
    EGL_CLIENT_APIS = 0x308d,
    GL_NO_ERROR = 0,
    GL_INVALID_ENUM = 0x0500,
    GL_INVALID_VALUE = 0x0501,
    GL_INVALID_OPERATION = 0x0502,
    GL_SCISSOR_TEST = 0x0c11,
    GL_UNPACK_ALIGNMENT = 0x0cf5,
    GL_BYTE = 0x1400,
    GL_UNSIGNED_BYTE = 0x1401,
    GL_SHORT = 0x1402,
    GL_UNSIGNED_SHORT = 0x1403,
    GL_INT = 0x1404,
    GL_UNSIGNED_INT = 0x1405,
    GL_FLOAT = 0x1406,
    GL_ARRAY_BUFFER = 0x8892,
    GL_ELEMENT_ARRAY_BUFFER = 0x8893,
    GL_TEXTURE0 = 0x84c0,
    GL_UNSIGNED_SHORT_4_4_4_4 = 0x8033,
    GL_UNSIGNED_SHORT_5_5_5_1 = 0x8034,
    GL_UNSIGNED_SHORT_5_6_5 = 0x8363,
    GL_ALPHA = 0x1906,
    GL_RGB = 0x1907,
    GL_RGBA = 0x1908,
    GL_LUMINANCE = 0x1909,
    GL_LUMINANCE_ALPHA = 0x190a,
    GL_VERSION = 0x1f02,
    GL_TEXTURE_2D = 0x0de1
};

enum {
    SCREEN_PROPERTY_BUFFER_SIZE = 5,
    SCREEN_PROPERTY_FORMAT = 14,
    SCREEN_PROPERTY_PHYSICALLY_CONTIGUOUS = 32,
    SCREEN_PROPERTY_RENDER_BUFFERS = 37,
    SCREEN_PROPERTY_SIZE = 40,
    SCREEN_PROPERTY_STRIDE = 44,
    SCREEN_PROPERTY_SWAP_INTERVAL = 45,
    SCREEN_PROPERTY_USAGE = 48,
    SCREEN_PROPERTY_RENDER_BUFFER_COUNT = 53,
    SCREEN_PROPERTY_PHYSICAL_ADDRESS = 55,
    SCREEN_FORMAT_RGBA8888 = 8,
    SCREEN_USAGE_OPENGL_ES2 = 1 << 5,
    IDRIVE_SCREEN_MAX_BUFFERS = 2,
    IDRIVE_SCREEN_MAX_WINDOW_SURFACES = 16
};

static int read_surface_dimension(const char *name, int *value)
{
    const char *text = getenv(name);
    unsigned int parsed = 0;
    if (!text || !*text) return 0;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9') return -1;
        parsed = parsed * 10u + (unsigned int)(*text - '0');
        if (parsed > 4096u) return -1;
    }
    if (!parsed) return -1;
    *value = (int)parsed;
    return 1;
}

static int resize_native_window(void *window, int dimensions[2], int count)
{
    int width = 0, height = 0, width_status, height_status;
    int target[2], original[2], restore = -1;
    width_status = read_surface_dimension(
        "IDRIVE_ANGLE_HMI_SURFACE_WIDTH", &width);
    height_status = read_surface_dimension(
        "IDRIVE_ANGLE_HMI_SURFACE_HEIGHT", &height);
    if (!width_status && !height_status) return 1;
    if (width_status != 1 || height_status != 1 ||
        (uint64_t)(unsigned int)width * (uint64_t)(unsigned int)height * 4u >
            IDRIVE_ANGLE_EGL_RPC_MAX_FRAME_BYTES)
        return 0;
    if (width == dimensions[0] && height == dimensions[1]) return 1;

    original[0] = dimensions[0];
    original[1] = dimensions[1];
    target[0] = width;
    target[1] = height;
    if (screen_destroy_window_buffers(window) != 0) {
        EGL_TRACE("IDRIVE_ANGLE_HMI_SURFACE_RESIZE_ERROR stage=destroy old=%dx%d target=%dx%d\n",
                  original[0], original[1], width, height);
        return 0;
    }
    if (screen_set_window_property_iv(window, SCREEN_PROPERTY_BUFFER_SIZE,
                                      target) != 0 ||
        screen_set_window_property_iv(window, SCREEN_PROPERTY_SIZE,
                                      target) != 0 ||
        screen_create_window_buffers(window, count) != 0) {
        if (screen_set_window_property_iv(window, SCREEN_PROPERTY_BUFFER_SIZE,
                                          original) == 0 &&
            screen_set_window_property_iv(window, SCREEN_PROPERTY_SIZE,
                                          original) == 0)
            restore = screen_create_window_buffers(window, count);
        EGL_TRACE("IDRIVE_ANGLE_HMI_SURFACE_RESIZE_ERROR stage=allocate old=%dx%d target=%dx%d restore=%d\n",
                  original[0], original[1], width, height, restore);
        (void)restore;
        return 0;
    }
    dimensions[0] = width;
    dimensions[1] = height;
    EGL_TRACE("IDRIVE_ANGLE_HMI_SURFACE_RESIZE old=%dx%d target=%dx%d buffers=%d\n",
              original[0], original[1], width, height, count);
    return 1;
}

#define EGL_NO_DISPLAY ((EGLDisplay)0)
#define EGL_NO_SURFACE ((EGLSurface)0)
#define EGL_NO_CONTEXT ((EGLContext)0)

extern int getpid(void);
extern int *__get_errno_ptr(void);

struct RpcResult {
    unsigned int error;
    unsigned int value[3];
    unsigned int payload_size;
};

static EGLDisplay g_display = (EGLDisplay)(uintptr_t)0x1001;
static int g_rpc_fd = -1;
static unsigned int g_next_request_id = 1;

/* EGL current state and scratch buffers belong to the calling HMI thread.
 * The native EGL/GLES dispatchers use thread-local state, so keeping these
 * process-global made concurrent HmiMain3D calls overwrite each other's
 * request payloads and current-context bookkeeping. */
enum { kBindCacheSlots = 128 };

struct ProviderThreadState {
    unsigned int egl_error;
    unsigned int gl_error;
    EGLContext current_context;
    EGLSurface current_draw;
    EGLSurface current_read;
    unsigned int unpack_alignment;
    unsigned int bound_array_buffer;
    unsigned int bound_element_array_buffer;
    char string_buffer[IDRIVE_ANGLE_EGL_RPC_MAX_STRING_BYTES];
    unsigned char request_payload[IDRIVE_ANGLE_EGL_RPC_MAX_ATTR_BYTES];
    unsigned char *rpc_payload;
    unsigned int batch_error;
    unsigned int confirmed_bind[2][kBindCacheSlots];
};

static unsigned int g_thread_state_key;
static volatile int g_thread_state_key_ready;
static volatile int g_thread_state_key_lock;
static volatile int g_rpc_lock;
static unsigned char g_fallback_rpc_payload[IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD];
static struct ProviderThreadState g_fallback_thread_state = {
    EGL_SUCCESS, GL_NO_ERROR, EGL_NO_CONTEXT, EGL_NO_SURFACE, EGL_NO_SURFACE,
    4, 0, 0, { 0 }, { 0 }, g_fallback_rpc_payload, 0, { { 0 }, { 0 } }
};

static struct idrive_angle_mailbox *g_mailbox;
static struct ProviderThreadState *g_batch_owner;
static unsigned int g_batch_size;
static unsigned char g_batch[IDRIVE_ANGLE_EGL_BATCH_BYTES];

static void flush_batch_locked(void);

static void lock_flag(volatile int *lock)
{
    while (__sync_lock_test_and_set(lock, 1)) {
        while (*lock) (void)sched_yield();
    }
}

static void unlock_flag(volatile int *lock)
{
    __sync_lock_release(lock);
}

static void destroy_thread_state(void *data)
{
    struct ProviderThreadState *state =
        (struct ProviderThreadState *)data;
    if (!state) return;
    lock_flag(&g_rpc_lock);
    if (g_batch_owner == state) flush_batch_locked();
    unlock_flag(&g_rpc_lock);
    if (state->rpc_payload) free(state->rpc_payload);
    free(state);
}

static struct ProviderThreadState *provider_thread_state(void)
{
    struct ProviderThreadState *state;
    if (!__atomic_load_n(&g_thread_state_key_ready, __ATOMIC_ACQUIRE)) {
        int ready;
        lock_flag(&g_thread_state_key_lock);
        ready = __atomic_load_n(&g_thread_state_key_ready, __ATOMIC_RELAXED);
        if (!ready) {
            ready = pthread_key_create(&g_thread_state_key, destroy_thread_state) == 0;
            __atomic_store_n(&g_thread_state_key_ready, ready, __ATOMIC_RELEASE);
        }
        unlock_flag(&g_thread_state_key_lock);
        if (!ready) return &g_fallback_thread_state;
    }

    state = (struct ProviderThreadState *)
        pthread_getspecific(g_thread_state_key);
    if (state) return state;

    state = (struct ProviderThreadState *)malloc(sizeof(*state));
    if (!state) return &g_fallback_thread_state;
    memset(state, 0, sizeof(*state));
    state->egl_error = EGL_SUCCESS;
    state->gl_error = GL_NO_ERROR;
    state->current_context = EGL_NO_CONTEXT;
    state->current_draw = EGL_NO_SURFACE;
    state->current_read = EGL_NO_SURFACE;
    state->unpack_alignment = 4;
    if (pthread_setspecific(g_thread_state_key, state) != 0) {
        free(state);
        return &g_fallback_thread_state;
    }
    return state;
}

static unsigned char *rpc_payload_buffer(void)
{
    struct ProviderThreadState *state = provider_thread_state();
    if (!state->rpc_payload) {
        state->rpc_payload =
            (unsigned char *)malloc(IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD);
        if (!state->rpc_payload) return g_fallback_rpc_payload;
    }
    return state->rpc_payload;
}

#define g_egl_error (provider_thread_state()->egl_error)
#define g_gl_error (provider_thread_state()->gl_error)
#define g_current_context (provider_thread_state()->current_context)
#define g_current_draw (provider_thread_state()->current_draw)
#define g_current_read (provider_thread_state()->current_read)
#define g_string_buffer (provider_thread_state()->string_buffer)
#define g_rpc_payload (rpc_payload_buffer())
#define g_request_payload (provider_thread_state()->request_payload)
#define g_unpack_alignment (provider_thread_state()->unpack_alignment)
#define g_bound_array_buffer (provider_thread_state()->bound_array_buffer)
#define g_bound_element_array_buffer \
    (provider_thread_state()->bound_element_array_buffer)

struct WindowSurface {
    unsigned int id;
    void *window;
    void *buffers[IDRIVE_SCREEN_MAX_BUFFERS];
    uint64_t physical_address[IDRIVE_SCREEN_MAX_BUFFERS];
    unsigned int stride[IDRIVE_SCREEN_MAX_BUFFERS];
    unsigned int width;
    unsigned int height;
    unsigned int count;
    int saved_swap_interval;
    int immediate_post;
};

static struct WindowSurface g_window_surfaces[IDRIVE_SCREEN_MAX_WINDOW_SURFACES];

static int send_all(int fd, const unsigned char *data, unsigned int length)
{
    unsigned int sent = 0;
    while (sent < length) {
        int result = (int)send(fd, data + sent, length - sent, 0);
        if (result <= 0) {
            EGL_TRACE("IDRIVE_ANGLE_RPC_SEND_FAIL fd=%d sent=%u length=%u result=%d errno=%d\n",
                      fd, sent, length, result, *__get_errno_ptr());
            return 0;
        }
        sent += (unsigned int)result;
    }
    return 1;
}

static int receive_all(int fd, unsigned char *data, unsigned int length)
{
    unsigned int received = 0;
    while (received < length) {
        int result = (int)recv(fd, data + received, length - received, 0);
        if (result <= 0) {
            EGL_TRACE("IDRIVE_ANGLE_RPC_RECV_FAIL fd=%d received=%u length=%u result=%d errno=%d\n",
                      fd, received, length, result, *__get_errno_ptr());
            return 0;
        }
        received += (unsigned int)result;
    }
    return 1;
}

static void disconnect_rpc(void)
{
    if (g_rpc_fd >= 0) close(g_rpc_fd);
    g_rpc_fd = -1;
}

/* Serial preflights and HmiMain3D share this aperture. Claim ownership before
 * writing and publish the frame only after it has been copied. */
static int mailbox_rpc(const unsigned char *request,
                       const unsigned char *payload, unsigned int payload_size,
                       unsigned char *response)
{
    enum { kReadWrite = 0x300, kWaitAttempts = 30000 };
    enum { kResponseSpins = 8192 };
    struct idrive_angle_mailbox *mailbox = g_mailbox;
    unsigned int attempt;
    unsigned int state;
    uint64_t spin_until = 0;

    if (!mailbox) {
        void *mapping = mmap_device_memory(0, IDRIVE_ANGLE_MAILBOX_BYTES,
                                           kReadWrite, 0,
                                           IDRIVE_ANGLE_MAILBOX_PHYS);
        if (!mapping || mapping == (void *)-1) {
            EGL_LOG("IDRIVE_ANGLE_MAILBOX_FAIL stage=map errno=%d\n",
                      *__get_errno_ptr());
            return 0;
        }
        g_mailbox = mailbox = mapping;
    }
    if (__atomic_load_n(&mailbox->magic, __ATOMIC_ACQUIRE) !=
        IDRIVE_ANGLE_MAILBOX_MAGIC) {
        EGL_LOG("IDRIVE_ANGLE_MAILBOX_FAIL stage=magic\n");
        return 0;
    }
    for (attempt = 0; attempt < kWaitAttempts; ++attempt) {
        state = IDRIVE_ANGLE_MAILBOX_IDLE;
        if (__atomic_compare_exchange_n(&mailbox->state, &state,
                                        IDRIVE_ANGLE_MAILBOX_WRITING, 0,
                                        __ATOMIC_ACQUIRE, __ATOMIC_RELAXED))
            break;
        if (state == IDRIVE_ANGLE_MAILBOX_FAILED) return 0;
        (void)usleep(1000);
    }
    if (attempt == kWaitAttempts) {
        EGL_LOG("IDRIVE_ANGLE_MAILBOX_FAIL stage=claim\n");
        return 0;
    }
    memcpy(mailbox->frame, request, IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES);
    if (payload_size)
        memcpy(mailbox->frame + IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES,
               payload, payload_size);
    if (__atomic_load_n(&mailbox->features, __ATOMIC_RELAXED) & IDRIVE_ANGLE_MAILBOX_FAST_WAIT) {
        const unsigned int opcode = idrive_angle_egl_rpc_u16(request + 6);
        if (opcode == IDRIVE_ANGLE_EGL_RPC_GL_BATCH ||
            opcode == IDRIVE_ANGLE_EGL_RPC_SWAP_WINDOW_SURFACE)
            spin_until = ClockCycles() + 49152u; /* Eight ms at the OMAP5 counter rate. */
    }
    state = IDRIVE_ANGLE_MAILBOX_WRITING;
    if (!__atomic_compare_exchange_n(&mailbox->state, &state,
                                     IDRIVE_ANGLE_MAILBOX_REQUEST, 0,
                                     __ATOMIC_RELEASE, __ATOMIC_RELAXED))
        return 0;
    for (attempt = 0; attempt < kWaitAttempts; ++attempt) {
        /* Short GLES calls usually complete before the guest could wake
         * from a timer sleep. Yield for GPU work and long operations. */
        unsigned int spin = kResponseSpins;
        do {
            state = __atomic_load_n(&mailbox->state, __ATOMIC_ACQUIRE);
        } while (state != IDRIVE_ANGLE_MAILBOX_RESPONSE &&
                 state != IDRIVE_ANGLE_MAILBOX_FAILED && --spin);
        if (state == IDRIVE_ANGLE_MAILBOX_RESPONSE) {
            unsigned int length;
            memcpy(response, mailbox->frame, IDRIVE_ANGLE_EGL_RPC_RESPONSE_BYTES);
            length = idrive_angle_egl_rpc_u32(response + 24);
            if (length <= IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD &&
                memcmp(response, "I6EA", 4) == 0 &&
                idrive_angle_egl_rpc_u16(response + 4) == IDRIVE_ANGLE_EGL_RPC_VERSION &&
                idrive_angle_egl_rpc_u32(response + 28) ==
                    idrive_angle_egl_rpc_u32(request + 24)) {
                if (length)
                    memcpy(g_rpc_payload,
                           mailbox->frame + IDRIVE_ANGLE_EGL_RPC_RESPONSE_BYTES,
                           length);
                return __atomic_compare_exchange_n(&mailbox->state, &state,
                                                   IDRIVE_ANGLE_MAILBOX_IDLE, 0,
                                                   __ATOMIC_RELEASE,
                                                   __ATOMIC_RELAXED);
            }
            break;
        }
        if (state == IDRIVE_ANGLE_MAILBOX_FAILED) return 0;
        while (spin_until && ClockCycles() < spin_until) {
            state = __atomic_load_n(&mailbox->state, __ATOMIC_ACQUIRE);
            if (state == IDRIVE_ANGLE_MAILBOX_RESPONSE ||
                state == IDRIVE_ANGLE_MAILBOX_FAILED)
                break;
        }
        if (state == IDRIVE_ANGLE_MAILBOX_RESPONSE) continue;
        if (state == IDRIVE_ANGLE_MAILBOX_FAILED) return 0;
        spin_until = 0;
        (void)usleep(1000);
    }
    /* A timed-out command may already have changed EGL state. Stop the
     * channel and avoid retrying or letting another client reuse its bytes. */
    __atomic_store_n(&mailbox->state, IDRIVE_ANGLE_MAILBOX_FAILED, __ATOMIC_RELEASE);
    EGL_LOG("IDRIVE_ANGLE_MAILBOX_FAIL stage=response\n");
    return 0;
}

static void put_rpc_float(unsigned char *destination, float value)
{
    unsigned int bits;
    memcpy(&bits, &value, sizeof(bits));
    idrive_angle_egl_rpc_put_u32(destination, bits);
}

/* QNX libsocket reads SOCK inside socket() to choose /dev/socket/<domain>.
 * HmiMain3D starts with the isolated stack selected and takes the direct path;
 * other clients use the scoped fallback so unrelated sockets retain their
 * inherited stack setting. */
static int create_rpc_socket(void)
{
    const unsigned int path_capacity = 512;
    const char *configured_stack = getenv("IDRIVE_ANGLE_RPC_SOCK");
    const char *previous_stack;
    char selected_stack[512];
    char saved_stack[512];
    unsigned int length;
    int had_previous;
    int fd;
    int socket_error;
    int restore_result;
    int *error_number = __get_errno_ptr();

    if (!configured_stack || !configured_stack[0])
        return socket(AF_INET, SOCK_STREAM, 0);

    length = (unsigned int)strlen(configured_stack);
    if (length >= path_capacity) {
        *error_number = 22;
        return -1;
    }
    memcpy(selected_stack, configured_stack, length + 1);

    previous_stack = getenv("SOCK");
    had_previous = previous_stack != (const char *)0;
    if (had_previous) {
        length = (unsigned int)strlen(previous_stack);
        if (length >= path_capacity) {
            *error_number = 22;
            return -1;
        }
        memcpy(saved_stack, previous_stack, length + 1);
        if (strcmp(saved_stack, selected_stack) == 0) {
            fd = socket(AF_INET, SOCK_STREAM, 0);
            EGL_TRACE("IDRIVE_ANGLE_RPC_SOCKET_RESULT stage=socket-inherited fd=%d errno=%d prefix=%s\n",
                      fd, *error_number, selected_stack);
            return fd;
        }
    }

    if (setenv("SOCK", selected_stack, 1) != 0) {
        EGL_TRACE("IDRIVE_ANGLE_RPC_SOCKET_FAIL stage=setenv errno=%d prefix=%s\n",
                  *error_number, selected_stack);
        return -1;
    }
    fd = socket(AF_INET, SOCK_STREAM, 0);
    socket_error = *error_number;
    EGL_TRACE("IDRIVE_ANGLE_RPC_SOCKET_RESULT stage=socket-scoped fd=%d errno=%d prefix=%s\n",
              fd, socket_error, selected_stack);
    restore_result = had_previous
        ? setenv("SOCK", saved_stack, 1)
        : unsetenv("SOCK");
    if (restore_result != 0) {
        int restore_error = *error_number;
        EGL_TRACE("IDRIVE_ANGLE_RPC_SOCK_RESTORE_FAIL result=%d errno=%d\n",
                  restore_result, restore_error);
        if (fd >= 0) close(fd);
        *error_number = restore_error;
        return -1;
    }
    if (fd < 0) *error_number = socket_error;
    return fd;
}

static int connect_rpc(void)
{
    struct idrive_sockaddr_in address;
    int fd;
    if (g_rpc_fd >= 0) return 1;
    fd = create_rpc_socket();
    if (fd < 0) {
        EGL_TRACE("IDRIVE_ANGLE_RPC_CONNECT_FAIL stage=socket result=%d errno=%d\n",
                  fd, *__get_errno_ptr());
        return 0;
    }
    EGL_TRACE("IDRIVE_ANGLE_RPC_SOCKET_CREATED fd=%d prefix=%s\n",
              fd, getenv("IDRIVE_ANGLE_RPC_SOCK") &&
                  getenv("IDRIVE_ANGLE_RPC_SOCK")[0]
                      ? getenv("IDRIVE_ANGLE_RPC_SOCK") : "process-default");
    memset(&address, 0, sizeof(address));
    address.length = (unsigned char)sizeof(address);
    address.family = AF_INET;
    address.port = (unsigned short)((IDRIVE_NETWORK_PORT << 8) |
                                    (IDRIVE_NETWORK_PORT >> 8));
    address.address = 0xfdc730a0u; /* 160.48.199.253 in network byte order */
    {
        int result = connect(fd, &address, sizeof(address));
        if (result != 0) {
#if defined(IDRIVE_ANGLE_EGL_TRACE)
            int error = *__get_errno_ptr();
            EGL_TRACE("IDRIVE_ANGLE_RPC_CONNECT_FAIL stage=connect fd=%d result=%d errno=%d endpoint=160.48.199.253:%u\n",
                      fd, result, error, IDRIVE_NETWORK_PORT);
#endif
            close(fd);
            return 0;
        }
    }
    g_rpc_fd = fd;
    EGL_TRACE("IDRIVE_ANGLE_RPC_CONNECTED fd=%d\n", fd);
    return 1;
}

static unsigned int encode_request(unsigned char *request, unsigned int opcode,
                                   unsigned int a, unsigned int b, unsigned int c,
                                   unsigned int payload_size)
{
    unsigned int id = g_next_request_id++;
    if (!id) id = g_next_request_id++;
    memcpy(request, "I6ER", 4);
    idrive_angle_egl_rpc_put_u16(request + 4, IDRIVE_ANGLE_EGL_RPC_VERSION);
    idrive_angle_egl_rpc_put_u16(request + 6, opcode);
    idrive_angle_egl_rpc_put_u32(request + 8, (unsigned int)getpid());
    idrive_angle_egl_rpc_put_u32(request + 12, a);
    idrive_angle_egl_rpc_put_u32(request + 16, b);
    idrive_angle_egl_rpc_put_u32(request + 20, c);
    idrive_angle_egl_rpc_put_u32(request + 24, id);
    idrive_angle_egl_rpc_put_u32(request + 28, payload_size);
    return id;
}

static int rpc_call_locked(unsigned int opcode, unsigned int a, unsigned int b,
                           unsigned int c, const unsigned char *payload,
                           unsigned int payload_size, struct RpcResult *result,
                           int use_mailbox)
{
    unsigned char request[IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES];
    unsigned char response[IDRIVE_ANGLE_EGL_RPC_RESPONSE_BYTES];
    unsigned int reply_size;
    unsigned int request_id;
    int success = 0;

    memset(result, 0, sizeof(*result));
    request_id = encode_request(request, opcode, a, b, c, payload_size);

    EGL_TRACE("IDRIVE_ANGLE_RPC_BEGIN opcode=%u request=%u payload=%u\n",
              opcode, request_id, payload_size);
    if (use_mailbox) {
        if (!mailbox_rpc(request, payload, payload_size, response)) goto done;
    } else if (!connect_rpc()) {
        EGL_TRACE("IDRIVE_ANGLE_RPC_FAIL opcode=%u request=%u stage=connect\n",
                  opcode, request_id);
        goto done;
    } else if (!send_all(g_rpc_fd, request, sizeof(request))) {
        EGL_TRACE("IDRIVE_ANGLE_RPC_FAIL opcode=%u request=%u stage=send-header\n",
                  opcode, request_id);
        disconnect_rpc();
        goto done;
    } else if (payload_size && !send_all(g_rpc_fd, payload, payload_size)) {
        EGL_TRACE("IDRIVE_ANGLE_RPC_FAIL opcode=%u request=%u stage=send-payload\n",
                  opcode, request_id);
        disconnect_rpc();
        goto done;
    } else if (!receive_all(g_rpc_fd, response, sizeof(response))) {
        EGL_TRACE("IDRIVE_ANGLE_RPC_FAIL opcode=%u request=%u stage=receive-header\n",
                  opcode, request_id);
        disconnect_rpc();
        goto done;
    }

    if (memcmp(response, "I6EA", 4) != 0 ||
        idrive_angle_egl_rpc_u16(response + 4) != IDRIVE_ANGLE_EGL_RPC_VERSION ||
        idrive_angle_egl_rpc_u32(response + 28) != request_id) {
        disconnect_rpc();
        goto done;
    }
    result->error = idrive_angle_egl_rpc_u32(response + 8);
    result->value[0] = idrive_angle_egl_rpc_u32(response + 12);
    result->value[1] = idrive_angle_egl_rpc_u32(response + 16);
    result->value[2] = idrive_angle_egl_rpc_u32(response + 20);
    reply_size = idrive_angle_egl_rpc_u32(response + 24);
    result->payload_size = reply_size;
    if (reply_size > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD ||
        (!use_mailbox && reply_size &&
         !receive_all(g_rpc_fd, g_rpc_payload, reply_size))) {
        EGL_TRACE("IDRIVE_ANGLE_RPC_FAIL opcode=%u request=%u stage=receive-payload size=%u\n",
                  opcode, request_id, reply_size);
        disconnect_rpc();
        goto done;
    }
    EGL_TRACE("IDRIVE_ANGLE_RPC_DONE opcode=%u request=%u status=%u error=0x%04x payload=%u\n",
              opcode, request_id, idrive_angle_egl_rpc_u16(response + 6),
              result->error, reply_size);
    if (opcode == IDRIVE_ANGLE_EGL_RPC_TERMINATE &&
        idrive_angle_egl_rpc_u16(response + 6) == 0) disconnect_rpc();
    success = idrive_angle_egl_rpc_u16(response + 6) == 0;

done:
    return success;
}

static void flush_batch_locked(void)
{
    struct RpcResult reply;
    unsigned int error;
    if (!g_batch_owner) return;
    if (rpc_call_locked(IDRIVE_ANGLE_EGL_RPC_GL_BATCH, 0, 0, 0, g_batch,
                        g_batch_size, &reply, 1))
        error = reply.value[0];
    else
        error = GL_INVALID_OPERATION;
    if (!g_batch_owner->batch_error) g_batch_owner->batch_error = error;
    g_batch_owner = 0;
    g_batch_size = 0;
}

static int rpc_ordered(unsigned int opcode, unsigned int a, unsigned int b,
                       unsigned int c, const unsigned char *payload,
                       unsigned int payload_size, struct RpcResult *result,
                       unsigned int batch_features)
{
    const unsigned int size = IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES + payload_size;
    const char *transport;
    int use_mailbox;
    int success = 0;
    if (!result || payload_size > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD) return 0;

    /* Keep one ordered stream even when multiple HMI threads call EGL. */
    lock_flag(&g_rpc_lock);
    transport = getenv("IDRIVE_ANGLE_EGL_MAILBOX");
    use_mailbox = transport && transport[0] == '1' && !transport[1];
    if (batch_features && use_mailbox && g_mailbox && size <= sizeof(g_batch) &&
        (__atomic_load_n(&g_mailbox->features, __ATOMIC_RELAXED) & batch_features) ==
            batch_features) {
        struct ProviderThreadState *state = provider_thread_state();
        if (state != &g_fallback_thread_state) {
            if (g_batch_owner != state || size > sizeof(g_batch) - g_batch_size)
                flush_batch_locked();
            g_batch_owner = state;
            encode_request(g_batch + g_batch_size, opcode, a, b, c, payload_size);
            if (payload_size)
                memcpy(g_batch + g_batch_size + IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES,
                       payload, payload_size);
            g_batch_size += size;
            memset(result, 0, sizeof(*result));
            success = 1;
        }
    }
    if (!success) {
        flush_batch_locked();
        success = rpc_call_locked(opcode, a, b, c, payload, payload_size, result,
                                  use_mailbox);
    }
    unlock_flag(&g_rpc_lock);
    return success;
}

static int rpc(unsigned int opcode, unsigned int a, unsigned int b,
               unsigned int c, const unsigned char *payload,
               unsigned int payload_size, struct RpcResult *result)
{
    return rpc_ordered(opcode, a, b, c, payload, payload_size, result,
                       idrive_angle_egl_rpc_batchable(opcode)
                           ? IDRIVE_ANGLE_MAILBOX_BATCH : 0);
}

static struct WindowSurface *find_window_surface(unsigned int id)
{
    unsigned int i;
    for (i = 0; i < IDRIVE_SCREEN_MAX_WINDOW_SURFACES; ++i)
        if (g_window_surfaces[i].id == id) return &g_window_surfaces[i];
    return 0;
}

static struct WindowSurface *allocate_window_surface(void)
{
    unsigned int i;
    for (i = 0; i < IDRIVE_SCREEN_MAX_WINDOW_SURFACES; ++i)
        if (!g_window_surfaces[i].id) return &g_window_surfaces[i];
    return 0;
}

static void clear_window_surfaces(void)
{
    memset(g_window_surfaces, 0, sizeof(g_window_surfaces));
}

static unsigned int handle_id(const void *handle)
{
    return (unsigned int)(uintptr_t)handle;
}

static unsigned int pack_attributes(const EGLint *attributes,
                                    unsigned char *out,
                                    unsigned int capacity)
{
    unsigned int count = 0;
    if (!attributes) {
        if (capacity < 4) return 0;
        idrive_angle_egl_rpc_put_u32(out, EGL_NONE);
        return 4;
    }
    while (count < IDRIVE_ANGLE_EGL_RPC_MAX_ATTR_INTS &&
           (count + 1) * 4u <= capacity) {
        idrive_angle_egl_rpc_put_u32(out + count * 4u,
                                     (unsigned int)attributes[count]);
        if (attributes[count] == EGL_NONE) return (count + 1) * 4u;
        count++;
    }
    return 0;
}

static EGLBoolean unsupported_egl(unsigned int error)
{
    g_egl_error = error;
    return EGL_FALSE;
}

static void *unsupported_handle(unsigned int error)
{
    g_egl_error = error;
    return (void *)0;
}

static EGLBoolean egl_get_configs(EGLDisplay display, EGLConfig *configs,
                                  EGLint config_size, EGLint *num_config)
{
    struct RpcResult reply;
    unsigned int capacity = config_size > 0 && configs ? (unsigned int)config_size : 0;
    if (display != g_display || config_size < 0 || (capacity && !configs))
        return unsupported_egl(EGL_BAD_PARAMETER);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GET_CONFIGS, capacity, 0, 0, 0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    if (num_config) *num_config = (EGLint)reply.value[0];
    for (unsigned int i = 0; i < capacity && i < reply.payload_size / 4u; ++i)
        configs[i] = (EGLConfig)(uintptr_t)idrive_angle_egl_rpc_u32(g_rpc_payload + i * 4u);
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static EGLBoolean egl_choose_config(EGLDisplay display, const EGLint *attributes,
                                    EGLConfig *configs, EGLint config_size,
                                    EGLint *num_config)
{
    struct RpcResult reply;
    unsigned int capacity = config_size > 0 && configs ? (unsigned int)config_size : 0;
    unsigned int bytes = pack_attributes(attributes, g_request_payload,
                                        sizeof(g_request_payload));
    EGL_TRACE("IDRIVE_ANGLE_EGL_CALL name=eglChooseConfig display=0x%08x capacity=%u attributes=%u\n",
              handle_id(display), capacity, bytes);
    if (display != g_display || config_size < 0 || !bytes)
        return unsupported_egl(EGL_BAD_ATTRIBUTE);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_CHOOSE_CONFIG, 0, capacity, 0,
             g_request_payload, bytes, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    if (num_config) *num_config = (EGLint)reply.value[0];
    for (unsigned int i = 0; i < capacity && i < reply.payload_size / 4u; ++i)
        configs[i] = (EGLConfig)(uintptr_t)idrive_angle_egl_rpc_u32(g_rpc_payload + i * 4u);
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static EGLint egl_get_error(void)
{
    const unsigned int error = g_egl_error;
    g_egl_error = EGL_SUCCESS;
    return (EGLint)error;
}

static EGLDisplay egl_get_display(void *native_display)
{
    (void)native_display;
    EGL_TRACE("IDRIVE_ANGLE_EGL_CALL name=eglGetDisplay\n");
    return g_display;
}

static EGLBoolean egl_initialize(EGLDisplay display, EGLint *major, EGLint *minor)
{
    struct RpcResult reply;
    EGL_TRACE("IDRIVE_ANGLE_EGL_CALL name=eglInitialize display=0x%08x\n",
              handle_id(display));
    if (display != g_display) return unsupported_egl(EGL_BAD_DISPLAY);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_INITIALIZE, 0, 0, 0, 0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    if (major) *major = (EGLint)reply.value[0];
    if (minor) *minor = (EGLint)reply.value[1];
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static EGLBoolean egl_terminate(EGLDisplay display)
{
    struct RpcResult reply;
    if (display != g_display) return unsupported_egl(EGL_BAD_DISPLAY);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_TERMINATE, 0, 0, 0, 0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    g_current_context = EGL_NO_CONTEXT;
    g_current_draw = EGL_NO_SURFACE;
    g_current_read = EGL_NO_SURFACE;
    clear_window_surfaces();
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static const char *query_string(EGLDisplay display, EGLint name)
{
    struct RpcResult reply;
    if (display != g_display) {
        g_egl_error = EGL_BAD_DISPLAY;
        return 0;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_QUERY_STRING, (unsigned int)name, 0, 0,
             0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return 0;
    }
    if (reply.payload_size == 0 || reply.payload_size > sizeof(g_string_buffer)) {
        g_egl_error = EGL_BAD_ALLOC;
        return 0;
    }
    memcpy(g_string_buffer, g_rpc_payload, reply.payload_size);
    g_string_buffer[sizeof(g_string_buffer) - 1] = '\0';
    g_egl_error = EGL_SUCCESS;
    return g_string_buffer;
}

static EGLBoolean egl_get_config_attrib(EGLDisplay display, EGLConfig config,
                                        EGLint attribute, EGLint *value)
{
    struct RpcResult reply;
    if (display != g_display) return unsupported_egl(EGL_BAD_DISPLAY);
    if (!config || !value) return unsupported_egl(EGL_BAD_PARAMETER);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GET_CONFIG_ATTRIB, handle_id(config),
             (unsigned int)attribute, 0, 0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    *value = (EGLint)reply.value[0];
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static EGLSurface egl_create_pbuffer_surface(EGLDisplay display, EGLConfig config,
                                             const EGLint *attributes)
{
    struct RpcResult reply;
    unsigned int bytes = pack_attributes(attributes, g_request_payload,
                                        sizeof(g_request_payload));
    if (display != g_display) return (EGLSurface)unsupported_handle(EGL_BAD_DISPLAY);
    if (!config) return (EGLSurface)unsupported_handle(EGL_BAD_CONFIG);
    if (!bytes) return (EGLSurface)unsupported_handle(EGL_BAD_ATTRIBUTE);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_CREATE_PBUFFER, handle_id(config), 0, 0,
             g_request_payload, bytes, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_NO_SURFACE;
    }
    g_egl_error = EGL_SUCCESS;
    return (EGLSurface)(uintptr_t)reply.value[0];
}

static EGLContext egl_create_context(EGLDisplay display, EGLConfig config,
                                     EGLContext share, const EGLint *attributes)
{
    struct RpcResult reply;
    unsigned int bytes = pack_attributes(attributes, g_request_payload,
                                        sizeof(g_request_payload));
    if (display != g_display) return (EGLContext)unsupported_handle(EGL_BAD_DISPLAY);
    if (!config) return (EGLContext)unsupported_handle(EGL_BAD_CONFIG);
    if (!bytes) return (EGLContext)unsupported_handle(EGL_BAD_ATTRIBUTE);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_CREATE_CONTEXT, handle_id(config),
             handle_id(share), 0, g_request_payload, bytes, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_NO_CONTEXT;
    }
    g_egl_error = EGL_SUCCESS;
    return (EGLContext)(uintptr_t)reply.value[0];
}

static EGLBoolean egl_make_current(EGLDisplay display, EGLSurface draw,
                                   EGLSurface read, EGLContext context)
{
    struct RpcResult reply;
    EGL_TRACE("IDRIVE_ANGLE_EGL_CALL name=eglMakeCurrent display=0x%08x draw=0x%08x read=0x%08x context=0x%08x\n",
              handle_id(display), handle_id(draw), handle_id(read),
              handle_id(context));
    if (display != g_display) return unsupported_egl(EGL_BAD_DISPLAY);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_MAKE_CURRENT, handle_id(draw), handle_id(read),
             handle_id(context), 0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    struct ProviderThreadState *state = provider_thread_state();
    memset(state->confirmed_bind, 0, sizeof(state->confirmed_bind));
    state->current_draw = draw;
    state->current_read = read;
    state->current_context = context;
    state->egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static EGLBoolean egl_destroy_surface(EGLDisplay display, EGLSurface surface)
{
    struct RpcResult reply;
    struct WindowSurface *window_surface;
    if (display != g_display) return unsupported_egl(EGL_BAD_DISPLAY);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_DESTROY_SURFACE, handle_id(surface), 0, 0,
             0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    window_surface = find_window_surface(handle_id(surface));
    if (window_surface) memset(window_surface, 0, sizeof(*window_surface));
    if (g_current_draw == surface) g_current_draw = EGL_NO_SURFACE;
    if (g_current_read == surface) g_current_read = EGL_NO_SURFACE;
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static EGLBoolean egl_destroy_context(EGLDisplay display, EGLContext context)
{
    struct RpcResult reply;
    if (display != g_display) return unsupported_egl(EGL_BAD_DISPLAY);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_DESTROY_CONTEXT, handle_id(context), 0, 0,
             0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    if (g_current_context == context) g_current_context = EGL_NO_CONTEXT;
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static EGLBoolean egl_query_surface(EGLDisplay display, EGLSurface surface,
                                    EGLint attribute, EGLint *value)
{
    struct RpcResult reply;
    struct WindowSurface *window_surface;
    if (display != g_display) return unsupported_egl(EGL_BAD_DISPLAY);
    if (!value) return unsupported_egl(EGL_BAD_PARAMETER);
    window_surface = find_window_surface(handle_id(surface));
    if (window_surface && attribute == EGL_WIDTH) {
        *value = (EGLint)window_surface->width;
        g_egl_error = EGL_SUCCESS;
        return EGL_TRUE;
    }
    if (window_surface && attribute == EGL_HEIGHT) {
        *value = (EGLint)window_surface->height;
        g_egl_error = EGL_SUCCESS;
        return EGL_TRUE;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_QUERY_SURFACE, handle_id(surface),
             (unsigned int)attribute, 0, 0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    *value = (EGLint)reply.value[0];
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static void apply_window_swap_interval(struct WindowSurface *surface)
{
    const int immediate = g_mailbox &&
        (__atomic_load_n(&g_mailbox->features, __ATOMIC_RELAXED) &
         IDRIVE_ANGLE_MAILBOX_IMMEDIATE_POST);
    if (immediate == surface->immediate_post || surface->saved_swap_interval == -2)
        return;
    if (surface->saved_swap_interval == -1 &&
        screen_get_window_property_iv(surface->window, SCREEN_PROPERTY_SWAP_INTERVAL,
                                      &surface->saved_swap_interval) != 0) {
        surface->saved_swap_interval = -2;
        EGL_LOG("IDRIVE_ANGLE_SCREEN_INTERVAL_FAIL stage=get errno=%d\n",
                *__get_errno_ptr());
        return;
    }
    const int interval = immediate ? 0 : surface->saved_swap_interval;
    if (screen_set_window_property_iv(surface->window, SCREEN_PROPERTY_SWAP_INTERVAL,
                                      &interval) != 0) {
        surface->saved_swap_interval = -2;
        EGL_LOG("IDRIVE_ANGLE_SCREEN_INTERVAL_FAIL stage=set errno=%d\n",
                *__get_errno_ptr());
        return;
    }
    surface->immediate_post = immediate;
    EGL_LOG("IDRIVE_ANGLE_SCREEN_INTERVAL value=%d original=%d\n",
            interval, surface->saved_swap_interval);
}

static EGLBoolean egl_swap_buffers(EGLDisplay display, EGLSurface surface)
{
    struct RpcResult reply;
    struct WindowSurface *window_surface;
    EGL_TRACE("IDRIVE_ANGLE_EGL_CALL name=eglSwapBuffers display=0x%08x surface=0x%08x\n",
              handle_id(display), handle_id(surface));
    if (display != g_display) return unsupported_egl(EGL_BAD_DISPLAY);
    window_surface = find_window_surface(handle_id(surface));
    if (window_surface) {
        void *available[IDRIVE_SCREEN_MAX_BUFFERS] = { 0 };
        unsigned int index = 0;
        unsigned char payload[16];
        int damage[4];
        uint64_t started, buffer_done, rpc_done;
        apply_window_swap_interval(window_surface);
        started = g_mailbox ? ClockCycles() : 0;
        /* Screen owns the front/back transition. The buffer available after
         * a post can differ from the next entry in the initial allocation. */
        if (screen_get_window_property_pv(window_surface->window,
                                          SCREEN_PROPERTY_RENDER_BUFFERS,
                                          available) != 0) {
            EGL_LOG("IDRIVE_ANGLE_SCREEN_POST_FAIL stage=render_buffers errno=%d\n",
                      *__get_errno_ptr());
            return unsupported_egl(EGL_BAD_SURFACE);
        }
        while (index < window_surface->count &&
               window_surface->buffers[index] != available[0])
            ++index;
        if (index == window_surface->count) {
            EGL_LOG("IDRIVE_ANGLE_SCREEN_POST_FAIL stage=unavailable_buffer\n");
            return unsupported_egl(EGL_BAD_SURFACE);
        }
        const uint64_t address = window_surface->physical_address[index];
        idrive_angle_egl_rpc_put_u32(payload, window_surface->stride[index]);
        idrive_angle_egl_rpc_put_u32(payload + 4, SCREEN_FORMAT_RGBA8888);
        idrive_angle_egl_rpc_put_u32(payload + 8, (unsigned int)address);
        idrive_angle_egl_rpc_put_u32(payload + 12, (unsigned int)(address >> 32));
        buffer_done = g_mailbox ? ClockCycles() : 0;
        if (!rpc(IDRIVE_ANGLE_EGL_RPC_SWAP_WINDOW_SURFACE,
                 window_surface->id, window_surface->width,
                 window_surface->height, payload, sizeof(payload), &reply)) {
            g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
            return EGL_FALSE;
        }
        rpc_done = g_mailbox ? ClockCycles() : 0;
        damage[0] = 0;
        damage[1] = 0;
        damage[2] = (int)window_surface->width;
        damage[3] = (int)window_surface->height;
        if (screen_post_window(window_surface->window, available[0], 1, damage, 0) != 0) {
            EGL_LOG("IDRIVE_ANGLE_SCREEN_POST_FAIL stage=post errno=%d\n",
                      *__get_errno_ptr());
            return unsupported_egl(EGL_BAD_SURFACE);
        }
        if (g_mailbox) {
            g_mailbox->screen_buffer_cycles = (unsigned int)(buffer_done - started);
            g_mailbox->screen_rpc_cycles = (unsigned int)(rpc_done - buffer_done);
            g_mailbox->screen_post_cycles = (unsigned int)(ClockCycles() - rpc_done);
            const unsigned int count =
                __atomic_fetch_add(&g_mailbox->screen_posts, 1, __ATOMIC_RELEASE);
            if (count == 0)
                EGL_LOG("IDRIVE_ANGLE_SCREEN_POST physical=0x%llx\n",
                        (unsigned long long)address);
            else
                EGL_TRACE("IDRIVE_ANGLE_SCREEN_POST physical=0x%llx\n",
                          (unsigned long long)address);
        } else {
            EGL_LOG("IDRIVE_ANGLE_SCREEN_POST physical=0x%llx\n",
                    (unsigned long long)address);
        }
        g_egl_error = EGL_SUCCESS;
        return EGL_TRUE;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_SWAP_BUFFERS, handle_id(surface), 0, 0,
             0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static EGLSurface egl_create_window_surface(EGLDisplay display, EGLConfig config,
                                            void *native_window,
                                            const EGLint *attributes)
{
    struct WindowSurface local;
    struct WindowSurface *slot;
    struct RpcResult reply;
    int dimensions[2] = { 0, 0 };
    int usage = 0, count = 0;
    void *buffers[IDRIVE_SCREEN_MAX_BUFFERS] = { 0 };
    unsigned int i;

    EGL_TRACE("IDRIVE_ANGLE_EGL_CALL name=eglCreateWindowSurface display=0x%08x config=0x%08x window=0x%08x\n",
              handle_id(display), handle_id(config), handle_id(native_window));
    if (display != g_display) return (EGLSurface)unsupported_handle(EGL_BAD_DISPLAY);
    if (!config) return (EGLSurface)unsupported_handle(EGL_BAD_CONFIG);
    if (!native_window) return (EGLSurface)unsupported_handle(EGL_BAD_NATIVE_WINDOW);
    if (attributes) {
        for (i = 0; i < 32 && attributes[i] != EGL_NONE; i += 2) {
            if (i + 1 >= 32 || attributes[i + 1] == EGL_NONE ||
                attributes[i] != EGL_RENDER_BUFFER ||
                attributes[i + 1] != EGL_BACK_BUFFER)
                return (EGLSurface)unsupported_handle(EGL_BAD_ATTRIBUTE);
        }
        if (i >= 32) return (EGLSurface)unsupported_handle(EGL_BAD_ATTRIBUTE);
    }
    if (screen_get_window_property_iv(native_window, SCREEN_PROPERTY_BUFFER_SIZE,
                                      dimensions) != 0 ||
        screen_get_window_property_iv(native_window, SCREEN_PROPERTY_USAGE,
                                      &usage) != 0 ||
        screen_get_window_property_iv(native_window,
                                      SCREEN_PROPERTY_RENDER_BUFFER_COUNT,
                                      &count) != 0 ||
        dimensions[0] <= 0 || dimensions[1] <= 0 ||
        (usage & SCREEN_USAGE_OPENGL_ES2) == 0 ||
        count <= 0 || count > IDRIVE_SCREEN_MAX_BUFFERS ||
        (uint64_t)(unsigned int)dimensions[0] *
            (uint64_t)(unsigned int)dimensions[1] * 4u >
            IDRIVE_ANGLE_EGL_RPC_MAX_FRAME_BYTES)
        return (EGLSurface)unsupported_handle(EGL_BAD_NATIVE_WINDOW);

    if (!resize_native_window(native_window, dimensions, count) ||
        screen_get_window_property_iv(native_window,
                                      SCREEN_PROPERTY_BUFFER_SIZE,
                                      dimensions) != 0 ||
        screen_get_window_property_pv(native_window,
                                      SCREEN_PROPERTY_RENDER_BUFFERS,
                                      (void **)buffers) != 0 ||
        dimensions[0] <= 0 || dimensions[1] <= 0 ||
        (uint64_t)(unsigned int)dimensions[0] *
            (uint64_t)(unsigned int)dimensions[1] * 4u >
            IDRIVE_ANGLE_EGL_RPC_MAX_FRAME_BYTES)
        return (EGLSurface)unsupported_handle(EGL_BAD_NATIVE_WINDOW);

    memset(&local, 0, sizeof(local));
    local.window = native_window;
    local.saved_swap_interval = -1;
    local.width = (unsigned int)dimensions[0];
    local.height = (unsigned int)dimensions[1];
    local.count = (unsigned int)count;
    for (i = 0; i < local.count; ++i) {
        int format = -1, size[2] = { 0, 0 }, stride = 0, contiguous = 0;
        int64_t physical = 0;
        if (!buffers[i] ||
            screen_get_buffer_property_iv(buffers[i], SCREEN_PROPERTY_FORMAT,
                                          &format) != 0 ||
            screen_get_buffer_property_iv(buffers[i],
                                          SCREEN_PROPERTY_BUFFER_SIZE,
                                          size) != 0 ||
            screen_get_buffer_property_iv(buffers[i], SCREEN_PROPERTY_STRIDE,
                                          &stride) != 0 ||
            screen_get_buffer_property_iv(buffers[i],
                                          SCREEN_PROPERTY_PHYSICALLY_CONTIGUOUS,
                                          &contiguous) != 0 ||
            screen_get_buffer_property_llv(buffers[i],
                                           SCREEN_PROPERTY_PHYSICAL_ADDRESS,
                                           &physical) != 0 ||
            format != SCREEN_FORMAT_RGBA8888 ||
            size[0] != dimensions[0] || size[1] != dimensions[1] ||
            stride < dimensions[0] * 4 || contiguous != 1 || physical <= 0)
            return (EGLSurface)unsupported_handle(EGL_BAD_NATIVE_WINDOW);
        local.buffers[i] = buffers[i];
        local.physical_address[i] = (uint64_t)physical;
        local.stride[i] = (unsigned int)stride;
    }

    if (!rpc(IDRIVE_ANGLE_EGL_RPC_CREATE_WINDOW_SURFACE,
             handle_id(config), local.width, local.height, 0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_NO_SURFACE;
    }
    local.id = reply.value[0];
    if (!local.id || !(slot = allocate_window_surface())) {
        (void)rpc(IDRIVE_ANGLE_EGL_RPC_DESTROY_SURFACE, local.id,
                  0, 0, 0, 0, &reply);
        return (EGLSurface)unsupported_handle(EGL_BAD_ALLOC);
    }
    /* QNX libc exports memcpy, while Clang can lower a struct assignment
     * to an ARM EABI helper absent from this guest. */
    memcpy(slot, &local, sizeof(local));
    EGL_LOG("IDRIVE_ANGLE_SCREEN_BUFFERS count=%u width=%u height=%u\n",
            local.count, local.width, local.height);
    g_egl_error = EGL_SUCCESS;
    return (EGLSurface)(uintptr_t)local.id;
}

static EGLSurface egl_create_pixmap_surface(EGLDisplay display, EGLConfig config,
                                            void *native_pixmap,
                                            const EGLint *attributes)
{
    (void)config;
    (void)native_pixmap;
    (void)attributes;
    return (EGLSurface)unsupported_handle(display == g_display
        ? EGL_BAD_NATIVE_PIXMAP : EGL_BAD_DISPLAY);
}

static EGLBoolean egl_wait_client(void)
{
    return unsupported_egl(EGL_BAD_MATCH);
}

static EGLBoolean egl_release_thread(void)
{
    if (g_current_context != EGL_NO_CONTEXT) {
        struct RpcResult reply;
        if (!rpc(IDRIVE_ANGLE_EGL_RPC_MAKE_CURRENT, 0, 0, 0, 0, 0, &reply)) {
            g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
            return EGL_FALSE;
        }
    }
    g_current_context = EGL_NO_CONTEXT;
    g_current_draw = EGL_NO_SURFACE;
    g_current_read = EGL_NO_SURFACE;
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

static EGLSurface egl_create_pbuffer_from_client_buffer(EGLDisplay display,
                                                         EGLenum buffer_type,
                                                         EGLClientBuffer buffer,
                                                         EGLConfig config,
                                                         const EGLint *attributes)
{
    (void)buffer_type;
    (void)buffer;
    (void)config;
    (void)attributes;
    return (EGLSurface)unsupported_handle(display == g_display
        ? EGL_BAD_PARAMETER : EGL_BAD_DISPLAY);
}

static EGLBoolean egl_surface_attrib(EGLDisplay display, EGLSurface surface,
                                     EGLint attribute, EGLint value)
{
    (void)surface;
    (void)attribute;
    (void)value;
    return unsupported_egl(display == g_display ? EGL_BAD_MATCH : EGL_BAD_DISPLAY);
}

static EGLBoolean egl_bind_tex_image(EGLDisplay display, EGLSurface surface,
                                     EGLint buffer)
{
    (void)surface;
    (void)buffer;
    return unsupported_egl(display == g_display ? EGL_BAD_MATCH : EGL_BAD_DISPLAY);
}

static EGLBoolean egl_release_tex_image(EGLDisplay display, EGLSurface surface,
                                        EGLint buffer)
{
    (void)surface;
    (void)buffer;
    return unsupported_egl(display == g_display ? EGL_BAD_MATCH : EGL_BAD_DISPLAY);
}

static EGLBoolean egl_swap_interval(EGLDisplay display, EGLint interval)
{
    (void)interval;
    return unsupported_egl(display == g_display ? EGL_BAD_MATCH : EGL_BAD_DISPLAY);
}

static EGLBoolean egl_wait_gl(void)
{
    return unsupported_egl(EGL_BAD_MATCH);
}

static EGLBoolean egl_wait_native(EGLint engine)
{
    (void)engine;
    return unsupported_egl(EGL_BAD_MATCH);
}

static EGLBoolean egl_copy_buffers(EGLDisplay display, EGLSurface surface,
                                   void *native_pixmap)
{
    (void)surface;
    (void)native_pixmap;
    return unsupported_egl(display == g_display ? EGL_BAD_MATCH : EGL_BAD_DISPLAY);
}

static EGLBoolean egl_query_context(EGLDisplay display, EGLContext context,
                                    EGLint attribute, EGLint *value)
{
    struct RpcResult reply;
    if (display != g_display) return unsupported_egl(EGL_BAD_DISPLAY);
    if (!value) return unsupported_egl(EGL_BAD_PARAMETER);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_QUERY_CONTEXT, handle_id(context),
             (unsigned int)attribute, 0, 0, 0, &reply)) {
        g_egl_error = reply.error ? reply.error : EGL_BAD_ALLOC;
        return EGL_FALSE;
    }
    *value = (EGLint)reply.value[0];
    g_egl_error = EGL_SUCCESS;
    return EGL_TRUE;
}

unsigned int glGetError(void)
{
    struct ProviderThreadState *state = provider_thread_state();
    unsigned int error;
    lock_flag(&g_rpc_lock);
    if (g_batch_owner == state) flush_batch_locked();
    error = state->batch_error;
    state->batch_error = GL_NO_ERROR;
    unlock_flag(&g_rpc_lock);
    if (error) return error;
    error = state->gl_error;
    state->gl_error = GL_NO_ERROR;
    return error;
}

const unsigned char *glGetString(unsigned int name)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return 0;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_GET_STRING, name, 0, 0, 0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return 0;
    }
    if (reply.payload_size == 0 || reply.payload_size > sizeof(g_string_buffer)) {
        g_gl_error = GL_INVALID_OPERATION;
        return 0;
    }
    memcpy(g_string_buffer, g_rpc_payload, reply.payload_size);
    g_string_buffer[sizeof(g_string_buffer) - 1] = '\0';
    g_gl_error = GL_NO_ERROR;
    return (const unsigned char *)g_string_buffer;
}

void glViewport(int x, int y, int width, int height)
{
    unsigned char payload[16];
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    idrive_angle_egl_rpc_put_u32(payload, (unsigned int)x);
    idrive_angle_egl_rpc_put_u32(payload + 4, (unsigned int)y);
    idrive_angle_egl_rpc_put_u32(payload + 8, (unsigned int)width);
    idrive_angle_egl_rpc_put_u32(payload + 12, (unsigned int)height);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_VIEWPORT, 0, 0, 0,
             payload, sizeof(payload), &reply))
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
    else
        g_gl_error = GL_NO_ERROR;
}

void glClearColor(float red, float green, float blue, float alpha)
{
    float values[4];
    unsigned char payload[16];
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    values[0] = red; values[1] = green; values[2] = blue; values[3] = alpha;
    for (unsigned int i = 0; i < 4; ++i) {
        unsigned int bits = 0;
        memcpy(&bits, &values[i], sizeof(bits));
        idrive_angle_egl_rpc_put_u32(payload + i * 4u, bits);
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_COLOR, 0, 0, 0,
             payload, sizeof(payload), &reply))
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
    else
        g_gl_error = GL_NO_ERROR;
}

void glClear(unsigned int mask)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_CLEAR, mask, 0, 0, 0, 0, &reply))
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
    else
        g_gl_error = GL_NO_ERROR;
}

static void gen_gl_objects(unsigned int opcode, const char *function,
                           int count, unsigned int *objects)
{
    struct RpcResult reply;
    unsigned int offset;
    (void)function;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (count < 0 || (count > 0 && !objects)) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=%s count=%d\n",
              function, count);
    if (!rpc(opcode, (unsigned int)count, 0, 0, 0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    if (reply.payload_size != (unsigned int)count * 4u) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    for (offset = 0; offset < reply.payload_size; offset += 4u)
        objects[offset / 4u] = idrive_angle_egl_rpc_u32(g_rpc_payload + offset);
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=%s count=%d first=%u\n",
              function, count, count ? objects[0] : 0);
}

void glGenBuffers(int count, unsigned int *buffers)
{
    gen_gl_objects(IDRIVE_ANGLE_EGL_RPC_GL_GEN_BUFFERS, "glGenBuffers",
                   count, buffers);
}

void glGenTextures(int count, unsigned int *textures)
{
    gen_gl_objects(IDRIVE_ANGLE_EGL_RPC_GL_GEN_TEXTURES, "glGenTextures",
                   count, textures);
}

unsigned int glCreateShader(unsigned int type)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return 0;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glCreateShader type=0x%04x\n",
              type);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_CREATE_SHADER, type, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return 0;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glCreateShader type=0x%04x shader=%u\n",
              type, reply.value[0]);
    return reply.value[0];
}

unsigned int glCreateProgram(void)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return 0;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glCreateProgram\n");
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_CREATE_PROGRAM, 0, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return 0;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glCreateProgram program=%u\n",
              reply.value[0]);
    return reply.value[0];
}

void glAttachShader(unsigned int program, unsigned int shader)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!program || !shader) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glAttachShader program=%u shader=%u\n",
              program, shader);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_ATTACH_SHADER, program, shader, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glAttachShader program=%u shader=%u error=0x%04x\n",
                  program, shader, g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glAttachShader program=%u shader=%u\n",
              program, shader);
}

void glLinkProgram(unsigned int program)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!program) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glLinkProgram program=%u\n",
              program);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_LINK_PROGRAM, program, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glLinkProgram program=%u error=0x%04x\n",
                  program, g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glLinkProgram program=%u\n",
              program);
}

static int bind_gl_object(unsigned int opcode, const char *function,
                          unsigned int target, unsigned int object,
                          unsigned int batch_features)
{
    struct RpcResult reply;
    (void)function;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return 0;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=%s target=0x%04x object=%u\n",
              function, target, object);
    if (!rpc_ordered(opcode, target, object, 0, 0, 0, &reply, batch_features)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return 0;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=%s target=0x%04x object=%u\n",
              function, target, object);
    return 1;
}

void glBindBuffer(unsigned int target, unsigned int buffer)
{
    struct ProviderThreadState *state = provider_thread_state();
    unsigned int *confirmed = 0;
    unsigned int batch_features = 0;
    if (target == GL_ARRAY_BUFFER || target == GL_ELEMENT_ARRAY_BUFFER) {
        const unsigned int slot = target == GL_ELEMENT_ARRAY_BUFFER;
        confirmed = &state->confirmed_bind[slot][buffer % kBindCacheSlots];
        /* Zero unbinds a supported target. Other names need a successful
         * synchronous bind before we use them to pack guest pointer arguments. */
        if (buffer == 0 || *confirmed == buffer)
            batch_features = IDRIVE_ANGLE_MAILBOX_BATCH | IDRIVE_ANGLE_MAILBOX_BATCH_BIND;
    }
    if (bind_gl_object(IDRIVE_ANGLE_EGL_RPC_GL_BIND_BUFFER, "glBindBuffer",
                       target, buffer, batch_features)) {
        if (confirmed) *confirmed = buffer;
        if (target == GL_ARRAY_BUFFER) state->bound_array_buffer = buffer;
        if (target == GL_ELEMENT_ARRAY_BUFFER) state->bound_element_array_buffer = buffer;
    }
}

void glBindTexture(unsigned int target, unsigned int texture)
{
    (void)bind_gl_object(IDRIVE_ANGLE_EGL_RPC_GL_BIND_TEXTURE, "glBindTexture",
                         target, texture, IDRIVE_ANGLE_MAILBOX_BATCH);
}

void glShaderBinary(int count, const unsigned int *shaders,
                    unsigned int binary_format, const void *binary,
                    int length)
{
    struct RpcResult reply;
    unsigned int ids_size;
    unsigned int payload_size;
    unsigned int i;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (count < 0 || length < 0 || (count > 0 && !shaders) ||
        (length > 0 && !binary)) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    if ((unsigned int)count > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / 4u) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    ids_size = (unsigned int)count * 4u;
    if (ids_size > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD ||
        (unsigned int)length > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD - ids_size) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    payload_size = ids_size + (unsigned int)length;
    for (i = 0; i < (unsigned int)count; ++i)
        idrive_angle_egl_rpc_put_u32(g_rpc_payload + i * 4u, shaders[i]);
    if (length > 0)
        memcpy(g_rpc_payload + ids_size, binary, (unsigned int)length);
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glShaderBinary count=%d format=0x%08x length=%d\n",
              count, binary_format, length);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_SHADER_BINARY_CAPTURE,
             (unsigned int)count, binary_format, (unsigned int)length,
             g_rpc_payload, payload_size, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glShaderBinary error=0x%04x captured=unknown\n",
                  g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glShaderBinary captured=1\n");
}

void glShaderSource(unsigned int shader, int count,
                    const char *const *strings, const int *lengths)
{
    struct RpcResult reply;
    unsigned int offset = 0;
    unsigned int i;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!shader || count <= 0 || !strings ||
        (unsigned int)count > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / 4u) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    for (i = 0; i < (unsigned int)count; ++i) {
        size_t length;
        if (!strings[i] || (lengths && lengths[i] < -1)) {
            g_gl_error = GL_INVALID_VALUE;
            return;
        }
        if (lengths && lengths[i] >= 0)
            length = (size_t)lengths[i];
        else
            length = strlen(strings[i]);
        if (offset > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD - 4u ||
            length > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD - offset - 4u) {
            g_gl_error = GL_INVALID_VALUE;
            return;
        }
        idrive_angle_egl_rpc_put_u32(g_rpc_payload + offset,
                                     (unsigned int)length);
        offset += 4u;
        if (length) memcpy(g_rpc_payload + offset, strings[i], (unsigned int)length);
        offset += (unsigned int)length;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glShaderSource shader=%u count=%d bytes=%u\n",
              shader, count, offset);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_SHADER_SOURCE, shader,
             (unsigned int)count, offset, g_rpc_payload, offset, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glShaderSource error=0x%04x\n",
                  g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glShaderSource shader=%u count=%d\n",
              shader, count);
}

void glBufferData(unsigned int target, int size, const void *data,
                  unsigned int usage)
{
    struct RpcResult reply;
    unsigned int payload_size;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (size < 0 || (unsigned int)size > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    payload_size = data ? (unsigned int)size : 0;
    if (payload_size) memcpy(g_rpc_payload, data, payload_size);
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glBufferData target=0x%04x size=%d usage=0x%04x data=%u\n",
              target, size, usage, data != 0);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_BUFFER_DATA, target,
             (unsigned int)size, usage, g_rpc_payload, payload_size, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glBufferData error=0x%04x\n",
                  g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glBufferData size=%d\n", size);
}

void glBufferSubData(unsigned int target, int offset, int size,
                     const void *data)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (offset < 0 || size < 0 ||
        (unsigned int)size > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD ||
        (size > 0 && !data)) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    if (size > 0) memcpy(g_rpc_payload, data, (unsigned int)size);
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glBufferSubData target=0x%04x offset=%d size=%d data=%u\n",
              target, offset, size, data != 0);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_BUFFER_SUB_DATA, target,
             (unsigned int)offset, (unsigned int)size,
             g_rpc_payload, (unsigned int)size, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glBufferSubData error=0x%04x\n",
                  g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glTexParameteri(unsigned int target, unsigned int pname, int param)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glTexParameteri target=0x%04x pname=0x%04x param=%d\n",
              target, pname, param);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_TEX_PARAMETERI, target, pname,
             (unsigned int)param, 0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glPixelStorei(unsigned int pname, int param)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glPixelStorei pname=0x%04x param=%d\n",
              pname, param);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_PIXEL_STOREI, pname,
             (unsigned int)param, 0, 0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    if (pname == GL_UNPACK_ALIGNMENT &&
        (param == 1 || param == 2 || param == 4 || param == 8))
        g_unpack_alignment = (unsigned int)param;
    g_gl_error = GL_NO_ERROR;
}

static unsigned int texture_components(unsigned int format)
{
    switch (format) {
    case GL_ALPHA:
    case GL_LUMINANCE:
        return 1;
    case GL_LUMINANCE_ALPHA:
        return 2;
    case GL_RGB:
        return 3;
    case GL_RGBA:
        return 4;
    default:
        return 0;
    }
}

static int texture_upload_size(int width, int height, unsigned int format,
                               unsigned int type, unsigned int *byte_count)
{
    uint64_t row_bytes;
    uint64_t row_stride;
    uint64_t total;
    unsigned int components = texture_components(format);
    unsigned int element_size;
    if (width < 0 || height < 0 || !components || !byte_count) return 0;
    if (type == GL_UNSIGNED_SHORT_4_4_4_4 ||
        type == GL_UNSIGNED_SHORT_5_5_5_1 ||
        type == GL_UNSIGNED_SHORT_5_6_5) {
        element_size = 2;
        components = 1;
    } else {
        switch (type) {
        case GL_BYTE:
        case GL_UNSIGNED_BYTE: element_size = 1; break;
        case GL_SHORT:
        case GL_UNSIGNED_SHORT: element_size = 2; break;
        case GL_INT:
        case GL_UNSIGNED_INT:
        case GL_FLOAT: element_size = 4; break;
        default: return 0;
        }
    }
    row_bytes = (uint64_t)(unsigned int)width * components * element_size;
    row_stride = (row_bytes + g_unpack_alignment - 1u) &
                 ~((uint64_t)g_unpack_alignment - 1u);
    if (height > 1 && row_stride >
        (IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD - 32u) /
        ((unsigned int)height - 1u)) return 0;
    total = height == 0 ? 0 : row_stride * ((unsigned int)height - 1u) + row_bytes;
    if (total > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD - 32u) return 0;
    *byte_count = (unsigned int)total;
    return 1;
}

void glTexImage2D(unsigned int target, int level, int internal_format,
                  int width, int height, int border, unsigned int format,
                  unsigned int type, const void *pixels)
{
    unsigned char *payload = g_rpc_payload;
    struct RpcResult reply;
    unsigned int pixel_bytes = 0;
    unsigned int payload_size = 32;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (width < 0 || height < 0 || border < 0 ||
        (pixels && !texture_upload_size(width, height, format, type,
                                        &pixel_bytes))) {
        g_gl_error = GL_INVALID_VALUE;
        EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glTexImage2D target=0x%04x level=%d size=%dx%d format=0x%04x type=0x%04x data=%u rejected=1\n",
                  target, level, width, height, format, type, pixels != 0);
        return;
    }
    idrive_angle_egl_rpc_put_u32(payload, target);
    idrive_angle_egl_rpc_put_u32(payload + 4, (unsigned int)level);
    idrive_angle_egl_rpc_put_u32(payload + 8, (unsigned int)internal_format);
    idrive_angle_egl_rpc_put_u32(payload + 12, (unsigned int)width);
    idrive_angle_egl_rpc_put_u32(payload + 16, (unsigned int)height);
    idrive_angle_egl_rpc_put_u32(payload + 20, (unsigned int)border);
    idrive_angle_egl_rpc_put_u32(payload + 24, format);
    idrive_angle_egl_rpc_put_u32(payload + 28, type);
    if (pixels && pixel_bytes) {
        memcpy(payload + 32, pixels, pixel_bytes);
        payload_size += pixel_bytes;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glTexImage2D target=0x%04x level=%d size=%dx%d format=0x%04x type=0x%04x data=%u upload_bytes=%u\n",
              target, level, width, height, format, type, pixels != 0,
              pixel_bytes);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_TEX_IMAGE_2D, target,
             (unsigned int)level, (unsigned int)width,
             payload, payload_size, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glTexImage2D error=0x%04x\n",
                  g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glTexSubImage2D(unsigned int target, int level, int xoffset, int yoffset,
                     int width, int height, unsigned int format,
                     unsigned int type, const void *pixels)
{
    unsigned char *payload = g_rpc_payload;
    struct RpcResult reply;
    unsigned int pixel_bytes = 0;
    unsigned int payload_size = 32;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (level < 0 || xoffset < 0 || yoffset < 0 || width < 0 || height < 0 ||
        (pixels && !texture_upload_size(width, height, format, type,
                                        &pixel_bytes))) {
        g_gl_error = GL_INVALID_VALUE;
        EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glTexSubImage2D target=0x%04x level=%d offset=%d,%d size=%dx%d format=0x%04x type=0x%04x data=%u rejected=1\n",
                  target, level, xoffset, yoffset, width, height, format,
                  type, pixels != 0);
        return;
    }
    idrive_angle_egl_rpc_put_u32(payload, target);
    idrive_angle_egl_rpc_put_u32(payload + 4, (unsigned int)level);
    idrive_angle_egl_rpc_put_u32(payload + 8, (unsigned int)xoffset);
    idrive_angle_egl_rpc_put_u32(payload + 12, (unsigned int)yoffset);
    idrive_angle_egl_rpc_put_u32(payload + 16, (unsigned int)width);
    idrive_angle_egl_rpc_put_u32(payload + 20, (unsigned int)height);
    idrive_angle_egl_rpc_put_u32(payload + 24, format);
    idrive_angle_egl_rpc_put_u32(payload + 28, type);
    if (pixels && pixel_bytes) {
        memcpy(payload + 32, pixels, pixel_bytes);
        payload_size += pixel_bytes;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glTexSubImage2D target=0x%04x level=%d offset=%d,%d size=%dx%d format=0x%04x type=0x%04x data=%u upload_bytes=%u\n",
              target, level, xoffset, yoffset, width, height, format, type,
              pixels != 0, pixel_bytes);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_TEX_SUB_IMAGE_2D, target,
             (unsigned int)level, (unsigned int)width,
             payload, payload_size, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glTexSubImage2D error=0x%04x\n",
                  g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glCompileShader(unsigned int shader)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!shader) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glCompileShader shader=%u\n", shader);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_COMPILE_SHADER, shader, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glCompileShader shader=%u error=0x%04x\n",
                  shader, g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glGetShaderiv(unsigned int shader, unsigned int pname, int *params)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!shader || !params) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_GET_SHADER_IV, shader, pname, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    *params = (int)reply.value[0];
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetShaderiv shader=%u pname=0x%04x value=%d\n",
              shader, pname, *params);
}

void glGetProgramiv(unsigned int program, unsigned int pname, int *params)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!program || !params) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glGetProgramiv program=%u pname=0x%04x\n",
              program, pname);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_GET_PROGRAM_IV, program, pname, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetProgramiv program=%u pname=0x%04x error=0x%04x\n",
                  program, pname, g_gl_error);
        return;
    }
    *params = (int)reply.value[0];
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetProgramiv program=%u pname=0x%04x value=%d\n",
              program, pname, *params);
}

void glGetProgramInfoLog(unsigned int program, int bufsize, int *length,
                         char *infolog)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!program || bufsize < 0 || (bufsize > 0 && !infolog)) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glGetProgramInfoLog program=%u bufsize=%d\n",
              program, bufsize);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_GET_PROGRAM_INFO_LOG, program,
             (unsigned int)bufsize, 0, 0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetProgramInfoLog program=%u error=0x%04x\n",
                  program, g_gl_error);
        return;
    }
    if (reply.payload_size > (unsigned int)bufsize) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (length) *length = (int)reply.value[0];
    if (reply.payload_size && infolog)
        memcpy(infolog, g_rpc_payload, reply.payload_size);
    if (infolog && bufsize > (int)reply.payload_size)
        infolog[reply.payload_size] = '\0';
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetProgramInfoLog program=%u length=%u\n",
              program, reply.payload_size);
}

static void get_active_program_symbol(unsigned int opcode,
                                      const char *function,
                                      unsigned int program,
                                      unsigned int index,
                                      int bufsize,
                                      int *length,
                                      int *size,
                                      unsigned int *type,
                                      char *name)
{
    struct RpcResult reply;
    (void)function;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!program || bufsize < 0 || (bufsize > 0 && !name)) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=%s program=%u index=%u bufsize=%d\n",
              function, program, index, bufsize);
    if (!rpc(opcode, program, index, (unsigned int)bufsize,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    if (reply.value[0] > reply.payload_size ||
        reply.payload_size > (unsigned int)bufsize ||
        (bufsize > 0 && reply.payload_size >= (unsigned int)bufsize)) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (length) *length = (int)reply.value[0];
    if (size) *size = (int)reply.value[1];
    if (type) *type = reply.value[2];
    if (name && bufsize > 0) {
        memcpy(name, g_rpc_payload, reply.payload_size);
        name[reply.payload_size] = '\0';
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=%s program=%u index=%u length=%u size=%u type=0x%04x name=%s\n",
              function, program, index, reply.value[0], reply.value[1],
              reply.value[2], name ? name : "");
}

void glGetActiveUniform(unsigned int program, unsigned int index, int bufsize,
                        int *length, int *size, unsigned int *type, char *name)
{
    get_active_program_symbol(IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_UNIFORM,
                              "glGetActiveUniform", program, index, bufsize,
                              length, size, type, name);
}

void glGetActiveAttrib(unsigned int program, unsigned int index, int bufsize,
                       int *length, int *size, unsigned int *type, char *name)
{
    get_active_program_symbol(IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_ATTRIB,
                              "glGetActiveAttrib", program, index, bufsize,
                              length, size, type, name);
}

static int get_program_location(unsigned int opcode, const char *function,
                                unsigned int program, const char *name)
{
    struct RpcResult reply;
    unsigned int length = 0;
    (void)function;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return -1;
    }
    if (!program || !name) {
        g_gl_error = GL_INVALID_VALUE;
        return -1;
    }
    while (length < IDRIVE_ANGLE_EGL_RPC_MAX_STRING_BYTES && name[length])
        ++length;
    if (length == IDRIVE_ANGLE_EGL_RPC_MAX_STRING_BYTES) {
        g_gl_error = GL_INVALID_VALUE;
        return -1;
    }
    memcpy(g_string_buffer, name, length);
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=%s program=%u name=%.*s\n",
              function, program, (int)length, g_string_buffer);
    if (!rpc(opcode, program, length, 0,
             (const unsigned char *)g_string_buffer, length, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return -1;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=%s program=%u location=%d\n",
              function, program, (int)reply.value[0]);
    return (int)reply.value[0];
}

int glGetAttribLocation(unsigned int program, const char *name)
{
    return get_program_location(IDRIVE_ANGLE_EGL_RPC_GL_GET_ATTRIB_LOCATION,
                                "glGetAttribLocation", program, name);
}

int glGetUniformLocation(unsigned int program, const char *name)
{
    return get_program_location(IDRIVE_ANGLE_EGL_RPC_GL_GET_UNIFORM_LOCATION,
                                "glGetUniformLocation", program, name);
}

void glUseProgram(unsigned int program)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glUseProgram program=%u\n", program);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_USE_PROGRAM, program, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    g_gl_error = GL_NO_ERROR;
    EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glUseProgram program=%u\n", program);
}

static void set_vertex_attrib_array(unsigned int opcode, const char *function,
                                    unsigned int index)
{
    struct RpcResult reply;
    (void)function;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=%s index=%u\n", function, index);
    if (!rpc(opcode, index, 0, 0, 0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glEnableVertexAttribArray(unsigned int index)
{
    set_vertex_attrib_array(IDRIVE_ANGLE_EGL_RPC_GL_ENABLE_VERTEX_ATTRIB_ARRAY,
                            "glEnableVertexAttribArray", index);
}

void glDisableVertexAttribArray(unsigned int index)
{
    set_vertex_attrib_array(IDRIVE_ANGLE_EGL_RPC_GL_DISABLE_VERTEX_ATTRIB_ARRAY,
                            "glDisableVertexAttribArray", index);
}

void glVertexAttribPointer(unsigned int index, int size, unsigned int type,
                           unsigned char normalized, int stride,
                           const void *pointer)
{
    unsigned char payload[12];
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!g_bound_array_buffer) {
        g_gl_error = GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_UNSUPPORTED_GLES function=glVertexAttribPointer mode=client-array error=0x%04x\n",
                  g_gl_error);
        return;
    }
    if (size < 1 || size > 4 || stride < 0 || normalized > 1) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    idrive_angle_egl_rpc_put_u32(payload, normalized);
    idrive_angle_egl_rpc_put_u32(payload + 4, (unsigned int)stride);
    idrive_angle_egl_rpc_put_u32(payload + 8, (unsigned int)(uintptr_t)pointer);
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glVertexAttribPointer index=%u size=%d type=0x%04x normalized=%u stride=%d offset=0x%08x array_buffer=%u\n",
              index, size, type, normalized, stride,
              (unsigned int)(uintptr_t)pointer, g_bound_array_buffer);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_VERTEX_ATTRIB_POINTER, index,
             (unsigned int)size, type, payload, sizeof(payload), &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glUniform1i(int location, int value)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glUniform1i location=%d value=%d\n",
              location, value);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1I, (unsigned int)location,
             (unsigned int)value, 0, 0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glUniform1iv(int location, int count, const int *value)
{
    struct RpcResult reply;
    unsigned int payload_size;
    unsigned int i;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (count < 0 || (count > 0 && !value) ||
        (unsigned int)count > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / 4u) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    payload_size = (unsigned int)count * 4u;
    for (i = 0; i < (unsigned int)count; ++i)
        idrive_angle_egl_rpc_put_u32(g_rpc_payload + i * 4u,
                                     (unsigned int)value[i]);
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glUniform1iv location=%d count=%d\n",
              location, count);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1IV,
             (unsigned int)location, (unsigned int)count, 0,
             g_rpc_payload, payload_size, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glUniform1iv error=0x%04x\n",
                  g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

static void uniform_float_values(const char *function, int location, int count,
                                 unsigned int components, const float *value,
                                 unsigned int matrix_dimension,
                                 unsigned char transpose)
{
    struct RpcResult reply;
    unsigned int value_count;
    unsigned int payload_offset = 0;
    unsigned int payload_size;
    unsigned int i;
    unsigned int opcode;
    (void)function;

    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (count < 0 || (count > 0 && !value) ||
        (matrix_dimension && transpose != 0)) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    value_count = matrix_dimension
        ? matrix_dimension * matrix_dimension
        : components;
    if (value_count == 0 ||
        (unsigned int)count >
            (IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD -
             (matrix_dimension ? 4u : 0u)) / (value_count * 4u)) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    if (matrix_dimension) {
        idrive_angle_egl_rpc_put_u32(g_rpc_payload, transpose ? 1u : 0u);
        payload_offset = 4u;
        opcode = IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_MATRIX_FV;
    } else {
        opcode = IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_FV;
    }
    payload_size = payload_offset + (unsigned int)count * value_count * 4u;
    for (i = 0; i < (unsigned int)count * value_count; ++i)
        put_rpc_float(g_rpc_payload + payload_offset + i * 4u, value[i]);

    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=%s location=%d count=%d width=%u matrix=%u\n",
              function, location, count, matrix_dimension ? matrix_dimension : components,
              matrix_dimension);
    if (!rpc(opcode, (unsigned int)location, (unsigned int)count,
             matrix_dimension ? matrix_dimension : components,
             g_rpc_payload, payload_size, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=%s error=0x%04x\n",
                  function, g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glUniform1f(int location, float x)
{
    const float value[1] = {x};
    uniform_float_values("glUniform1f", location, 1, 1, value, 0, 0);
}

void glUniform2f(int location, float x, float y)
{
    const float value[2] = {x, y};
    uniform_float_values("glUniform2f", location, 1, 2, value, 0, 0);
}

void glUniform3f(int location, float x, float y, float z)
{
    const float value[3] = {x, y, z};
    uniform_float_values("glUniform3f", location, 1, 3, value, 0, 0);
}

void glUniform4f(int location, float x, float y, float z, float w)
{
    const float value[4] = {x, y, z, w};
    uniform_float_values("glUniform4f", location, 1, 4, value, 0, 0);
}

void glUniform1fv(int location, int count, const float *value)
{
    uniform_float_values("glUniform1fv", location, count, 1, value, 0, 0);
}

void glUniform2fv(int location, int count, const float *value)
{
    uniform_float_values("glUniform2fv", location, count, 2, value, 0, 0);
}

void glUniform3fv(int location, int count, const float *value)
{
    uniform_float_values("glUniform3fv", location, count, 3, value, 0, 0);
}

void glUniform4fv(int location, int count, const float *value)
{
    uniform_float_values("glUniform4fv", location, count, 4, value, 0, 0);
}

void glUniformMatrix2fv(int location, int count, unsigned char transpose,
                        const float *value)
{
    uniform_float_values("glUniformMatrix2fv", location, count, 0, value, 2,
                         transpose);
}

void glUniformMatrix3fv(int location, int count, unsigned char transpose,
                        const float *value)
{
    uniform_float_values("glUniformMatrix3fv", location, count, 0, value, 3,
                         transpose);
}

void glUniformMatrix4fv(int location, int count, unsigned char transpose,
                        const float *value)
{
    uniform_float_values("glUniformMatrix4fv", location, count, 0, value, 4,
                         transpose);
}

void glBlendFuncSeparate(unsigned int src_rgb, unsigned int dst_rgb,
                         unsigned int src_alpha, unsigned int dst_alpha)
{
    unsigned char payload[4];
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    idrive_angle_egl_rpc_put_u32(payload, dst_alpha);
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glBlendFuncSeparate srcRGB=0x%04x dstRGB=0x%04x srcAlpha=0x%04x dstAlpha=0x%04x\n",
              src_rgb, dst_rgb, src_alpha, dst_alpha);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_BLEND_FUNC_SEPARATE, src_rgb, dst_rgb,
             src_alpha, payload, sizeof(payload), &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glBlendFuncSeparate error=0x%04x\n",
                  g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glBlendColor(float red, float green, float blue, float alpha)
{
    unsigned char payload[16];
    float channels[4];
    unsigned int channel_bits[4];
    struct RpcResult reply;
    unsigned int i;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    channels[0] = red;
    channels[1] = green;
    channels[2] = blue;
    channels[3] = alpha;
    for (i = 0; i < 4; ++i) {
        unsigned int bits = 0;
        memcpy(&bits, &channels[i], sizeof(bits));
        channel_bits[i] = bits;
        idrive_angle_egl_rpc_put_u32(payload + i * 4u, bits);
    }
    /* Avoid float-to-double vararg promotion: this QNX toolchain does not
     * provide __aeabi_f2d to the preloaded provider at runtime. */
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glBlendColor rgba_bits=%08x,%08x,%08x,%08x\n",
              channel_bits[0], channel_bits[1], channel_bits[2], channel_bits[3]);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_BLEND_COLOR, 0, 0, 0,
             payload, sizeof(payload), &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glBlendColor error=0x%04x\n",
                  g_gl_error);
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glActiveTexture(unsigned int texture)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glActiveTexture texture=0x%04x\n",
              texture);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_ACTIVE_TEXTURE, texture, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glDrawArrays(unsigned int mode, int first, int count)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (first < 0 || count < 0) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glDrawArrays mode=0x%04x first=%d count=%d\n",
              mode, first, count);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ARRAYS, mode, (unsigned int)first,
             (unsigned int)count, 0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glDrawElements(unsigned int mode, int count, unsigned int type,
                    const void *indices)
{
    struct RpcResult reply;
    unsigned int index_size;
    unsigned int index_bytes;
    unsigned int index_offset = (unsigned int)(uintptr_t)indices;
    unsigned char *payload = g_rpc_payload;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (count < 0) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    if (type == GL_UNSIGNED_BYTE) index_size = 1;
    else if (type == GL_UNSIGNED_SHORT) index_size = 2;
    else if (type == GL_UNSIGNED_INT) index_size = 4;
    else {
        g_gl_error = GL_INVALID_ENUM;
        return;
    }
    if ((unsigned int)count > (IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD - 8u) / index_size) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    index_bytes = (unsigned int)count * index_size;
    if (!g_bound_element_array_buffer && index_bytes && !indices) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (g_bound_element_array_buffer) index_bytes = 0;
    else index_offset = 0;
    idrive_angle_egl_rpc_put_u32(payload, index_offset);
    idrive_angle_egl_rpc_put_u32(payload + 4,
        g_bound_element_array_buffer ? 0u : index_bytes);
    if (index_bytes) memcpy(payload + 8, indices, index_bytes);
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glDrawElements mode=0x%04x count=%d type=0x%04x indices=0x%08x element_buffer=%u client_index_bytes=%u\n",
              mode, count, type, index_offset, g_bound_element_array_buffer,
              index_bytes);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ELEMENTS, mode, (unsigned int)count,
             type, payload, 8u + index_bytes, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glGenerateMipmap(unsigned int target)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_GENERATE_MIPMAP, target, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    g_gl_error = GL_NO_ERROR;
}

void glScissor(int x, int y, int width, int height)
{
    unsigned char payload[16];
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    idrive_angle_egl_rpc_put_u32(payload, (unsigned int)x);
    idrive_angle_egl_rpc_put_u32(payload + 4, (unsigned int)y);
    idrive_angle_egl_rpc_put_u32(payload + 8, (unsigned int)width);
    idrive_angle_egl_rpc_put_u32(payload + 12, (unsigned int)height);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_SCISSOR, 0, 0, 0,
             payload, sizeof(payload), &reply))
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
    else
        g_gl_error = GL_NO_ERROR;
}

void glEnable(unsigned int capability)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_ENABLE, capability, 0, 0,
             0, 0, &reply))
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
    else
        g_gl_error = GL_NO_ERROR;
}

void glDisable(unsigned int capability)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_DISABLE, capability, 0, 0,
             0, 0, &reply))
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
    else
        g_gl_error = GL_NO_ERROR;
}

void glDepthFunc(unsigned int function)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_FUNC, function, 0, 0,
             0, 0, &reply))
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
    else
        g_gl_error = GL_NO_ERROR;
}

void glDepthMask(unsigned char flag)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_MASK, flag, 0, 0,
             0, 0, &reply))
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
    else
        g_gl_error = GL_NO_ERROR;
}

/* Real stencil/blend state forwarding. Success must not clear a pending GL error. */
static void gl_state_rpc(unsigned int opcode, unsigned int a, unsigned int b,
                         unsigned int c, const unsigned char *payload,
                         unsigned int payload_size)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        if (g_gl_error == GL_NO_ERROR) g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!rpc(opcode, a, b, c, payload, payload_size, &reply) &&
        g_gl_error == GL_NO_ERROR)
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
}

void glStencilFuncSeparate(unsigned int face, unsigned int function,
                            int reference, unsigned int mask)
{
    unsigned char payload[4];
    idrive_angle_egl_rpc_put_u32(payload, mask);
    gl_state_rpc(IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_FUNC_SEPARATE, face, function,
                 (unsigned int)reference, payload, sizeof(payload));
}

void glStencilMaskSeparate(unsigned int face, unsigned int mask)
{
    gl_state_rpc(IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_MASK_SEPARATE,
                 face, mask, 0, 0, 0);
}

void glStencilOpSeparate(unsigned int face, unsigned int fail,
                          unsigned int depth_fail, unsigned int depth_pass)
{
    unsigned char payload[4];
    idrive_angle_egl_rpc_put_u32(payload, depth_pass);
    gl_state_rpc(IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_OP_SEPARATE,
                 face, fail, depth_fail, payload, sizeof(payload));
}

void glStencilFunc(unsigned int function, int reference, unsigned int mask)
{
    glStencilFuncSeparate(0x0408u, function, reference, mask);
}

void glStencilMask(unsigned int mask)
{
    glStencilMaskSeparate(0x0408u, mask);
}

void glStencilOp(unsigned int fail, unsigned int depth_fail, unsigned int depth_pass)
{
    glStencilOpSeparate(0x0408u, fail, depth_fail, depth_pass);
}

void glClearStencil(int value)
{
    gl_state_rpc(IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_STENCIL,
                 (unsigned int)value, 0, 0, 0, 0);
}

void glBlendEquationSeparate(unsigned int rgb, unsigned int alpha)
{
    gl_state_rpc(IDRIVE_ANGLE_EGL_RPC_GL_BLEND_EQUATION_SEPARATE,
                 rgb, alpha, 0, 0, 0);
}

void glBlendEquation(unsigned int mode)
{
    glBlendEquationSeparate(mode, mode);
}

void glGetBooleanv(unsigned int pname, unsigned char *params)
{
    struct RpcResult reply;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!params) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glGetBooleanv pname=0x%04x\n",
              pname);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_GET_BOOLEAN, pname, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    if (reply.payload_size > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    memcpy(params, g_rpc_payload, reply.payload_size);
    g_gl_error = GL_NO_ERROR;
    if (reply.payload_size != 0)
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetBooleanv pname=0x%04x first=%u values=%u\n",
                  pname, g_rpc_payload[0], reply.payload_size);
    else
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetBooleanv pname=0x%04x values=0\n",
                  pname);
}

void glGetIntegerv(unsigned int pname, int *params)
{
    struct RpcResult reply;
    unsigned int offset;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!params) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glGetIntegerv pname=0x%04x\n",
              pname);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_GET_INTEGER, pname, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    if ((reply.payload_size % 4u) != 0 ||
        reply.payload_size > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    for (offset = 0; offset < reply.payload_size; offset += 4u)
        params[offset / 4u] = (int)idrive_angle_egl_rpc_u32(g_rpc_payload + offset);
    g_gl_error = GL_NO_ERROR;
    if (reply.payload_size >= 4u)
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetIntegerv pname=0x%04x first=0x%08x values=%u\n",
                  pname, (unsigned int)params[0], reply.payload_size / 4u);
    else
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetIntegerv pname=0x%04x values=0\n",
                  pname);
}

void glGetFloatv(unsigned int pname, float *params)
{
    struct RpcResult reply;
    unsigned int offset;
    unsigned int first_bits = 0;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (!params) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    EGL_TRACE("IDRIVE_ANGLE_GLES_CALL function=glGetFloatv pname=0x%04x\n",
              pname);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_GET_FLOAT, pname, 0, 0,
             0, 0, &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    if ((reply.payload_size % 4u) != 0 ||
        reply.payload_size > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    for (offset = 0; offset < reply.payload_size; offset += 4u) {
        unsigned int bits = idrive_angle_egl_rpc_u32(g_rpc_payload + offset);
        memcpy(params + offset / 4u, &bits, sizeof(bits));
    }
    g_gl_error = GL_NO_ERROR;
    if (reply.payload_size >= 4u) {
        memcpy(&first_bits, params, sizeof(first_bits));
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetFloatv pname=0x%04x first_bits=0x%08x values=%u\n",
                  pname, first_bits, reply.payload_size / 4u);
    } else {
        EGL_TRACE("IDRIVE_ANGLE_GLES_DONE function=glGetFloatv pname=0x%04x values=0\n",
                  pname);
    }
}

void glReadPixels(int x, int y, int width, int height,
                  unsigned int format, unsigned int type, void *pixels)
{
    unsigned char payload[24];
    struct RpcResult reply;
    unsigned int byte_count;
    if (g_current_context == EGL_NO_CONTEXT) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if (width < 0 || height < 0) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    if (format != GL_RGBA || type != GL_UNSIGNED_BYTE || !pixels) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    if ((unsigned int)width > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / 4u /
                              ((unsigned int)height ? (unsigned int)height : 1u)) {
        g_gl_error = GL_INVALID_VALUE;
        return;
    }
    byte_count = (unsigned int)width * (unsigned int)height * 4u;
    idrive_angle_egl_rpc_put_u32(payload, (unsigned int)x);
    idrive_angle_egl_rpc_put_u32(payload + 4, (unsigned int)y);
    idrive_angle_egl_rpc_put_u32(payload + 8, (unsigned int)width);
    idrive_angle_egl_rpc_put_u32(payload + 12, (unsigned int)height);
    idrive_angle_egl_rpc_put_u32(payload + 16, format);
    idrive_angle_egl_rpc_put_u32(payload + 20, type);
    if (!rpc(IDRIVE_ANGLE_EGL_RPC_GL_READ_PIXELS, 0, 0, 0,
             payload, sizeof(payload), &reply)) {
        g_gl_error = reply.error ? reply.error : GL_INVALID_OPERATION;
        return;
    }
    if (reply.payload_size != byte_count) {
        g_gl_error = GL_INVALID_OPERATION;
        return;
    }
    memcpy(pixels, g_rpc_payload, byte_count);
    g_gl_error = GL_NO_ERROR;
}

static unsigned int unsupported_gl(const char *entry)
{
#if defined(IDRIVE_ANGLE_EGL_TRACE)
    printf("IDRIVE_ANGLE_UNSUPPORTED_GLES function=%s error=0x%04x\n",
           entry, GL_INVALID_OPERATION);
    fflush((void *)0);
#else
    (void)entry;
#endif
    if (g_gl_error == GL_NO_ERROR) g_gl_error = GL_INVALID_OPERATION;
    return 0;
}

#define IDRIVE_GLES_SYMBOL(name) \
    unsigned int name() { return unsupported_gl(#name); }
#include "qnx-gles2-provider-unsupported.inc"
#undef IDRIVE_GLES_SYMBOL

struct GlesProc {
    const char *name;
    EGLProc proc;
};

#define IDRIVE_GLES_SYMBOL(name) { #name, (EGLProc)name },
static const struct GlesProc g_gles_procs[] = {
#include "qnx-gles2-provider-symbols.inc"
};
#undef IDRIVE_GLES_SYMBOL

static EGLProc egl_get_proc_address(const char *name)
{
    unsigned int i;
    if (!name) return (EGLProc)0;
    for (i = 0; i < sizeof(g_gles_procs) / sizeof(g_gles_procs[0]); ++i)
        if (strcmp(name, g_gles_procs[i].name) == 0) return g_gles_procs[i].proc;
    return (EGLProc)0;
}

static EGLBoolean egl_bind_api(EGLenum api)
{
    if (api != EGL_OPENGL_ES_API) return unsupported_egl(EGL_BAD_PARAMETER);
    return EGL_TRUE;
}

static EGLenum egl_query_api(void)
{
    return EGL_OPENGL_ES_API;
}

static EGLContext egl_get_current_context(void) { return g_current_context; }
static EGLDisplay egl_get_current_display(void)
{
    return g_current_context == EGL_NO_CONTEXT ? EGL_NO_DISPLAY : g_display;
}
static EGLSurface egl_get_current_surface(EGLint which)
{
    if (which == EGL_DRAW) return g_current_draw;
    if (which == EGL_READ) return g_current_read;
    g_egl_error = EGL_BAD_PARAMETER;
    return EGL_NO_SURFACE;
}

/* Exact 34-slot table order recovered from libEGL.so.1. */
typedef void (*Proc)(void);
#define CORE_PROCS(X) \
 X(egl_get_error) X(egl_get_display) X(egl_initialize) X(egl_terminate) \
 X(query_string) X(egl_get_configs) X(egl_choose_config) X(egl_get_config_attrib) \
 X(egl_create_window_surface) X(egl_create_pbuffer_surface) X(egl_create_pixmap_surface) \
 X(egl_destroy_surface) X(egl_query_surface) X(egl_bind_api) X(egl_query_api) \
 X(egl_wait_client) X(egl_release_thread) X(egl_create_pbuffer_from_client_buffer) \
 X(egl_surface_attrib) X(egl_bind_tex_image) X(egl_release_tex_image) X(egl_swap_interval) \
 X(egl_create_context) X(egl_destroy_context) X(egl_make_current) \
 X(egl_get_current_context) X(egl_get_current_surface) X(egl_get_current_display) \
 X(egl_query_context) X(egl_wait_gl) X(egl_wait_native) \
 X(egl_swap_buffers) X(egl_copy_buffers) X(egl_get_proc_address)

static Proc g_dispatch[34] = {
#define SLOT(name) (Proc)name,
    CORE_PROCS(SLOT)
#undef SLOT
};

const char *ID6eglQueryString(EGLDisplay display, EGLint name)
{
    if (display == EGL_NO_DISPLAY && name == 0x6000) {
        EGL_LOG("IDRIVE_ANGLE_PROVIDER_HANDSHAKE pid=%d slots=34\n", getpid());
        return (const char *)g_dispatch;
    }
    return query_string(display, name);
}

