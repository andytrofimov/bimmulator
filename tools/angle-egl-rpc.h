#ifndef IDRIVE6_ANGLE_EGL_RPC_H
#define IDRIVE6_ANGLE_EGL_RPC_H

#define IDRIVE_ANGLE_EGL_RPC_PORT 41416u
#define IDRIVE_ANGLE_EGL_RPC_VERSION 4u
#define IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES 32u
#define IDRIVE_ANGLE_EGL_RPC_RESPONSE_BYTES 32u
#define IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD (16u * 1024u * 1024u)
#define IDRIVE_ANGLE_EGL_RPC_MAX_ATTR_INTS 128u
#define IDRIVE_ANGLE_EGL_RPC_MAX_ATTR_BYTES (IDRIVE_ANGLE_EGL_RPC_MAX_ATTR_INTS * 4u)
#define IDRIVE_ANGLE_EGL_RPC_MAX_STRING_BYTES 65536u
#define IDRIVE_ANGLE_EGL_RPC_MAX_FRAME_BYTES (16u * 1024u * 1024u)

/* The OMAP5430 machine maps a separate shared backend at this address.
 * Aligned native little-endian words coordinate ownership. The frame bytes
 * retain the existing big-endian RPC layout in both directions. */
#define IDRIVE_ANGLE_MAILBOX_PHYS 0x70000000u
#define IDRIVE_ANGLE_MAILBOX_BYTES (17u * 1024u * 1024u)
#define IDRIVE_ANGLE_MAILBOX_MAGIC 0x424d3649u /* I6MB */
#define IDRIVE_ANGLE_MAILBOX_FRAME_OFFSET 64u
#define IDRIVE_ANGLE_MAILBOX_BATCH 1u
#define IDRIVE_ANGLE_MAILBOX_BATCH_BIND 2u
#define IDRIVE_ANGLE_MAILBOX_FAST_WAIT 8u
#define IDRIVE_ANGLE_MAILBOX_IMMEDIATE_POST 16u
#define IDRIVE_ANGLE_EGL_BATCH_BYTES (64u * 1024u)
#define IDRIVE_HMI_CONTROLLER_OFFSET 0x01010000u
#define IDRIVE_HMI_CONTROLLER_SLOTS 64u

/* The controller producer is the host renderer's local input socket.
 * The HMI bridge consumes this ring independently of its rendering thread. */
struct idrive_hmi_controller_ring {
    unsigned int ready;
    unsigned int read_index;
    unsigned int write_index;
    unsigned int events[IDRIVE_HMI_CONTROLLER_SLOTS];
};

static inline int idrive_hmi_controller_is_rotary(unsigned int key)
{
    return key == 13u || key == 14u;
}

static inline int idrive_hmi_controller_valid(unsigned int key,
                                             unsigned int pressed)
{
    return ((key >= 1u && key <= 12u) || key == 17u)
        ? pressed <= 1u : idrive_hmi_controller_is_rotary(key) && pressed == 0u;
}

enum idrive_angle_mailbox_state {
    IDRIVE_ANGLE_MAILBOX_IDLE,
    IDRIVE_ANGLE_MAILBOX_WRITING,
    IDRIVE_ANGLE_MAILBOX_REQUEST,
    IDRIVE_ANGLE_MAILBOX_PROCESSING,
    IDRIVE_ANGLE_MAILBOX_RESPONSE,
    IDRIVE_ANGLE_MAILBOX_FAILED,
};

struct idrive_angle_mailbox {
    unsigned int magic;
    unsigned int state;
    unsigned int features;     /* Host capabilities published before magic. */
    unsigned int screen_posts; /* Guest increments after a successful Screen post. */
    unsigned int screen_buffer_cycles;
    unsigned int screen_rpc_cycles;
    unsigned int screen_post_cycles;
    unsigned char reserved[IDRIVE_ANGLE_MAILBOX_FRAME_OFFSET - 28u];
    unsigned char frame[IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES +
                        IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD];
};

enum idrive_angle_egl_rpc_opcode {
    IDRIVE_ANGLE_EGL_RPC_INITIALIZE = 1,
    IDRIVE_ANGLE_EGL_RPC_TERMINATE = 2,
    IDRIVE_ANGLE_EGL_RPC_QUERY_STRING = 3,
    IDRIVE_ANGLE_EGL_RPC_GET_CONFIGS = 4,
    IDRIVE_ANGLE_EGL_RPC_CHOOSE_CONFIG = 5,
    IDRIVE_ANGLE_EGL_RPC_GET_CONFIG_ATTRIB = 6,
    IDRIVE_ANGLE_EGL_RPC_CREATE_PBUFFER = 7,
    IDRIVE_ANGLE_EGL_RPC_CREATE_CONTEXT = 8,
    IDRIVE_ANGLE_EGL_RPC_MAKE_CURRENT = 9,
    IDRIVE_ANGLE_EGL_RPC_DESTROY_SURFACE = 10,
    IDRIVE_ANGLE_EGL_RPC_DESTROY_CONTEXT = 11,
    IDRIVE_ANGLE_EGL_RPC_QUERY_SURFACE = 12,
    IDRIVE_ANGLE_EGL_RPC_SWAP_BUFFERS = 13,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_STRING = 14,
    IDRIVE_ANGLE_EGL_RPC_QUERY_CONTEXT = 15,
    IDRIVE_ANGLE_EGL_RPC_GL_VIEWPORT = 16,
    IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_COLOR = 17,
    IDRIVE_ANGLE_EGL_RPC_GL_CLEAR = 18,
    IDRIVE_ANGLE_EGL_RPC_GL_READ_PIXELS = 19,
    IDRIVE_ANGLE_EGL_RPC_CREATE_WINDOW_SURFACE = 20,
    IDRIVE_ANGLE_EGL_RPC_SWAP_WINDOW_SURFACE = 21,
    IDRIVE_ANGLE_EGL_RPC_GL_SCISSOR = 22,
    IDRIVE_ANGLE_EGL_RPC_GL_ENABLE = 23,
    IDRIVE_ANGLE_EGL_RPC_GL_DISABLE = 24,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_INTEGER = 25,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_BOOLEAN = 26,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_FLOAT = 27,
    IDRIVE_ANGLE_EGL_RPC_GL_GEN_BUFFERS = 28,
    IDRIVE_ANGLE_EGL_RPC_GL_GEN_TEXTURES = 29,
    IDRIVE_ANGLE_EGL_RPC_GL_CREATE_SHADER = 30,
    IDRIVE_ANGLE_EGL_RPC_GL_BIND_BUFFER = 31,
    IDRIVE_ANGLE_EGL_RPC_GL_BIND_TEXTURE = 32,
    IDRIVE_ANGLE_EGL_RPC_GL_SHADER_BINARY_CAPTURE = 33,
    IDRIVE_ANGLE_EGL_RPC_GL_SHADER_SOURCE = 34,
    IDRIVE_ANGLE_EGL_RPC_GL_BUFFER_DATA = 35,
    IDRIVE_ANGLE_EGL_RPC_GL_TEX_PARAMETERI = 36,
    IDRIVE_ANGLE_EGL_RPC_GL_PIXEL_STOREI = 37,
    IDRIVE_ANGLE_EGL_RPC_GL_TEX_IMAGE_2D = 38,
    IDRIVE_ANGLE_EGL_RPC_GL_COMPILE_SHADER = 39,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_SHADER_IV = 40,
    IDRIVE_ANGLE_EGL_RPC_GL_GENERATE_MIPMAP = 41,
    IDRIVE_ANGLE_EGL_RPC_GL_CREATE_PROGRAM = 42,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_PROGRAM_IV = 43,
    IDRIVE_ANGLE_EGL_RPC_GL_ATTACH_SHADER = 44,
    IDRIVE_ANGLE_EGL_RPC_GL_LINK_PROGRAM = 45,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_UNIFORM = 46,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_ATTRIB = 47,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_ATTRIB_LOCATION = 48,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_UNIFORM_LOCATION = 49,
    IDRIVE_ANGLE_EGL_RPC_GL_USE_PROGRAM = 50,
    IDRIVE_ANGLE_EGL_RPC_GL_ENABLE_VERTEX_ATTRIB_ARRAY = 51,
    IDRIVE_ANGLE_EGL_RPC_GL_DISABLE_VERTEX_ATTRIB_ARRAY = 52,
    IDRIVE_ANGLE_EGL_RPC_GL_VERTEX_ATTRIB_POINTER = 53,
    IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1I = 54,
    IDRIVE_ANGLE_EGL_RPC_GL_ACTIVE_TEXTURE = 55,
    IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ARRAYS = 56,
    IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ELEMENTS = 57,
    IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1IV = 58,
    IDRIVE_ANGLE_EGL_RPC_GL_BLEND_FUNC_SEPARATE = 59,
    IDRIVE_ANGLE_EGL_RPC_GL_BLEND_COLOR = 60,
    IDRIVE_ANGLE_EGL_RPC_GL_GET_PROGRAM_INFO_LOG = 61,
    IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_FUNC = 62,
    IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_MASK = 63,
    IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_FV = 64,
    IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_MATRIX_FV = 65,
    IDRIVE_ANGLE_EGL_RPC_GL_BUFFER_SUB_DATA = 66,
    IDRIVE_ANGLE_EGL_RPC_GL_TEX_SUB_IMAGE_2D = 67,
    IDRIVE_ANGLE_EGL_RPC_GL_BATCH = 68,
    IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_FUNC_SEPARATE = 69,
    IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_MASK_SEPARATE = 70,
    IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_OP_SEPARATE = 71,
    IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_STENCIL = 72,
    IDRIVE_ANGLE_EGL_RPC_GL_BLEND_EQUATION_SEPARATE = 73
};

/* These calls return no data and do not change the provider's local
 * unpack state. A buffer bind can only be queued after the provider has
 * established that ANGLE accepts that name and target in the context. */
static inline int idrive_angle_egl_rpc_batchable(unsigned int opcode)
{
    switch (opcode) {
    case IDRIVE_ANGLE_EGL_RPC_GL_VIEWPORT:
    case IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_COLOR:
    case IDRIVE_ANGLE_EGL_RPC_GL_CLEAR:
    case IDRIVE_ANGLE_EGL_RPC_GL_SCISSOR:
    case IDRIVE_ANGLE_EGL_RPC_GL_ENABLE:
    case IDRIVE_ANGLE_EGL_RPC_GL_DISABLE:
    case IDRIVE_ANGLE_EGL_RPC_GL_BIND_BUFFER:
    case IDRIVE_ANGLE_EGL_RPC_GL_BIND_TEXTURE:
    case IDRIVE_ANGLE_EGL_RPC_GL_TEX_PARAMETERI:
    case IDRIVE_ANGLE_EGL_RPC_GL_GENERATE_MIPMAP:
    case IDRIVE_ANGLE_EGL_RPC_GL_USE_PROGRAM:
    case IDRIVE_ANGLE_EGL_RPC_GL_ENABLE_VERTEX_ATTRIB_ARRAY:
    case IDRIVE_ANGLE_EGL_RPC_GL_DISABLE_VERTEX_ATTRIB_ARRAY:
    case IDRIVE_ANGLE_EGL_RPC_GL_VERTEX_ATTRIB_POINTER:
    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1I:
    case IDRIVE_ANGLE_EGL_RPC_GL_ACTIVE_TEXTURE:
    case IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ARRAYS:
    case IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ELEMENTS:
    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1IV:
    case IDRIVE_ANGLE_EGL_RPC_GL_BLEND_FUNC_SEPARATE:
    case IDRIVE_ANGLE_EGL_RPC_GL_BLEND_COLOR:
    case IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_FUNC:
    case IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_MASK:
    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_FV:
    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_MATRIX_FV:
    case IDRIVE_ANGLE_EGL_RPC_GL_BUFFER_SUB_DATA:
    case IDRIVE_ANGLE_EGL_RPC_GL_TEX_SUB_IMAGE_2D:
        return 1;
    default:
        return 0;
    }
}

static inline unsigned int idrive_angle_egl_rpc_u16(const unsigned char *p)
{
    return ((unsigned int)p[0] << 8) | p[1];
}

static inline unsigned int idrive_angle_egl_rpc_u32(const unsigned char *p)
{
    return ((unsigned int)p[0] << 24) | ((unsigned int)p[1] << 16) |
           ((unsigned int)p[2] << 8) | (unsigned int)p[3];
}

static inline void idrive_angle_egl_rpc_put_u16(unsigned char *p,
                                                 unsigned int value)
{
    p[0] = (unsigned char)(value >> 8);
    p[1] = (unsigned char)value;
}

static inline void idrive_angle_egl_rpc_put_u32(unsigned char *p,
                                                 unsigned int value)
{
    p[0] = (unsigned char)(value >> 24);
    p[1] = (unsigned char)(value >> 16);
    p[2] = (unsigned char)(value >> 8);
    p[3] = (unsigned char)value;
}

#endif
