#define EGL_EGLEXT_PROTOTYPES 1
#define GL_GLEXT_PROTOTYPES 1

#include <EGL/egl.h>
#include <EGL/eglext.h>
#if !defined(IDRIVE_USE_MESA)
#include <EGL/eglext_angle.h>
#endif
#include <GLES2/gl2.h>

#include "angle-egl-rpc.h"

#include <algorithm>
#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iterator>
#include <netinet/in.h>
#include <sstream>
#include <string>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <unistd.h>
#include <vector>

namespace {

constexpr GLenum kGlInvalidOperation = 0x0502;
constexpr GLenum kGlInvalidValue = 0x0501;
constexpr GLenum kGlInvalidEnum = 0x0500;
constexpr GLenum kGlRgba = 0x1908;
constexpr GLenum kGlUnsignedByte = 0x1401;
constexpr EGLint kEglSurfaceType = 0x3033;
constexpr EGLint kEglRenderableType = 0x3040;
constexpr EGLint kEglOpenGles2Bit = 0x0004;
constexpr EGLint kEglOpenGles3Bit = 0x0040;
constexpr EGLint kEglContextClientVersion = 0x3098;
constexpr EGLint kEglPbufferBit = 0x0001;
constexpr EGLint kEglWindowBit = 0x0004;
constexpr unsigned int kScreenFormatRgba8888 = 8;
constexpr std::uint64_t kGuestRamBase = 0x80000000ULL;
constexpr std::size_t kMaxConfigResults = 64;

float rpc_float(const unsigned char *bytes)
{
    const std::uint32_t bits = idrive_angle_egl_rpc_u32(bytes);
    float value = 0.0f;
    static_assert(sizeof(value) == sizeof(bits), "RPC GLES float must be 32-bit");
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

volatile std::sig_atomic_t g_stop = 0;
int g_listener = -1;
int g_guest_ram_fd = -1;
std::uint64_t g_guest_ram_size = 0;
std::string g_guest_ram_path;
std::string g_shader_capture_dir;
unsigned int g_shader_capture_index = 0;
std::string g_draw_capture_dir;
unsigned int g_draw_capture_limit = 0;
unsigned int g_draw_capture_index = 0;
std::string g_resource_capture_dir;
unsigned int g_resource_capture_index = 0;
std::unordered_map<GLuint, std::vector<unsigned char>> g_buffer_contents;
EGLDisplay g_display = EGL_NO_DISPLAY;
EGLint g_major = 0;
EGLint g_minor = 0;
bool g_display_initialized = false;
bool g_requires_gles3 = false;

struct ShaderTranslation {
    std::vector<unsigned char> native_binary;
    std::string native_path;
    std::string source;
    std::string source_path;
    struct UniformNameAlias {
        std::string native_name;
        std::string host_name;
    };
    std::vector<UniformNameAlias> uniform_aliases;
};

std::vector<ShaderTranslation> g_shader_translations;
std::unordered_map<GLuint, std::vector<ShaderTranslation::UniformNameAlias>>
    g_shader_uniform_aliases;
std::unordered_map<GLuint, std::vector<ShaderTranslation::UniformNameAlias>>
    g_program_uniform_aliases;

struct ClientState {
    unsigned int next_config = 1;
    unsigned int next_surface = 1;
    unsigned int next_context = 1;
    std::unordered_map<unsigned int, EGLConfig> configs;
    std::unordered_map<unsigned int, EGLSurface> surfaces;
    std::unordered_map<unsigned int, EGLContext> contexts;
};

std::unordered_map<unsigned int, ClientState> g_clients;
// EGL current state belongs to this single dispatch thread, not every RPC
// client. Track the client that successfully bound it; a failed bind leaves
// the previous owner intact. A deferred context destroy also keeps ownership.
unsigned int g_current_context_client = 0;

bool read_all(int fd, unsigned char *data, std::size_t size,
              std::chrono::steady_clock::time_point *first_byte_time = nullptr)
{
    std::size_t received = 0;
    while (received < size) {
        const ssize_t result = recv(fd, data + received, size - received, 0);
        if (result <= 0) return false;
        if (received == 0 && first_byte_time) {
            *first_byte_time = std::chrono::steady_clock::now();
        }
        received += static_cast<std::size_t>(result);
    }
    return true;
}

bool write_all(int fd, const unsigned char *data, std::size_t size)
{
    std::size_t sent = 0;
    while (sent < size) {
        const ssize_t result = send(fd, data + sent, size - sent, 0);
        if (result <= 0) return false;
        sent += static_cast<std::size_t>(result);
    }
    return true;
}

std::string capture_resource_blob(const char *kind, GLuint object,
                                  unsigned int update,
                                  const unsigned char *data, std::size_t size)
{
    if (g_resource_capture_dir.empty()) return {};
    char filename[160];
    std::snprintf(filename, sizeof(filename), "%s-%u-update-%06u.bin",
                  kind, object, update);
    const std::string path = g_resource_capture_dir + "/" + filename;
    std::ofstream capture(path, std::ios::binary);
    if (!capture || (size && !capture.write(
            reinterpret_cast<const char *>(data),
            static_cast<std::streamsize>(size)))) {
        std::fprintf(stderr,
                     "ANGLE_RESOURCE_CAPTURE_FAIL kind=%s object=%u bytes=%zu path=%s\n",
                     kind, object, size, path.c_str());
        return {};
    }
    return path;
}

GLuint bound_buffer(GLenum target)
{
    GLint name = 0;
    const GLenum binding = target == GL_ELEMENT_ARRAY_BUFFER
        ? GL_ELEMENT_ARRAY_BUFFER_BINDING : GL_ARRAY_BUFFER_BINDING;
    glGetIntegerv(binding, &name);
    return name > 0 ? static_cast<GLuint>(name) : 0;
}

void set_error(unsigned char *response, EGLint error)
{
    idrive_angle_egl_rpc_put_u16(response + 6, 1);
    idrive_angle_egl_rpc_put_u32(response + 8, static_cast<unsigned int>(error));
}

void set_value(unsigned char *response, unsigned int slot, unsigned int value)
{
    idrive_angle_egl_rpc_put_u32(response + 12 + slot * 4, value);
}

std::uint64_t frame_hash(const std::vector<unsigned char> &frame)
{
    std::uint64_t value = 1469598103934665603ULL;
    for (const unsigned char byte : frame) {
        value ^= byte;
        value *= 1099511628211ULL;
    }
    return value;
}

bool load_shader_translation(const char *native_path, const char *source_path)
{
    std::ifstream native_file(native_path, std::ios::binary);
    std::ifstream source_file(source_path, std::ios::binary);
    if (!native_file || !source_file) {
        std::fprintf(stderr,
                     "ANGLE_SHADER_MAP_FAIL native=%s source=%s reason=open\n",
                     native_path, source_path);
        return false;
    }

    ShaderTranslation translation;
    translation.native_binary.assign(
        std::istreambuf_iterator<char>(native_file),
        std::istreambuf_iterator<char>());
    translation.source.assign(
        std::istreambuf_iterator<char>(source_file),
        std::istreambuf_iterator<char>());
    translation.native_path = native_path;
    translation.source_path = source_path;
    constexpr const char *alias_prefix = "// IDRIVE_UNIFORM_ALIAS ";
    const std::size_t alias_prefix_length = std::strlen(alias_prefix);
    std::istringstream source_lines(translation.source);
    std::string source_line;
    while (std::getline(source_lines, source_line)) {
        if (source_line.compare(0, alias_prefix_length, alias_prefix) != 0) {
            continue;
        }
        std::istringstream alias_fields(
            source_line.substr(alias_prefix_length));
        std::string native_field;
        std::string host_field;
        if (!(alias_fields >> native_field >> host_field) ||
            native_field.compare(0, 7, "native=") != 0 ||
            host_field.compare(0, 5, "host=") != 0) {
            std::fprintf(stderr,
                         "ANGLE_SHADER_MAP_FAIL native=%s source=%s reason=uniform-alias-syntax\n",
                         native_path, source_path);
            return false;
        }
        ShaderTranslation::UniformNameAlias alias{
            native_field.substr(7), host_field.substr(5)};
        if (alias.native_name.rfind("gl_", 0) != 0 ||
            alias.host_name.empty() || alias.host_name.rfind("gl_", 0) == 0 ||
            std::any_of(translation.uniform_aliases.begin(),
                        translation.uniform_aliases.end(),
                        [&](const auto &existing) {
                            return existing.native_name == alias.native_name ||
                                   existing.host_name == alias.host_name;
                        })) {
            std::fprintf(stderr,
                         "ANGLE_SHADER_MAP_FAIL native=%s source=%s reason=uniform-alias-contract\n",
                         native_path, source_path);
            return false;
        }
        translation.uniform_aliases.push_back(std::move(alias));
    }
    if (translation.source.find("#version 300 es") != std::string::npos) {
        g_requires_gles3 = true;
    }
    if (translation.native_binary.empty() || translation.source.empty()) {
        std::fprintf(stderr,
                     "ANGLE_SHADER_MAP_FAIL native=%s source=%s reason=empty\n",
                     native_path, source_path);
        return false;
    }

    std::fprintf(stderr,
                 "ANGLE_SHADER_MAP_READY native=%s bytes=%zu source=%s bytes=%zu\n",
                 translation.native_path.c_str(), translation.native_binary.size(),
                 translation.source_path.c_str(), translation.source.size());
    g_shader_translations.push_back(std::move(translation));
    return true;
}

const ShaderTranslation *find_shader_translation(const unsigned char *binary,
                                                  std::size_t length)
{
    for (const ShaderTranslation &translation : g_shader_translations) {
        if (translation.native_binary.size() == length &&
            std::equal(translation.native_binary.begin(),
                       translation.native_binary.end(), binary)) {
            return &translation;
        }
    }
    return nullptr;
}

void capture_draw_snapshot(GLenum mode, GLsizei count, GLenum index_type)
{
    if (g_draw_capture_dir.empty() ||
        g_draw_capture_index >= g_draw_capture_limit) {
        return;
    }

    EGLSurface surface = eglGetCurrentSurface(EGL_DRAW);
    EGLint width = 0;
    EGLint height = 0;
    if (surface == EGL_NO_SURFACE ||
        eglQuerySurface(g_display, surface, EGL_WIDTH, &width) != EGL_TRUE ||
        eglQuerySurface(g_display, surface, EGL_HEIGHT, &height) != EGL_TRUE ||
        width <= 0 || height <= 0) {
        std::fprintf(stderr,
                     "ANGLE_DRAW_CAPTURE_FAIL reason=surface dimensions unavailable\n");
        return;
    }

    const unsigned int index = ++g_draw_capture_index;
    GLint program = 0;
    GLint viewport[4] = { 0, 0, 0, 0 };
    GLint scissor[4] = { 0, 0, 0, 0 };
    GLint active_texture = 0;
    GLint texture_2d = 0;
    const GLuint element_buffer = bound_buffer(GL_ELEMENT_ARRAY_BUFFER);
    GLfloat clear_color[4] = { 0, 0, 0, 0 };
    glGetIntegerv(GL_CURRENT_PROGRAM, &program);
    glGetIntegerv(GL_VIEWPORT, viewport);
    glGetIntegerv(GL_SCISSOR_BOX, scissor);
    glGetIntegerv(GL_ACTIVE_TEXTURE, &active_texture);
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture_2d);
    glGetFloatv(GL_COLOR_CLEAR_VALUE, clear_color);

    GLint active_uniforms = 0;
    GLint max_uniform_name = 0;
    glGetProgramiv(static_cast<GLuint>(program), GL_ACTIVE_UNIFORMS,
                   &active_uniforms);
    glGetProgramiv(static_cast<GLuint>(program), GL_ACTIVE_UNIFORM_MAX_LENGTH,
                   &max_uniform_name);
    if (active_uniforms > 0 && max_uniform_name > 0) {
        std::vector<GLchar> uniform_name(static_cast<std::size_t>(max_uniform_name), '\0');
        for (GLint uniform_index = 0; uniform_index < active_uniforms;
             ++uniform_index) {
            GLsizei name_length = 0;
            GLint array_size = 0;
            GLenum type = 0;
            glGetActiveUniform(static_cast<GLuint>(program),
                               static_cast<GLuint>(uniform_index),
                               static_cast<GLsizei>(uniform_name.size()),
                               &name_length, &array_size, &type,
                               uniform_name.data());
            if (name_length <= 0 ||
                static_cast<std::size_t>(name_length) >= uniform_name.size()) {
                continue;
            }
            uniform_name[static_cast<std::size_t>(name_length)] = '\0';
            const GLint location = glGetUniformLocation(
                static_cast<GLuint>(program), uniform_name.data());
            if (location < 0) continue;

            unsigned int components = 0;
            bool integer_value = false;
            switch (type) {
            case GL_FLOAT: case GL_INT: case GL_BOOL: case GL_SAMPLER_2D:
                components = 1; integer_value = type != GL_FLOAT; break;
            case GL_FLOAT_VEC2: case GL_INT_VEC2: case GL_BOOL_VEC2:
                components = 2; integer_value = type != GL_FLOAT_VEC2; break;
            case GL_FLOAT_VEC3: case GL_INT_VEC3: case GL_BOOL_VEC3:
                components = 3; integer_value = type != GL_FLOAT_VEC3; break;
            case GL_FLOAT_VEC4: case GL_INT_VEC4: case GL_BOOL_VEC4:
                components = 4; integer_value = type != GL_FLOAT_VEC4; break;
            case GL_FLOAT_MAT2: components = 4; break;
            case GL_FLOAT_MAT3: components = 9; break;
            case GL_FLOAT_MAT4: components = 16; break;
            default: break;
            }

            std::fprintf(stderr,
                         "ANGLE_DRAW_UNIFORM index=%u program=%d name=%s location=%d type=0x%04x size=%d",
                         index, program, uniform_name.data(), location, type,
                         array_size);
            if (components != 0 && integer_value) {
                GLint values[16] = {};
                glGetUniformiv(static_cast<GLuint>(program), location, values);
                for (unsigned int component = 0; component < components;
                     ++component) {
                    std::fprintf(stderr, " v%u=%d", component, values[component]);
                }
            } else if (components != 0) {
                GLfloat values[16] = {};
                glGetUniformfv(static_cast<GLuint>(program), location, values);
                for (unsigned int component = 0; component < components;
                     ++component) {
                    std::fprintf(stderr, " v%u=%.9g", component,
                                 static_cast<double>(values[component]));
                }
            }
            std::fputc('\n', stderr);
        }
    }

    GLint active_attributes = 0;
    GLint max_attribute_name = 0;
    glGetProgramiv(static_cast<GLuint>(program), GL_ACTIVE_ATTRIBUTES,
                   &active_attributes);
    glGetProgramiv(static_cast<GLuint>(program), GL_ACTIVE_ATTRIBUTE_MAX_LENGTH,
                   &max_attribute_name);
    std::unordered_set<GLuint> draw_buffers;
    if (element_buffer) draw_buffers.insert(element_buffer);
    if (active_attributes > 0 && max_attribute_name > 0) {
        std::vector<GLchar> attribute_name(
            static_cast<std::size_t>(max_attribute_name), '\0');
        for (GLint attribute_index = 0; attribute_index < active_attributes;
             ++attribute_index) {
            GLsizei name_length = 0;
            GLint array_size = 0;
            GLenum type = 0;
            glGetActiveAttrib(static_cast<GLuint>(program),
                              static_cast<GLuint>(attribute_index),
                              static_cast<GLsizei>(attribute_name.size()),
                              &name_length, &array_size, &type,
                              attribute_name.data());
            if (name_length <= 0 ||
                static_cast<std::size_t>(name_length) >= attribute_name.size()) {
                continue;
            }
            attribute_name[static_cast<std::size_t>(name_length)] = '\0';
            const GLint location = glGetAttribLocation(
                static_cast<GLuint>(program), attribute_name.data());
            if (location < 0) continue;

            GLint enabled = GL_FALSE;
            GLint size = 0;
            GLint type_value = 0;
            GLint normalized = GL_FALSE;
            GLint stride = 0;
            GLint buffer = 0;
            GLvoid *pointer = nullptr;
            glGetVertexAttribiv(static_cast<GLuint>(location),
                                GL_VERTEX_ATTRIB_ARRAY_ENABLED, &enabled);
            glGetVertexAttribiv(static_cast<GLuint>(location),
                                GL_VERTEX_ATTRIB_ARRAY_SIZE, &size);
            glGetVertexAttribiv(static_cast<GLuint>(location),
                                GL_VERTEX_ATTRIB_ARRAY_TYPE, &type_value);
            glGetVertexAttribiv(static_cast<GLuint>(location),
                                GL_VERTEX_ATTRIB_ARRAY_NORMALIZED, &normalized);
            glGetVertexAttribiv(static_cast<GLuint>(location),
                                GL_VERTEX_ATTRIB_ARRAY_STRIDE, &stride);
            glGetVertexAttribiv(static_cast<GLuint>(location),
                                GL_VERTEX_ATTRIB_ARRAY_BUFFER_BINDING, &buffer);
            glGetVertexAttribPointerv(static_cast<GLuint>(location),
                                      GL_VERTEX_ATTRIB_ARRAY_POINTER, &pointer);
            std::fprintf(stderr,
                         "ANGLE_DRAW_ATTRIBUTE index=%u program=%d name=%s location=%d type=0x%04x size=%d enabled=%d components=%d component_type=0x%04x normalized=%d stride=%d buffer=%d offset=%llu\n",
                         index, program, attribute_name.data(), location, type,
                         array_size, enabled, size, type_value, normalized,
                         stride,
                         buffer,
                         static_cast<unsigned long long>(
                             reinterpret_cast<std::uintptr_t>(pointer)));
            if (buffer > 0) draw_buffers.insert(static_cast<GLuint>(buffer));
        }
    }

    const GLint saved_active_texture = active_texture;
    GLint texture_unit_count = 0;
    glGetIntegerv(GL_MAX_COMBINED_TEXTURE_IMAGE_UNITS, &texture_unit_count);
    if (texture_unit_count > 16) texture_unit_count = 16;
    for (GLint unit = 0; unit < texture_unit_count; ++unit) {
        glActiveTexture(static_cast<GLenum>(GL_TEXTURE0 + unit));
        GLint unit_texture = 0;
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &unit_texture);
        if (unit_texture != 0) {
            std::fprintf(stderr,
                         "ANGLE_DRAW_TEXTURE_UNIT index=%u unit=%d texture=%d\n",
                         index, unit, unit_texture);
        }
    }
    glActiveTexture(static_cast<GLenum>(saved_active_texture));

    for (const GLuint buffer : draw_buffers) {
        const auto contents = g_buffer_contents.find(buffer);
        if (contents == g_buffer_contents.end()) continue;
        const std::string path = capture_resource_blob(
            "draw-buffer", buffer, index, contents->second.data(),
            contents->second.size());
        if (!path.empty()) {
            std::fprintf(stderr,
                         "ANGLE_DRAW_RESOURCE_BUFFER index=%u buffer=%u bytes=%zu path=%s\n",
                         index, buffer, contents->second.size(), path.c_str());
        }
    }

    char filename[96];
    std::snprintf(filename, sizeof(filename), "draw-%04u.ppm", index);
    const std::string path = g_draw_capture_dir + "/" + filename;
    std::vector<unsigned char> rgba(static_cast<std::size_t>(width) *
                                    static_cast<std::size_t>(height) * 4u);
    glFinish();
    glReadPixels(0, 0, width, height, kGlRgba, kGlUnsignedByte, rgba.data());
    const GLenum read_error = glGetError();
    if (read_error != GL_NO_ERROR) {
        std::fprintf(stderr,
                     "ANGLE_DRAW_CAPTURE_FAIL index=%u error=0x%04x\n",
                     index, read_error);
        return;
    }

    std::ofstream image(path, std::ios::binary);
    if (!image) {
        std::fprintf(stderr,
                     "ANGLE_DRAW_CAPTURE_FAIL index=%u path=%s reason=open\n",
                     index, path.c_str());
        return;
    }
    image << "P6\n" << width << " " << height << "\n255\n";
    for (GLint y = height - 1; y >= 0; --y) {
        const unsigned char *row = rgba.data() +
            static_cast<std::size_t>(y) * static_cast<std::size_t>(width) * 4u;
        for (GLint x = 0; x < width; ++x) {
            image.write(reinterpret_cast<const char *>(row + x * 4), 3);
        }
    }
    if (!image) {
        std::fprintf(stderr,
                     "ANGLE_DRAW_CAPTURE_FAIL index=%u path=%s reason=write\n",
                     index, path.c_str());
        return;
    }

    std::fprintf(stderr,
                 "ANGLE_DRAW_CAPTURE index=%u program=%d mode=0x%04x count=%d index_type=0x%04x element_buffer=%u viewport=%d,%d,%d,%d clear=%.6g,%.6g,%.6g,%.6g scissor=%d,%d,%d,%d scissor_test=%d blend=%d depth=%d cull=%d active_texture=0x%04x texture_2d=%d path=%s\n",
                 index, program, mode, count, index_type, element_buffer,
                 viewport[0], viewport[1], viewport[2], viewport[3],
                 clear_color[0], clear_color[1], clear_color[2], clear_color[3],
                 scissor[0], scissor[1], scissor[2], scissor[3],
                 glIsEnabled(GL_SCISSOR_TEST) == GL_TRUE,
                 glIsEnabled(GL_BLEND) == GL_TRUE,
                 glIsEnabled(GL_DEPTH_TEST) == GL_TRUE,
                 glIsEnabled(GL_CULL_FACE) == GL_TRUE,
                 active_texture, texture_2d, path.c_str());
}

const char *opcode_name(unsigned int opcode)
{
    switch (opcode) {
    case IDRIVE_ANGLE_EGL_RPC_INITIALIZE: return "INITIALIZE";
    case IDRIVE_ANGLE_EGL_RPC_TERMINATE: return "TERMINATE";
    case IDRIVE_ANGLE_EGL_RPC_QUERY_STRING: return "QUERY_STRING";
    case IDRIVE_ANGLE_EGL_RPC_GET_CONFIGS: return "GET_CONFIGS";
    case IDRIVE_ANGLE_EGL_RPC_CHOOSE_CONFIG: return "CHOOSE_CONFIG";
    case IDRIVE_ANGLE_EGL_RPC_GET_CONFIG_ATTRIB: return "GET_CONFIG_ATTRIB";
    case IDRIVE_ANGLE_EGL_RPC_CREATE_PBUFFER: return "CREATE_PBUFFER";
    case IDRIVE_ANGLE_EGL_RPC_CREATE_CONTEXT: return "CREATE_CONTEXT";
    case IDRIVE_ANGLE_EGL_RPC_MAKE_CURRENT: return "MAKE_CURRENT";
    case IDRIVE_ANGLE_EGL_RPC_DESTROY_SURFACE: return "DESTROY_SURFACE";
    case IDRIVE_ANGLE_EGL_RPC_DESTROY_CONTEXT: return "DESTROY_CONTEXT";
    case IDRIVE_ANGLE_EGL_RPC_QUERY_SURFACE: return "QUERY_SURFACE";
    case IDRIVE_ANGLE_EGL_RPC_SWAP_BUFFERS: return "SWAP_BUFFERS";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_STRING: return "GL_GET_STRING";
    case IDRIVE_ANGLE_EGL_RPC_QUERY_CONTEXT: return "QUERY_CONTEXT";
    case IDRIVE_ANGLE_EGL_RPC_GL_VIEWPORT: return "GL_VIEWPORT";
    case IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_COLOR: return "GL_CLEAR_COLOR";
    case IDRIVE_ANGLE_EGL_RPC_GL_CLEAR: return "GL_CLEAR";
    case IDRIVE_ANGLE_EGL_RPC_GL_READ_PIXELS: return "GL_READ_PIXELS";
    case IDRIVE_ANGLE_EGL_RPC_CREATE_WINDOW_SURFACE: return "CREATE_WINDOW_SURFACE";
    case IDRIVE_ANGLE_EGL_RPC_SWAP_WINDOW_SURFACE: return "SWAP_WINDOW_SURFACE";
    case IDRIVE_ANGLE_EGL_RPC_GL_SCISSOR: return "GL_SCISSOR";
    case IDRIVE_ANGLE_EGL_RPC_GL_ENABLE: return "GL_ENABLE";
    case IDRIVE_ANGLE_EGL_RPC_GL_DISABLE: return "GL_DISABLE";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_INTEGER: return "GL_GET_INTEGER";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_BOOLEAN: return "GL_GET_BOOLEAN";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_FLOAT: return "GL_GET_FLOAT";
    case IDRIVE_ANGLE_EGL_RPC_GL_GEN_BUFFERS: return "GL_GEN_BUFFERS";
    case IDRIVE_ANGLE_EGL_RPC_GL_GEN_TEXTURES: return "GL_GEN_TEXTURES";
    case IDRIVE_ANGLE_EGL_RPC_GL_CREATE_SHADER: return "GL_CREATE_SHADER";
    case IDRIVE_ANGLE_EGL_RPC_GL_BATCH: return "GL_BATCH";
    case IDRIVE_ANGLE_EGL_RPC_GL_BIND_BUFFER: return "GL_BIND_BUFFER";
    case IDRIVE_ANGLE_EGL_RPC_GL_BIND_TEXTURE: return "GL_BIND_TEXTURE";
    case IDRIVE_ANGLE_EGL_RPC_GL_SHADER_BINARY_CAPTURE: return "GL_SHADER_BINARY_CAPTURE";
    case IDRIVE_ANGLE_EGL_RPC_GL_SHADER_SOURCE: return "GL_SHADER_SOURCE";
    case IDRIVE_ANGLE_EGL_RPC_GL_BUFFER_DATA: return "GL_BUFFER_DATA";
    case IDRIVE_ANGLE_EGL_RPC_GL_BUFFER_SUB_DATA: return "GL_BUFFER_SUB_DATA";
    case IDRIVE_ANGLE_EGL_RPC_GL_TEX_PARAMETERI: return "GL_TEX_PARAMETERI";
    case IDRIVE_ANGLE_EGL_RPC_GL_PIXEL_STOREI: return "GL_PIXEL_STOREI";
    case IDRIVE_ANGLE_EGL_RPC_GL_TEX_IMAGE_2D: return "GL_TEX_IMAGE_2D";
    case IDRIVE_ANGLE_EGL_RPC_GL_TEX_SUB_IMAGE_2D: return "GL_TEX_SUB_IMAGE_2D";
    case IDRIVE_ANGLE_EGL_RPC_GL_COMPILE_SHADER: return "GL_COMPILE_SHADER";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_SHADER_IV: return "GL_GET_SHADER_IV";
    case IDRIVE_ANGLE_EGL_RPC_GL_GENERATE_MIPMAP: return "GL_GENERATE_MIPMAP";
    case IDRIVE_ANGLE_EGL_RPC_GL_CREATE_PROGRAM: return "GL_CREATE_PROGRAM";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_PROGRAM_IV: return "GL_GET_PROGRAM_IV";
    case IDRIVE_ANGLE_EGL_RPC_GL_ATTACH_SHADER: return "GL_ATTACH_SHADER";
    case IDRIVE_ANGLE_EGL_RPC_GL_LINK_PROGRAM: return "GL_LINK_PROGRAM";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_UNIFORM: return "GL_GET_ACTIVE_UNIFORM";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_ATTRIB: return "GL_GET_ACTIVE_ATTRIB";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_ATTRIB_LOCATION: return "GL_GET_ATTRIB_LOCATION";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_UNIFORM_LOCATION: return "GL_GET_UNIFORM_LOCATION";
    case IDRIVE_ANGLE_EGL_RPC_GL_USE_PROGRAM: return "GL_USE_PROGRAM";
    case IDRIVE_ANGLE_EGL_RPC_GL_ENABLE_VERTEX_ATTRIB_ARRAY: return "GL_ENABLE_VERTEX_ATTRIB_ARRAY";
    case IDRIVE_ANGLE_EGL_RPC_GL_DISABLE_VERTEX_ATTRIB_ARRAY: return "GL_DISABLE_VERTEX_ATTRIB_ARRAY";
    case IDRIVE_ANGLE_EGL_RPC_GL_VERTEX_ATTRIB_POINTER: return "GL_VERTEX_ATTRIB_POINTER";
    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1I: return "GL_UNIFORM_1I";
    case IDRIVE_ANGLE_EGL_RPC_GL_ACTIVE_TEXTURE: return "GL_ACTIVE_TEXTURE";
    case IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ARRAYS: return "GL_DRAW_ARRAYS";
    case IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ELEMENTS: return "GL_DRAW_ELEMENTS";
    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1IV: return "GL_UNIFORM_1IV";
    case IDRIVE_ANGLE_EGL_RPC_GL_BLEND_FUNC_SEPARATE: return "GL_BLEND_FUNC_SEPARATE";
    case IDRIVE_ANGLE_EGL_RPC_GL_BLEND_COLOR: return "GL_BLEND_COLOR";
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_PROGRAM_INFO_LOG: return "GL_GET_PROGRAM_INFO_LOG";
    case IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_FUNC: return "GL_DEPTH_FUNC";
    case IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_MASK: return "GL_DEPTH_MASK";
    case IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_FUNC_SEPARATE: return "GL_STENCIL_FUNC_SEPARATE";
    case IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_MASK_SEPARATE: return "GL_STENCIL_MASK_SEPARATE";
    case IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_OP_SEPARATE: return "GL_STENCIL_OP_SEPARATE";
    case IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_STENCIL: return "GL_CLEAR_STENCIL";
    case IDRIVE_ANGLE_EGL_RPC_GL_BLEND_EQUATION_SEPARATE: return "GL_BLEND_EQUATION_SEPARATE";
    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_FV: return "GL_UNIFORM_FV";
    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_MATRIX_FV: return "GL_UNIFORM_MATRIX_FV";
    default: return "UNKNOWN";
    }
}

bool write_all_at(int fd, const unsigned char *data, std::size_t size,
                  std::uint64_t offset)
{
    std::size_t written = 0;
    while (written < size) {
        const ssize_t result = pwrite(fd, data + written, size - written,
                                      static_cast<off_t>(offset + written));
        if (result <= 0) {
            if (result < 0 && errno == EINTR) continue;
            return false;
        }
        written += static_cast<std::size_t>(result);
    }
    return true;
}

bool ensure_display()
{
    if (g_display_initialized) return true;
#if defined(IDRIVE_USE_MESA)
    constexpr const char *backend_name = "mesa-surfaceless";
    g_display = eglGetPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, nullptr, nullptr);
#else
#if defined(__APPLE__)
    constexpr EGLint backend = EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE;
    constexpr const char *backend_name = "metal";
#else
    constexpr EGLint backend = EGL_PLATFORM_ANGLE_TYPE_VULKAN_ANGLE;
    constexpr const char *backend_name = "vulkan";
#endif
    const EGLAttrib attributes[] = {
        EGL_PLATFORM_ANGLE_TYPE_ANGLE, backend,
        EGL_NONE,
    };
    g_display = eglGetPlatformDisplay(EGL_PLATFORM_ANGLE_ANGLE, nullptr, attributes);
#endif
    if (g_display == EGL_NO_DISPLAY ||
        eglInitialize(g_display, &g_major, &g_minor) != EGL_TRUE ||
        eglBindAPI(EGL_OPENGL_ES_API) != EGL_TRUE) {
        std::fprintf(stderr, "ANGLE_EGL_RPC_INIT_FAIL egl=0x%04x\n", eglGetError());
        return false;
    }
    g_display_initialized = true;
    std::fprintf(stderr, "ANGLE_EGL_RPC_BACKEND backend=%s egl=%d.%d depth_requirement=24\n",
                 backend_name, g_major, g_minor);
    return true;
}

bool parse_attributes(const std::vector<unsigned char> &payload,
                      std::vector<EGLint> &attributes)
{
    if (payload.size() % 4 != 0 ||
        payload.size() > IDRIVE_ANGLE_EGL_RPC_MAX_ATTR_INTS * 4u) {
        return false;
    }
    attributes.reserve(payload.size() / 4);
    for (std::size_t i = 0; i < payload.size(); i += 4) {
        attributes.push_back(static_cast<EGLint>(idrive_angle_egl_rpc_u32(payload.data() + i)));
    }
    if (attributes.empty() || attributes.back() != EGL_NONE ||
        attributes.size() % 2u == 0) return false;
    return true;
}

void append_u32(std::vector<unsigned char> &payload, unsigned int value)
{
    const std::size_t old_size = payload.size();
    payload.resize(old_size + 4);
    idrive_angle_egl_rpc_put_u32(payload.data() + old_size, value);
}

void destroy_client_objects(unsigned int client_id, ClientState &client)
{
    if (g_current_context_client == client_id &&
        eglGetCurrentContext() != EGL_NO_CONTEXT &&
        eglMakeCurrent(g_display, EGL_NO_SURFACE, EGL_NO_SURFACE,
                       EGL_NO_CONTEXT) == EGL_TRUE) {
        g_current_context_client = 0;
    }
    for (const auto &entry : client.contexts) {
        (void)eglDestroyContext(g_display, entry.second);
    }
    for (const auto &entry : client.surfaces) {
        (void)eglDestroySurface(g_display, entry.second);
    }
    client.contexts.clear();
    client.surfaces.clear();
    client.configs.clear();
}

bool process_request(const unsigned char *request,
                     const std::vector<unsigned char> &payload,
                     unsigned char *response,
                     std::vector<unsigned char> &response_payload)
{
    const unsigned int opcode = idrive_angle_egl_rpc_u16(request + 6);
    const unsigned int client_id = idrive_angle_egl_rpc_u32(request + 8);
    const unsigned int a = idrive_angle_egl_rpc_u32(request + 12);
    const unsigned int b = idrive_angle_egl_rpc_u32(request + 16);
    const unsigned int c = idrive_angle_egl_rpc_u32(request + 20);
    ClientState &client = g_clients[client_id];
    if (opcode != IDRIVE_ANGLE_EGL_RPC_INITIALIZE && !ensure_display()) {
        set_error(response, EGL_NOT_INITIALIZED);
        return false;
    }

    switch (opcode) {
    case IDRIVE_ANGLE_EGL_RPC_INITIALIZE:
        if (!ensure_display()) {
            set_error(response, EGL_NOT_INITIALIZED);
            return false;
        }
        set_value(response, 0, static_cast<unsigned int>(g_major));
        set_value(response, 1, static_cast<unsigned int>(g_minor));
        return true;

    case IDRIVE_ANGLE_EGL_RPC_TERMINATE:
        destroy_client_objects(client_id, client);
        g_clients.erase(client_id);
        return true;

    case IDRIVE_ANGLE_EGL_RPC_QUERY_STRING: {
        const char *value = eglQueryString(g_display, static_cast<EGLint>(a));
        if (!value) {
            set_error(response, eglGetError());
            return false;
        }
        const std::size_t length = std::strlen(value) + 1;
        if (length > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD) {
            set_error(response, EGL_BAD_ALLOC);
            return false;
        }
        response_payload.assign(value, value + length);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GET_CONFIGS:
    case IDRIVE_ANGLE_EGL_RPC_CHOOSE_CONFIG: {
        std::vector<EGLint> attributes;
        if (opcode == IDRIVE_ANGLE_EGL_RPC_CHOOSE_CONFIG &&
            !parse_attributes(payload, attributes)) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        if (opcode == IDRIVE_ANGLE_EGL_RPC_CHOOSE_CONFIG) {
            for (std::size_t i = 0; i + 1 < attributes.size(); i += 2) {
                if (attributes[i] == EGL_NONE) break;
                if (attributes[i] == kEglSurfaceType &&
                    (attributes[i + 1] & kEglWindowBit) != 0) {
                    attributes[i + 1] = (attributes[i + 1] & ~kEglWindowBit) |
                        kEglPbufferBit;
                }
                if (g_requires_gles3 && attributes[i] == kEglRenderableType &&
                    (attributes[i + 1] & kEglOpenGles2Bit) != 0) {
                    attributes[i + 1] |= kEglOpenGles3Bit;
                }
            }
        }
        const unsigned int capacity = opcode == IDRIVE_ANGLE_EGL_RPC_GET_CONFIGS
            ? a : b;
        const unsigned int safe_capacity = std::min<unsigned int>(capacity, kMaxConfigResults);
        std::vector<EGLConfig> configs(safe_capacity ? safe_capacity : 1, nullptr);
        EGLint count = 0;
        const EGLBoolean ok = opcode == IDRIVE_ANGLE_EGL_RPC_GET_CONFIGS
            ? eglGetConfigs(g_display, safe_capacity ? configs.data() : nullptr,
                            static_cast<EGLint>(safe_capacity), &count)
            : eglChooseConfig(g_display, attributes.data(),
                              safe_capacity ? configs.data() : nullptr,
                              static_cast<EGLint>(safe_capacity), &count);
        if (ok != EGL_TRUE) {
            set_error(response, eglGetError());
            return false;
        }
        set_value(response, 0, static_cast<unsigned int>(count));
        const unsigned int copied = std::min<unsigned int>(
            static_cast<unsigned int>(count), safe_capacity);
        for (unsigned int i = 0; i < copied; ++i) {
            unsigned int id = 0;
            for (const auto &entry : client.configs) {
                if (entry.second == configs[i]) { id = entry.first; break; }
            }
            if (id == 0) {
                id = client.next_config++;
                client.configs.emplace(id, configs[i]);
            }
            append_u32(response_payload, id);
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GET_CONFIG_ATTRIB: {
        const auto config = client.configs.find(a);
        if (config == client.configs.end()) {
            set_error(response, EGL_BAD_CONFIG);
            return false;
        }
        EGLint value = 0;
        if (eglGetConfigAttrib(g_display, config->second,
                                static_cast<EGLint>(b), &value) != EGL_TRUE) {
            set_error(response, eglGetError());
            return false;
        }
        if (g_requires_gles3 && static_cast<EGLint>(b) == kEglRenderableType) {
            value &= ~kEglOpenGles3Bit;
        }
        if (static_cast<EGLint>(b) == kEglSurfaceType) value |= kEglWindowBit;
        set_value(response, 0, static_cast<unsigned int>(value));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_CREATE_PBUFFER: {
        const auto config = client.configs.find(a);
        std::vector<EGLint> attributes;
        if (config == client.configs.end()) {
            set_error(response, EGL_BAD_CONFIG);
            return false;
        }
        if (!parse_attributes(payload, attributes)) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        EGLSurface surface = eglCreatePbufferSurface(g_display, config->second,
                                                     attributes.data());
        if (surface == EGL_NO_SURFACE) {
            set_error(response, eglGetError());
            return false;
        }
        const unsigned int id = client.next_surface++;
        client.surfaces.emplace(id, surface);
        set_value(response, 0, id);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_CREATE_WINDOW_SURFACE: {
        const auto config = client.configs.find(a);
        const unsigned int width = b;
        const unsigned int height = c;
        if (config == client.configs.end()) {
            set_error(response, EGL_BAD_CONFIG);
            return false;
        }
        if (payload.size() != 0 || width == 0 || height == 0 ||
            static_cast<std::uint64_t>(width) * height * 4u >
                IDRIVE_ANGLE_EGL_RPC_MAX_FRAME_BYTES) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        const EGLint attributes[] = {
            EGL_WIDTH, static_cast<EGLint>(width),
            EGL_HEIGHT, static_cast<EGLint>(height),
            EGL_NONE,
        };
        EGLSurface surface = eglCreatePbufferSurface(g_display, config->second,
                                                     attributes);
        if (surface == EGL_NO_SURFACE) {
            set_error(response, eglGetError());
            return false;
        }
        const unsigned int id = client.next_surface++;
        client.surfaces.emplace(id, surface);
        set_value(response, 0, id);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_CREATE_CONTEXT: {
        const auto config = client.configs.find(a);
        std::vector<EGLint> attributes;
        if (config == client.configs.end()) {
            set_error(response, EGL_BAD_CONFIG);
            return false;
        }
        if (!parse_attributes(payload, attributes)) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        if (g_requires_gles3) {
            bool found_client_version = false;
            bool promoted = false;
            for (std::size_t i = 0; i + 1 < attributes.size(); i += 2) {
                if (attributes[i] == EGL_NONE) break;
                if (attributes[i] == kEglContextClientVersion) {
                    found_client_version = true;
                    if (attributes[i + 1] < 3) {
                        attributes[i + 1] = 3;
                        promoted = true;
                    }
                }
            }
            if (!found_client_version) {
                attributes.insert(attributes.end() - 1,
                                  {kEglContextClientVersion, 3});
                promoted = true;
            }
            if (promoted) {
                std::fprintf(stderr,
                             "ANGLE_CONTEXT_GLES3_PROMOTION reason=essl300-shader-map\n");
            }
        }
        EGLContext share = EGL_NO_CONTEXT;
        if (b != 0) {
            const auto shared = client.contexts.find(b);
            if (shared == client.contexts.end()) {
                set_error(response, EGL_BAD_CONTEXT);
                return false;
            }
            share = shared->second;
        }
        EGLContext context = eglCreateContext(g_display, config->second,
                                              share, attributes.data());
        if (context == EGL_NO_CONTEXT) {
            set_error(response, eglGetError());
            return false;
        }
        const unsigned int id = client.next_context++;
        client.contexts.emplace(id, context);
        set_value(response, 0, id);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_MAKE_CURRENT: {
        EGLSurface draw = EGL_NO_SURFACE;
        EGLSurface read = EGL_NO_SURFACE;
        EGLContext context = EGL_NO_CONTEXT;
        if (a != 0) {
            const auto found = client.surfaces.find(a);
            if (found == client.surfaces.end()) { set_error(response, EGL_BAD_SURFACE); return false; }
            draw = found->second;
        }
        if (b != 0) {
            const auto found = client.surfaces.find(b);
            if (found == client.surfaces.end()) { set_error(response, EGL_BAD_SURFACE); return false; }
            read = found->second;
        }
        if (c != 0) {
            const auto found = client.contexts.find(c);
            if (found == client.contexts.end()) { set_error(response, EGL_BAD_CONTEXT); return false; }
            context = found->second;
        }
        if (eglMakeCurrent(g_display, draw, read, context) != EGL_TRUE) {
            set_error(response, eglGetError());
            return false;
        }
        g_current_context_client = context == EGL_NO_CONTEXT ? 0 : client_id;
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_DESTROY_SURFACE: {
        const auto surface = client.surfaces.find(a);
        if (surface == client.surfaces.end()) { set_error(response, EGL_BAD_SURFACE); return false; }
        if (eglDestroySurface(g_display, surface->second) != EGL_TRUE) {
            set_error(response, eglGetError());
            return false;
        }
        client.surfaces.erase(surface);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_DESTROY_CONTEXT: {
        const auto context = client.contexts.find(a);
        if (context == client.contexts.end()) { set_error(response, EGL_BAD_CONTEXT); return false; }
        if (eglDestroyContext(g_display, context->second) != EGL_TRUE) {
            set_error(response, eglGetError());
            return false;
        }
        client.contexts.erase(context);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_QUERY_SURFACE: {
        const auto surface = client.surfaces.find(a);
        if (surface == client.surfaces.end()) { set_error(response, EGL_BAD_SURFACE); return false; }
        EGLint value = 0;
        if (eglQuerySurface(g_display, surface->second, static_cast<EGLint>(b), &value) != EGL_TRUE) {
            set_error(response, eglGetError());
            return false;
        }
        set_value(response, 0, static_cast<unsigned int>(value));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_SWAP_BUFFERS: {
        const auto surface = client.surfaces.find(a);
        if (surface == client.surfaces.end()) { set_error(response, EGL_BAD_SURFACE); return false; }
        if (eglSwapBuffers(g_display, surface->second) != EGL_TRUE) {
            set_error(response, eglGetError());
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_SWAP_WINDOW_SURFACE: {
        const auto surface = client.surfaces.find(a);
        if (surface == client.surfaces.end()) {
            set_error(response, EGL_BAD_SURFACE);
            return false;
        }
        if (payload.size() != 16 || g_guest_ram_fd < 0 ||
            eglGetCurrentContext() == EGL_NO_CONTEXT ||
            eglGetCurrentSurface(EGL_DRAW) != surface->second) {
            set_error(response, EGL_BAD_ACCESS);
            return false;
        }
        const unsigned int width = b;
        const unsigned int height = c;
        const unsigned int stride = idrive_angle_egl_rpc_u32(payload.data());
        const unsigned int format = idrive_angle_egl_rpc_u32(payload.data() + 4);
        const std::uint64_t physical_address =
            static_cast<std::uint64_t>(idrive_angle_egl_rpc_u32(payload.data() + 8)) |
            (static_cast<std::uint64_t>(idrive_angle_egl_rpc_u32(payload.data() + 12)) << 32);
        const std::uint64_t active_bytes = static_cast<std::uint64_t>(width) * height * 4u;
        const std::uint64_t frame_bytes = static_cast<std::uint64_t>(stride) * height;
        EGLint surface_width = 0, surface_height = 0;
        if (width == 0 || height == 0 || format != kScreenFormatRgba8888 ||
            stride < static_cast<std::uint64_t>(width) * 4u ||
            active_bytes > IDRIVE_ANGLE_EGL_RPC_MAX_FRAME_BYTES ||
            frame_bytes > IDRIVE_ANGLE_EGL_RPC_MAX_FRAME_BYTES ||
            physical_address < kGuestRamBase ||
            eglQuerySurface(g_display, surface->second, 0x3057, &surface_width) != EGL_TRUE ||
            eglQuerySurface(g_display, surface->second, 0x3056, &surface_height) != EGL_TRUE ||
            surface_width != static_cast<EGLint>(width) ||
            surface_height != static_cast<EGLint>(height)) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        const std::uint64_t offset = physical_address - kGuestRamBase;
        if (offset > g_guest_ram_size || frame_bytes > g_guest_ram_size - offset) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }

        // A read into client memory already waits for the preceding draws.
        static std::vector<unsigned char> gl_pixels;
        static std::vector<unsigned char> frame;
        gl_pixels.resize(static_cast<std::size_t>(active_bytes));
        glReadPixels(0, 0, static_cast<GLsizei>(width),
                     static_cast<GLsizei>(height), kGlRgba, kGlUnsignedByte,
                     gl_pixels.data());
        const GLenum read_error = glGetError();
        if (read_error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(read_error));
            return false;
        }
        if (eglSwapBuffers(g_display, surface->second) != EGL_TRUE) {
            set_error(response, eglGetError());
            return false;
        }

        frame.resize(static_cast<std::size_t>(frame_bytes));
        const std::size_t row_bytes = static_cast<std::size_t>(width) * 4u;
        for (unsigned int y = 0; y < height; ++y) {
            const unsigned int gl_y = height - 1u - y;
            const unsigned char *source = gl_pixels.data() +
                static_cast<std::size_t>(gl_y) * row_bytes;
            unsigned char *destination = frame.data() +
                static_cast<std::size_t>(y) * stride;
            for (unsigned int x = 0; x < width; ++x) {
                destination[x * 4u + 0u] = source[x * 4u + 2u];
                destination[x * 4u + 1u] = source[x * 4u + 1u];
                destination[x * 4u + 2u] = source[x * 4u + 0u];
                destination[x * 4u + 3u] = source[x * 4u + 3u];
            }
            std::memset(destination + row_bytes, 0, stride - row_bytes);
        }
        if (!write_all_at(g_guest_ram_fd, frame.data(), frame.size(), offset)) {
            set_error(response, EGL_BAD_ALLOC);
            return false;
        }
        const std::uint64_t hash = frame_hash(frame);
        set_value(response, 0, static_cast<unsigned int>(hash));
        set_value(response, 1, static_cast<unsigned int>(hash >> 32));
        set_value(response, 2, static_cast<unsigned int>(frame.size()));
        std::fprintf(stderr,
                     "ANGLE_SCREEN_FRAME client=%u surface=%u physical=0x%llx offset=0x%llx stride=%u width=%u height=%u format=%u bytes=%zu fnv1a64=%016llx present_us=%lld\n",
                     client_id, a,
                     static_cast<unsigned long long>(physical_address),
                     static_cast<unsigned long long>(offset), stride, width,
                     height, format, frame.size(),
                     static_cast<unsigned long long>(hash),
                     static_cast<long long>(std::chrono::duration_cast<std::chrono::microseconds>(
                         std::chrono::steady_clock::now().time_since_epoch()).count()));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GET_STRING: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        const GLubyte *value = glGetString(static_cast<GLenum>(a));
        if (!value) {
            set_error(response, glGetError());
            return false;
        }
        const std::size_t length = std::strlen(reinterpret_cast<const char *>(value)) + 1;
        if (length > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD) {
            set_error(response, EGL_BAD_ALLOC);
            return false;
        }
        response_payload.assign(value, value + length);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GET_INTEGER: {
        std::size_t value_count = 1;
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        switch (static_cast<GLenum>(a)) {
        case GL_VIEWPORT:
        case GL_SCISSOR_BOX:
            value_count = 4;
            break;
        case GL_MAX_VIEWPORT_DIMS:
        case GL_ALIASED_LINE_WIDTH_RANGE:
        case GL_ALIASED_POINT_SIZE_RANGE:
            value_count = 2;
            break;
        case GL_COMPRESSED_TEXTURE_FORMATS: {
            GLint formats = 0;
            glGetIntegerv(GL_NUM_COMPRESSED_TEXTURE_FORMATS, &formats);
            const GLenum error = glGetError();
            if (error != GL_NO_ERROR || formats < 0) {
                set_error(response, static_cast<EGLint>(
                    error == GL_NO_ERROR ? kGlInvalidValue : error));
                return false;
            }
            value_count = static_cast<std::size_t>(formats);
            break;
        }
        case GL_SHADER_BINARY_FORMATS: {
            GLint formats = 0;
            glGetIntegerv(GL_NUM_SHADER_BINARY_FORMATS, &formats);
            const GLenum error = glGetError();
            if (error != GL_NO_ERROR || formats < 0) {
                set_error(response, static_cast<EGLint>(
                    error == GL_NO_ERROR ? kGlInvalidValue : error));
                return false;
            }
            value_count = static_cast<std::size_t>(formats);
            break;
        }
        default:
            break;
        }
        if (value_count > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / 4u) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        std::vector<GLint> values(value_count ? value_count : 1u, 0);
        glGetIntegerv(static_cast<GLenum>(a), values.data());
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        for (std::size_t i = 0; i < value_count; ++i)
            append_u32(response_payload, static_cast<unsigned int>(values[i]));
        set_value(response, 0, static_cast<unsigned int>(value_count));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GET_BOOLEAN: {
        std::size_t value_count = 1;
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        switch (static_cast<GLenum>(a)) {
        case GL_VIEWPORT:
        case GL_SCISSOR_BOX:
        case GL_BLEND_COLOR:
        case GL_COLOR_CLEAR_VALUE:
        case GL_COLOR_WRITEMASK:
            value_count = 4;
            break;
        case GL_DEPTH_RANGE:
        case GL_MAX_VIEWPORT_DIMS:
        case GL_ALIASED_LINE_WIDTH_RANGE:
        case GL_ALIASED_POINT_SIZE_RANGE:
            value_count = 2;
            break;
        case GL_COMPRESSED_TEXTURE_FORMATS: {
            GLint formats = 0;
            glGetIntegerv(GL_NUM_COMPRESSED_TEXTURE_FORMATS, &formats);
            const GLenum error = glGetError();
            if (error != GL_NO_ERROR || formats < 0) {
                set_error(response, static_cast<EGLint>(
                    error == GL_NO_ERROR ? kGlInvalidValue : error));
                return false;
            }
            value_count = static_cast<std::size_t>(formats);
            break;
        }
        case GL_SHADER_BINARY_FORMATS: {
            GLint formats = 0;
            glGetIntegerv(GL_NUM_SHADER_BINARY_FORMATS, &formats);
            const GLenum error = glGetError();
            if (error != GL_NO_ERROR || formats < 0) {
                set_error(response, static_cast<EGLint>(
                    error == GL_NO_ERROR ? kGlInvalidValue : error));
                return false;
            }
            value_count = static_cast<std::size_t>(formats);
            break;
        }
        default:
            break;
        }
        if (value_count > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        std::vector<GLboolean> values(value_count ? value_count : 1u,
                                      static_cast<GLboolean>(GL_FALSE));
        glGetBooleanv(static_cast<GLenum>(a), values.data());
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        response_payload.insert(response_payload.end(), values.begin(),
                                values.begin() + value_count);
        set_value(response, 0, static_cast<unsigned int>(value_count));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GET_FLOAT: {
        std::size_t value_count = 1;
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        switch (static_cast<GLenum>(a)) {
        case GL_VIEWPORT:
        case GL_SCISSOR_BOX:
        case GL_BLEND_COLOR:
        case GL_COLOR_CLEAR_VALUE:
        case GL_COLOR_WRITEMASK:
            value_count = 4;
            break;
        case GL_DEPTH_RANGE:
        case GL_MAX_VIEWPORT_DIMS:
        case GL_ALIASED_LINE_WIDTH_RANGE:
        case GL_ALIASED_POINT_SIZE_RANGE:
            value_count = 2;
            break;
        case GL_COMPRESSED_TEXTURE_FORMATS: {
            GLint formats = 0;
            glGetIntegerv(GL_NUM_COMPRESSED_TEXTURE_FORMATS, &formats);
            const GLenum error = glGetError();
            if (error != GL_NO_ERROR || formats < 0) {
                set_error(response, static_cast<EGLint>(
                    error == GL_NO_ERROR ? kGlInvalidValue : error));
                return false;
            }
            value_count = static_cast<std::size_t>(formats);
            break;
        }
        case GL_SHADER_BINARY_FORMATS: {
            GLint formats = 0;
            glGetIntegerv(GL_NUM_SHADER_BINARY_FORMATS, &formats);
            const GLenum error = glGetError();
            if (error != GL_NO_ERROR || formats < 0) {
                set_error(response, static_cast<EGLint>(
                    error == GL_NO_ERROR ? kGlInvalidValue : error));
                return false;
            }
            value_count = static_cast<std::size_t>(formats);
            break;
        }
        default:
            break;
        }
        if (value_count > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / sizeof(GLfloat)) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        std::vector<GLfloat> values(value_count ? value_count : 1u, 0.0f);
        glGetFloatv(static_cast<GLenum>(a), values.data());
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        for (std::size_t i = 0; i < value_count; ++i) {
            std::uint32_t bits = 0;
            static_assert(sizeof(bits) == sizeof(values[i]),
                          "GLfloat must be a 32-bit IEEE-754 value");
            std::memcpy(&bits, &values[i], sizeof(bits));
            append_u32(response_payload, static_cast<unsigned int>(bits));
        }
        set_value(response, 0, static_cast<unsigned int>(value_count));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GEN_BUFFERS:
    case IDRIVE_ANGLE_EGL_RPC_GL_GEN_TEXTURES: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty() || a > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / sizeof(GLuint)) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        std::vector<GLuint> objects(a);
        if (opcode == IDRIVE_ANGLE_EGL_RPC_GL_GEN_BUFFERS)
            glGenBuffers(static_cast<GLsizei>(a), objects.data());
        else
            glGenTextures(static_cast<GLsizei>(a), objects.data());
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        for (const GLuint object : objects) append_u32(response_payload, object);
        set_value(response, 0, a);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_CREATE_SHADER: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const GLuint shader = glCreateShader(static_cast<GLenum>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        set_value(response, 0, shader);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_CREATE_PROGRAM: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (a || b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const GLuint program = glCreateProgram();
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        set_value(response, 0, program);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GET_PROGRAM_IV: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!a || !b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        GLint value = 0;
        glGetProgramiv(static_cast<GLuint>(a), static_cast<GLenum>(b), &value);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        set_value(response, 0, static_cast<unsigned int>(value));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GET_PROGRAM_INFO_LOG: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!a || b > IDRIVE_ANGLE_EGL_RPC_MAX_STRING_BYTES || c ||
            !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        std::vector<GLchar> log_buffer(b ? b : 1u, '\0');
        GLsizei length = 0;
        glGetProgramInfoLog(static_cast<GLuint>(a), static_cast<GLsizei>(b),
                            &length, log_buffer.data());
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        if (length < 0 || static_cast<unsigned int>(length) > b) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        set_value(response, 0, static_cast<unsigned int>(length));
        response_payload.assign(log_buffer.begin(), log_buffer.begin() + length);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_ATTACH_SHADER: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!a || !b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glAttachShader(static_cast<GLuint>(a), static_cast<GLuint>(b));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        const auto shader_aliases =
            g_shader_uniform_aliases.find(static_cast<GLuint>(b));
        if (shader_aliases != g_shader_uniform_aliases.end()) {
            auto &program_aliases =
                g_program_uniform_aliases[static_cast<GLuint>(a)];
            for (const auto &alias : shader_aliases->second) {
                const bool already_present = std::any_of(
                    program_aliases.begin(), program_aliases.end(),
                    [&](const auto &existing) {
                        return existing.native_name == alias.native_name;
                    });
                if (!already_present) {
                    program_aliases.push_back(alias);
                }
                std::fprintf(stderr,
                             "ANGLE_PROGRAM_UNIFORM_ALIAS program=%u shader=%u native=%s host=%s\n",
                             static_cast<GLuint>(a), static_cast<GLuint>(b),
                             alias.native_name.c_str(), alias.host_name.c_str());
            }
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_LINK_PROGRAM: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!a || b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glLinkProgram(static_cast<GLuint>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_UNIFORM:
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_ATTRIB: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!a || !payload.empty() || c > IDRIVE_ANGLE_EGL_RPC_MAX_STRING_BYTES) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        std::vector<GLchar> name(c ? c : 1u, '\0');
        GLsizei length = 0;
        GLint size = 0;
        GLenum type = 0;
        GLchar *name_output = c ? name.data() : nullptr;
        if (opcode == IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_UNIFORM) {
            glGetActiveUniform(static_cast<GLuint>(a), static_cast<GLuint>(b),
                static_cast<GLsizei>(c), &length, &size, &type, name_output);
        } else {
            glGetActiveAttrib(static_cast<GLuint>(a), static_cast<GLuint>(b),
                static_cast<GLsizei>(c), &length, &size, &type, name_output);
        }
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        if (length < 0 || static_cast<unsigned int>(length) > c) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (opcode == IDRIVE_ANGLE_EGL_RPC_GL_GET_ACTIVE_UNIFORM) {
            const auto aliases =
                g_program_uniform_aliases.find(static_cast<GLuint>(a));
            if (aliases != g_program_uniform_aliases.end()) {
                const std::string host_name(
                    name.data(), static_cast<std::size_t>(length));
                const auto alias = std::find_if(
                    aliases->second.begin(), aliases->second.end(),
                    [&](const auto &candidate) {
                        return candidate.host_name == host_name;
                    });
                if (alias != aliases->second.end()) {
                    if (alias->native_name.size() > c) {
                        set_error(response, kGlInvalidOperation);
                        return false;
                    }
                    std::fill(name.begin(), name.end(), '\0');
                    std::copy(alias->native_name.begin(), alias->native_name.end(),
                              name.begin());
                    length = static_cast<GLsizei>(alias->native_name.size());
                }
            }
        }
        set_value(response, 0, static_cast<unsigned int>(length));
        set_value(response, 1, static_cast<unsigned int>(size));
        set_value(response, 2, static_cast<unsigned int>(type));
        response_payload.assign(name.begin(), name.begin() + length);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GET_ATTRIB_LOCATION:
    case IDRIVE_ANGLE_EGL_RPC_GL_GET_UNIFORM_LOCATION: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!a || c || b > IDRIVE_ANGLE_EGL_RPC_MAX_STRING_BYTES ||
            payload.size() != b) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const std::string name(payload.begin(), payload.end());
        std::string host_name = name;
        if (opcode == IDRIVE_ANGLE_EGL_RPC_GL_GET_UNIFORM_LOCATION) {
            const auto aliases =
                g_program_uniform_aliases.find(static_cast<GLuint>(a));
            if (aliases != g_program_uniform_aliases.end()) {
                const auto alias = std::find_if(
                    aliases->second.begin(), aliases->second.end(),
                    [&](const auto &candidate) {
                        return candidate.native_name == name;
                    });
                if (alias != aliases->second.end()) {
                    host_name = alias->host_name;
                    std::fprintf(stderr,
                                 "ANGLE_UNIFORM_LOCATION_ALIAS program=%u native=%s host=%s\n",
                                 static_cast<GLuint>(a), name.c_str(),
                                 host_name.c_str());
                }
            }
        }
        GLint location = -1;
        if (opcode == IDRIVE_ANGLE_EGL_RPC_GL_GET_ATTRIB_LOCATION) {
            location = glGetAttribLocation(static_cast<GLuint>(a), name.c_str());
        } else {
            location = glGetUniformLocation(static_cast<GLuint>(a), host_name.c_str());
        }
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        set_value(response, 0, static_cast<unsigned int>(location));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_USE_PROGRAM: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glUseProgram(static_cast<GLuint>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_ENABLE_VERTEX_ATTRIB_ARRAY:
    case IDRIVE_ANGLE_EGL_RPC_GL_DISABLE_VERTEX_ATTRIB_ARRAY: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        if (opcode == IDRIVE_ANGLE_EGL_RPC_GL_ENABLE_VERTEX_ATTRIB_ARRAY)
            glEnableVertexAttribArray(static_cast<GLuint>(a));
        else
            glDisableVertexAttribArray(static_cast<GLuint>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_VERTEX_ATTRIB_POINTER: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (payload.size() != 12 || b < 1 || b > 4 ||
            idrive_angle_egl_rpc_u32(payload.data()) > 1) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const GLboolean normalized = static_cast<GLboolean>(
            idrive_angle_egl_rpc_u32(payload.data()));
        const GLsizei stride = static_cast<GLsizei>(
            idrive_angle_egl_rpc_u32(payload.data() + 4));
        const std::uintptr_t pointer = static_cast<std::uintptr_t>(
            idrive_angle_egl_rpc_u32(payload.data() + 8));
        if (stride < 0) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glVertexAttribPointer(static_cast<GLuint>(a), static_cast<GLint>(b),
            static_cast<GLenum>(c), normalized, stride,
            reinterpret_cast<const void *>(pointer));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1I: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glUniform1i(static_cast<GLint>(a), static_cast<GLint>(b));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_1IV: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b > 0x7fffffffu || c ||
            payload.size() != static_cast<std::size_t>(b) * 4u) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        std::vector<GLint> values(b);
        for (unsigned int i = 0; i < b; ++i) {
            values[i] = static_cast<GLint>(idrive_angle_egl_rpc_u32(
                payload.data() + static_cast<std::size_t>(i) * 4u));
        }
        glUniform1iv(static_cast<GLint>(a), static_cast<GLsizei>(b),
                     b ? values.data() : nullptr);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_FV: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b > 0x7fffffffu || c < 1 || c > 4 ||
            payload.size() != static_cast<std::size_t>(b) * c * 4u) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        std::vector<GLfloat> values(static_cast<std::size_t>(b) * c);
        for (std::size_t i = 0; i < values.size(); ++i)
            values[i] = rpc_float(payload.data() + i * 4u);
        const GLfloat *data = values.empty() ? nullptr : values.data();
        switch (c) {
        case 1: glUniform1fv(static_cast<GLint>(a), static_cast<GLsizei>(b), data); break;
        case 2: glUniform2fv(static_cast<GLint>(a), static_cast<GLsizei>(b), data); break;
        case 3: glUniform3fv(static_cast<GLint>(a), static_cast<GLsizei>(b), data); break;
        case 4: glUniform4fv(static_cast<GLint>(a), static_cast<GLsizei>(b), data); break;
        }
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_UNIFORM_MATRIX_FV: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b > 0x7fffffffu || c < 2 || c > 4 || payload.size() < 4u ||
            idrive_angle_egl_rpc_u32(payload.data()) != 0u ||
            payload.size() != 4u + static_cast<std::size_t>(b) * c * c * 4u) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const std::size_t components = static_cast<std::size_t>(c) * c;
        std::vector<GLfloat> values(static_cast<std::size_t>(b) * components);
        for (std::size_t i = 0; i < values.size(); ++i)
            values[i] = rpc_float(payload.data() + 4u + i * 4u);
        const GLfloat *data = values.empty() ? nullptr : values.data();
        switch (c) {
        case 2: glUniformMatrix2fv(static_cast<GLint>(a), static_cast<GLsizei>(b), GL_FALSE, data); break;
        case 3: glUniformMatrix3fv(static_cast<GLint>(a), static_cast<GLsizei>(b), GL_FALSE, data); break;
        case 4: glUniformMatrix4fv(static_cast<GLint>(a), static_cast<GLsizei>(b), GL_FALSE, data); break;
        }
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_BLEND_FUNC_SEPARATE: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (payload.size() != 4u) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const GLenum dst_alpha = static_cast<GLenum>(
            idrive_angle_egl_rpc_u32(payload.data()));
        glBlendFuncSeparate(static_cast<GLenum>(a), static_cast<GLenum>(b),
                            static_cast<GLenum>(c), dst_alpha);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_FUNC_SEPARATE:
    case IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_MASK_SEPARATE:
    case IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_OP_SEPARATE:
    case IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_STENCIL:
    case IDRIVE_ANGLE_EGL_RPC_GL_BLEND_EQUATION_SEPARATE: {
        if (g_current_context_client != client_id ||
            eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        const bool fourth_argument =
            opcode == IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_FUNC_SEPARATE ||
            opcode == IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_OP_SEPARATE;
        if (payload.size() != (fourth_argument ? 4u : 0u) ||
            (!fourth_argument && c) ||
            (opcode == IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_STENCIL && b)) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        switch (opcode) {
        case IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_FUNC_SEPARATE:
            glStencilFuncSeparate(static_cast<GLenum>(a), static_cast<GLenum>(b),
                                  static_cast<GLint>(c),
                                  idrive_angle_egl_rpc_u32(payload.data()));
            break;
        case IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_MASK_SEPARATE:
            glStencilMaskSeparate(static_cast<GLenum>(a), b);
            break;
        case IDRIVE_ANGLE_EGL_RPC_GL_STENCIL_OP_SEPARATE:
            glStencilOpSeparate(static_cast<GLenum>(a), static_cast<GLenum>(b),
                                static_cast<GLenum>(c),
                                idrive_angle_egl_rpc_u32(payload.data()));
            break;
        case IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_STENCIL:
            glClearStencil(static_cast<GLint>(a));
            break;
        case IDRIVE_ANGLE_EGL_RPC_GL_BLEND_EQUATION_SEPARATE:
            glBlendEquationSeparate(static_cast<GLenum>(a), static_cast<GLenum>(b));
            break;
        }
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_BLEND_COLOR: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (a || b || c || payload.size() != 16u) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        GLfloat color[4];
        for (unsigned int i = 0; i < 4; ++i) {
            const std::uint32_t bits = idrive_angle_egl_rpc_u32(
                payload.data() + i * 4u);
            std::memcpy(&color[i], &bits, sizeof(bits));
        }
        glBlendColor(color[0], color[1], color[2], color[3]);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_ACTIVE_TEXTURE: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glActiveTexture(static_cast<GLenum>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ARRAYS: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty() || b > 0x7fffffffu || c > 0x7fffffffu) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glDrawArrays(static_cast<GLenum>(a), static_cast<GLint>(b),
            static_cast<GLsizei>(c));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_DRAW_ELEMENTS: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b > 0x7fffffffu || payload.size() < 8) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        unsigned int index_size = 0;
        if (c == GL_UNSIGNED_BYTE) index_size = 1;
        else if (c == GL_UNSIGNED_SHORT) index_size = 2;
        else if (c == GL_UNSIGNED_INT) index_size = 4;
        else {
            set_error(response, kGlInvalidEnum);
            return false;
        }
        const unsigned int pointer_offset = idrive_angle_egl_rpc_u32(payload.data());
        const unsigned int client_bytes = idrive_angle_egl_rpc_u32(payload.data() + 4);
        const std::uint64_t expected_bytes = static_cast<std::uint64_t>(b) * index_size;
        if (client_bytes > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD - 8u ||
            payload.size() != 8u + client_bytes ||
            (client_bytes && (client_bytes != expected_bytes || pointer_offset))) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const void *indices = client_bytes
            ? static_cast<const void *>(payload.data() + 8)
            : reinterpret_cast<const void *>(static_cast<std::uintptr_t>(pointer_offset));
        glDrawElements(static_cast<GLenum>(a), static_cast<GLsizei>(b),
            static_cast<GLenum>(c), indices);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        capture_draw_snapshot(static_cast<GLenum>(a), static_cast<GLsizei>(b),
                              static_cast<GLenum>(c));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_BIND_BUFFER:
    case IDRIVE_ANGLE_EGL_RPC_GL_BIND_TEXTURE: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty() || c != 0) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        if (opcode == IDRIVE_ANGLE_EGL_RPC_GL_BIND_BUFFER)
            glBindBuffer(static_cast<GLenum>(a), static_cast<GLuint>(b));
        else
            glBindTexture(static_cast<GLenum>(a), static_cast<GLuint>(b));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_SHADER_BINARY_CAPTURE: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (a == 0 || a > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / 4u || c == 0) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const std::size_t ids_size = static_cast<std::size_t>(a) * 4u;
        if (
            ids_size > payload.size() || c > payload.size() - ids_size ||
            payload.size() != ids_size + static_cast<std::size_t>(c)) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const unsigned char *binary = payload.data() + ids_size;
        const unsigned int capture_index = ++g_shader_capture_index;
        std::string path = "none";
        if (!g_shader_capture_dir.empty()) {
            char filename[160];
            std::snprintf(filename, sizeof(filename),
                          "shader-%06u-client-%u-format-%08x-length-%u.bin",
                          capture_index, client_id, b, c);
            path = g_shader_capture_dir + "/" + filename;
            FILE *capture = std::fopen(path.c_str(), "wb");
            if (!capture) {
                set_error(response, kGlInvalidOperation);
                std::fprintf(stderr,
                             "ANGLE_SHADER_BINARY_CAPTURE_FAIL client=%u format=0x%08x length=%u errno=%d\n",
                             client_id, b, c, errno);
                return false;
            }
            const std::size_t written = std::fwrite(binary, 1, c, capture);
            const int close_result = std::fclose(capture);
            if (written != c || close_result != 0) {
                set_error(response, kGlInvalidOperation);
                std::fprintf(stderr,
                             "ANGLE_SHADER_BINARY_CAPTURE_FAIL client=%u format=0x%08x length=%u stage=write\n",
                             client_id, b, c);
                return false;
            }
        }

        const ShaderTranslation *translation = find_shader_translation(binary, c);
        std::fprintf(stderr,
                     "ANGLE_SHADER_BINARY_CAPTURE index=%u client=%u count=%u shaders=",
                     capture_index, client_id, a);
        for (unsigned int i = 0; i < a; ++i) {
            if (i) std::fputc(',', stderr);
            std::fprintf(stderr, "%u", idrive_angle_egl_rpc_u32(payload.data() + i * 4u));
        }
        if (translation != nullptr) {
            for (unsigned int i = 0; i < a; ++i) {
                const GLuint shader = idrive_angle_egl_rpc_u32(payload.data() + i * 4u);
                g_shader_uniform_aliases.erase(shader);
                const GLchar *source = translation->source.c_str();
                const GLint source_length = static_cast<GLint>(translation->source.size());
                glShaderSource(shader, 1, &source, &source_length);
                GLenum error = glGetError();
                if (error != GL_NO_ERROR) {
                    set_error(response, static_cast<EGLint>(error));
                    std::fprintf(stderr,
                                 "ANGLE_SHADER_BINARY_TRANSLATION_FAIL client=%u shader=%u source=%s error=0x%04x\n",
                                 client_id, shader, translation->source_path.c_str(), error);
                    return false;
                }
                glCompileShader(shader);
                error = glGetError();
                if (error != GL_NO_ERROR) {
                    set_error(response, static_cast<EGLint>(error));
                    std::fprintf(stderr,
                                 "ANGLE_SHADER_BINARY_COMPILE_FAIL client=%u shader=%u source=%s error=0x%04x\n",
                                 client_id, shader, translation->source_path.c_str(), error);
                    return false;
                }
                GLint compile_status = GL_FALSE;
                glGetShaderiv(shader, GL_COMPILE_STATUS, &compile_status);
                error = glGetError();
                if (error != GL_NO_ERROR || compile_status != GL_TRUE) {
                    set_error(response, error != GL_NO_ERROR
                        ? static_cast<EGLint>(error) : kGlInvalidOperation);
                    GLchar info_log[4096] = {};
                    GLsizei info_log_length = 0;
                    glGetShaderInfoLog(shader, static_cast<GLsizei>(sizeof(info_log)),
                                       &info_log_length, info_log);
                    std::fprintf(stderr,
                                 "ANGLE_SHADER_BINARY_COMPILE_STATUS_FAIL client=%u shader=%u source=%s status=%d error=0x%04x info=%.*s\n",
                                 client_id, shader, translation->source_path.c_str(),
                                 compile_status, error, static_cast<int>(info_log_length),
                                 info_log);
                    return false;
                }
                if (!translation->uniform_aliases.empty()) {
                    g_shader_uniform_aliases[shader] = translation->uniform_aliases;
                    for (const auto &alias : translation->uniform_aliases) {
                        std::fprintf(stderr,
                                     "ANGLE_SHADER_UNIFORM_ALIAS shader=%u native=%s host=%s source=%s\n",
                                     shader, alias.native_name.c_str(),
                                     alias.host_name.c_str(),
                                     translation->source_path.c_str());
                    }
                }
            }
            std::fprintf(stderr,
                         " format=0x%08x length=%u fnv1a64=%016llx path=%s outcome=SOURCE_MAPPED source=%s\n",
                         b, c,
                         static_cast<unsigned long long>(frame_hash(
                             std::vector<unsigned char>(binary, binary + c))),
                         path.c_str(), translation->source_path.c_str());
            return true;
        }

        std::fprintf(stderr,
                     " format=0x%08x length=%u fnv1a64=%016llx path=%s outcome=GL_INVALID_ENUM\n",
                     b, c,
                     static_cast<unsigned long long>(frame_hash(
                         std::vector<unsigned char>(binary, binary + c))),
                     path.c_str());
        set_error(response, kGlInvalidEnum);
        return false;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_SHADER_SOURCE: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (a == 0 || b == 0 || b > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / 4u ||
            c != payload.size()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        std::vector<std::string> sources;
        std::vector<GLint> lengths;
        std::vector<const GLchar *> source_pointers;
        std::vector<unsigned char> joined;
        std::size_t cursor = 0;
        sources.reserve(b);
        lengths.reserve(b);
        for (unsigned int i = 0; i < b; ++i) {
            if (cursor + 4u > payload.size()) {
                set_error(response, kGlInvalidValue);
                return false;
            }
            const unsigned int length = idrive_angle_egl_rpc_u32(payload.data() + cursor);
            cursor += 4u;
            if (length > payload.size() - cursor) {
                set_error(response, kGlInvalidValue);
                return false;
            }
            sources.emplace_back(
                reinterpret_cast<const char *>(payload.data() + cursor), length);
            lengths.push_back(static_cast<GLint>(length));
            joined.insert(joined.end(), payload.begin() + cursor,
                          payload.begin() + cursor + length);
            cursor += length;
        }
        if (cursor != payload.size()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        for (const std::string &source : sources)
            source_pointers.push_back(source.c_str());
        glShaderSource(static_cast<GLuint>(a), static_cast<GLsizei>(b),
                       source_pointers.data(), lengths.data());
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        char filename[160];
        std::string path;
        if (!g_shader_capture_dir.empty()) {
            std::snprintf(filename, sizeof(filename),
                          "source-%06u-client-%u-shader-%u.glsl",
                          ++g_shader_capture_index, client_id, a);
            path = g_shader_capture_dir + "/" + filename;
            FILE *capture = std::fopen(path.c_str(), "wb");
            if (!capture || std::fwrite(joined.data(), 1, joined.size(), capture) != joined.size()) {
                if (capture) std::fclose(capture);
                set_error(response, kGlInvalidOperation);
                std::fprintf(stderr,
                             "ANGLE_SHADER_SOURCE_CAPTURE_FAIL client=%u shader=%u bytes=%zu\n",
                             client_id, a, joined.size());
                return false;
            }
            if (std::fclose(capture) != 0) {
                set_error(response, kGlInvalidOperation);
                return false;
            }
        }
        std::fprintf(stderr,
                     "ANGLE_SHADER_SOURCE client=%u shader=%u count=%u bytes=%zu fnv1a64=%016llx path=%s\n",
                     client_id, a, b, joined.size(),
                     static_cast<unsigned long long>(frame_hash(joined)),
                     path.empty() ? "none" : path.c_str());
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_BUFFER_DATA: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD ||
            (!payload.empty() && payload.size() != b)) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glBufferData(static_cast<GLenum>(a), static_cast<GLsizeiptr>(b),
                     payload.empty() ? nullptr : payload.data(),
                     static_cast<GLenum>(c));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        const GLuint buffer = bound_buffer(static_cast<GLenum>(a));
        if (buffer && !g_resource_capture_dir.empty()) {
            if (payload.empty()) {
                g_buffer_contents.erase(buffer);
            } else {
                std::vector<unsigned char> contents(static_cast<std::size_t>(b));
                std::copy(payload.begin(), payload.end(), contents.begin());
                g_buffer_contents[buffer] = std::move(contents);
            }
            const std::string path = payload.empty() ? std::string{} :
                capture_resource_blob("buffer-upload", buffer,
                                      ++g_resource_capture_index,
                                      payload.data(), payload.size());
            std::fprintf(stderr,
                         "ANGLE_BUFFER_UPLOAD client=%u target=0x%04x buffer=%u size=%u usage=0x%04x data=%u path=%s\n",
                         client_id, a, buffer, b, c, !payload.empty(),
                         path.empty() ? "none" : path.c_str());
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_BUFFER_SUB_DATA: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b > 0x7fffffffu || c > 0x7fffffffu || payload.size() != c) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glBufferSubData(static_cast<GLenum>(a), static_cast<GLintptr>(b),
                        static_cast<GLsizeiptr>(c),
                        payload.empty() ? nullptr : payload.data());
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        const GLuint buffer = bound_buffer(static_cast<GLenum>(a));
        if (buffer && !g_resource_capture_dir.empty()) {
            auto contents = g_buffer_contents.find(buffer);
            if (contents != g_buffer_contents.end() &&
                static_cast<std::size_t>(b) <= contents->second.size() &&
                static_cast<std::size_t>(c) <= contents->second.size() - b) {
                std::copy(payload.begin(), payload.end(),
                          contents->second.begin() + b);
            }
            const std::string path = capture_resource_blob(
                "buffer-subupload", buffer, ++g_resource_capture_index,
                payload.empty() ? nullptr : payload.data(), payload.size());
            std::fprintf(stderr,
                         "ANGLE_BUFFER_SUB_UPLOAD client=%u target=0x%04x buffer=%u offset=%u bytes=%u path=%s\n",
                         client_id, a, buffer, b, c,
                         path.empty() ? "none" : path.c_str());
        }
        std::fprintf(stderr,
                     "ANGLE_BUFFER_SUB_DATA client=%u target=0x%04x offset=%u bytes=%u\n",
                     client_id, a, b, c);
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_TEX_PARAMETERI: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glTexParameteri(static_cast<GLenum>(a), static_cast<GLenum>(b),
                        static_cast<GLint>(c));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_PIXEL_STOREI: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty() || c != 0) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glPixelStorei(static_cast<GLenum>(a), static_cast<GLint>(b));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_TEX_IMAGE_2D: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (payload.size() < 32) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const GLenum target = idrive_angle_egl_rpc_u32(payload.data());
        const GLint level = static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data() + 4));
        const GLint internal_format = static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data() + 8));
        const GLsizei width = static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 12));
        const GLsizei height = static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 16));
        const GLint border = static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data() + 20));
        const GLenum format = idrive_angle_egl_rpc_u32(payload.data() + 24);
        const GLenum type = idrive_angle_egl_rpc_u32(payload.data() + 28);
        const void *pixels = payload.size() > 32 ? payload.data() + 32 : nullptr;
        GLint texture_name = 0;
        if (target == GL_TEXTURE_2D) {
            glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture_name);
        }
        glTexImage2D(target, level, internal_format, width, height, border,
                     format, type, pixels);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        std::string capture_path;
        if (texture_name > 0 && !g_resource_capture_dir.empty()) {
            capture_path = capture_resource_blob(
                "texture-upload", static_cast<GLuint>(texture_name),
                ++g_resource_capture_index, payload.size() > 32
                    ? payload.data() + 32 : nullptr,
                payload.size() - 32);
        }
        std::fprintf(stderr,
                     "ANGLE_TEXTURE_UPLOAD client=%u target=0x%04x texture=%d level=%d size=%dx%d format=0x%04x type=0x%04x bytes=%zu data=%u path=%s\n",
                     client_id, target, texture_name, level, width, height,
                     format, type, payload.size() - 32, pixels != nullptr,
                     capture_path.empty() ? "none" : capture_path.c_str());
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_TEX_SUB_IMAGE_2D: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (payload.size() < 32 ||
            a != idrive_angle_egl_rpc_u32(payload.data()) ||
            b != idrive_angle_egl_rpc_u32(payload.data() + 4) ||
            c != idrive_angle_egl_rpc_u32(payload.data() + 16)) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const GLenum target = idrive_angle_egl_rpc_u32(payload.data());
        const GLint level = static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data() + 4));
        const GLint xoffset = static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data() + 8));
        const GLint yoffset = static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data() + 12));
        const GLsizei width = static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 16));
        const GLsizei height = static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 20));
        const GLenum format = idrive_angle_egl_rpc_u32(payload.data() + 24);
        const GLenum type = idrive_angle_egl_rpc_u32(payload.data() + 28);
        const void *pixels = payload.size() > 32 ? payload.data() + 32 : nullptr;
        GLint texture_name = 0;
        if (target == GL_TEXTURE_2D) {
            glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture_name);
        }
        glTexSubImage2D(target, level, xoffset, yoffset, width, height,
                        format, type, pixels);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        std::string capture_path;
        if (texture_name > 0 && !g_resource_capture_dir.empty()) {
            capture_path = capture_resource_blob(
                "texture-subupload", static_cast<GLuint>(texture_name),
                ++g_resource_capture_index, payload.size() > 32
                    ? payload.data() + 32 : nullptr,
                payload.size() - 32);
        }
        std::fprintf(stderr,
                     "ANGLE_TEXTURE_SUB_UPLOAD client=%u target=0x%04x texture=%d level=%d offset=%d,%d size=%dx%d format=0x%04x type=0x%04x bytes=%zu data=%u path=%s\n",
                     client_id, target, texture_name, level, xoffset, yoffset,
                     width, height, format, type, payload.size() - 32,
                     pixels != nullptr,
                     capture_path.empty() ? "none" : capture_path.c_str());
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_COMPILE_SHADER: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!a || b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glCompileShader(static_cast<GLuint>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GET_SHADER_IV: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!a || !b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        GLint value = 0;
        glGetShaderiv(static_cast<GLuint>(a), static_cast<GLenum>(b), &value);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        set_value(response, 0, static_cast<unsigned int>(value));
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_GENERATE_MIPMAP: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!a || b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glGenerateMipmap(static_cast<GLenum>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_VIEWPORT: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (payload.size() != 16) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glViewport(static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data())),
                   static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data() + 4)),
                   static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 8)),
                   static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 12)));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_CLEAR_COLOR: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (payload.size() != 16) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        float color[4] = {};
        for (unsigned int i = 0; i < 4; ++i) {
            const unsigned int bits = idrive_angle_egl_rpc_u32(payload.data() + i * 4u);
            std::memcpy(&color[i], &bits, sizeof(bits));
        }
        glClearColor(color[0], color[1], color[2], color[3]);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_CLEAR: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glClear(static_cast<GLbitfield>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_SCISSOR: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (payload.size() != 16) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glScissor(static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data())),
                  static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data() + 4)),
                  static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 8)),
                  static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 12)));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_ENABLE:
    case IDRIVE_ANGLE_EGL_RPC_GL_DISABLE: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (!payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        if (opcode == IDRIVE_ANGLE_EGL_RPC_GL_ENABLE) glEnable(a);
        else glDisable(a);
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_FUNC: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glDepthFunc(static_cast<GLenum>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_DEPTH_MASK: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (a > 1 || b || c || !payload.empty()) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        glDepthMask(static_cast<GLboolean>(a));
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_GL_READ_PIXELS: {
        if (eglGetCurrentContext() == EGL_NO_CONTEXT) {
            set_error(response, kGlInvalidOperation);
            return false;
        }
        if (payload.size() != 24) {
            set_error(response, kGlInvalidValue);
            return false;
        }
        const GLint x = static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data()));
        const GLint y = static_cast<GLint>(idrive_angle_egl_rpc_u32(payload.data() + 4));
        const GLsizei width = static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 8));
        const GLsizei height = static_cast<GLsizei>(idrive_angle_egl_rpc_u32(payload.data() + 12));
        const GLenum format = idrive_angle_egl_rpc_u32(payload.data() + 16);
        const GLenum type = idrive_angle_egl_rpc_u32(payload.data() + 20);
        if (width <= 0 || height <= 0 || format != GL_RGBA || type != GL_UNSIGNED_BYTE ||
            static_cast<std::size_t>(width) > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD / 4u /
                static_cast<std::size_t>(height)) {
            set_error(response, (format != GL_RGBA || type != GL_UNSIGNED_BYTE)
                ? kGlInvalidEnum : kGlInvalidValue);
            return false;
        }
        const std::size_t bytes = static_cast<std::size_t>(width) *
            static_cast<std::size_t>(height) * 4u;
        response_payload.resize(bytes);
        glReadPixels(x, y, width, height, format, type, response_payload.data());
        const GLenum error = glGetError();
        if (error != GL_NO_ERROR) {
            response_payload.clear();
            set_error(response, static_cast<EGLint>(error));
            return false;
        }
        return true;
    }

    case IDRIVE_ANGLE_EGL_RPC_QUERY_CONTEXT: {
        const auto context = client.contexts.find(a);
        if (context == client.contexts.end()) {
            set_error(response, EGL_BAD_CONTEXT);
            return false;
        }
        EGLint value = 0;
        if (eglQueryContext(g_display, context->second,
                            static_cast<EGLint>(b), &value) != EGL_TRUE) {
            set_error(response, eglGetError());
            return false;
        }
        set_value(response, 0, static_cast<unsigned int>(value));
        return true;
    }

    default:
        set_error(response, EGL_BAD_PARAMETER);
        return false;
    }
}

bool valid_request(const unsigned char *request)
{
    return std::memcmp(request, "I6ER", 4) == 0 &&
        idrive_angle_egl_rpc_u16(request + 4) == IDRIVE_ANGLE_EGL_RPC_VERSION &&
        idrive_angle_egl_rpc_u32(request + 24) != 0 &&
        idrive_angle_egl_rpc_u32(request + 28) <= IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD;
}

bool process_batch(const unsigned char *request,
                   const std::vector<unsigned char> &payload,
                   unsigned char *response)
{
    constexpr std::size_t header = IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES;
    const unsigned int client = idrive_angle_egl_rpc_u32(request + 8);
    if (payload.empty() || payload.size() > IDRIVE_ANGLE_EGL_BATCH_BYTES ||
        idrive_angle_egl_rpc_u32(request + 12) ||
        idrive_angle_egl_rpc_u32(request + 16) ||
        idrive_angle_egl_rpc_u32(request + 20)) {
        set_error(response, EGL_BAD_PARAMETER);
        return false;
    }
    // Validate the entire envelope before executing any commands.
    for (std::size_t offset = 0; offset < payload.size();) {
        const unsigned char *command = payload.data() + offset;
        if (payload.size() - offset < header || !valid_request(command) ||
            idrive_angle_egl_rpc_u32(command + 8) != client ||
            !idrive_angle_egl_rpc_batchable(idrive_angle_egl_rpc_u16(command + 6))) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        const unsigned int length = idrive_angle_egl_rpc_u32(command + 28);
        if (length > payload.size() - offset - header) {
            set_error(response, EGL_BAD_PARAMETER);
            return false;
        }
        offset += header + length;
    }
    unsigned int first_error = GL_NO_ERROR;
    std::vector<unsigned char> command_payload;
    std::vector<unsigned char> unused_response_payload;
    for (std::size_t offset = 0; offset < payload.size();) {
        const unsigned char *command = payload.data() + offset;
        const unsigned char *start = command + header;
        const unsigned int length = idrive_angle_egl_rpc_u32(command + 28);
        command_payload.assign(start, start + length);
        unsigned char command_response[IDRIVE_ANGLE_EGL_RPC_RESPONSE_BYTES] = {};
        unused_response_payload.clear();
        if (!process_request(command, command_payload, command_response,
                             unused_response_payload)) {
            unsigned int error = idrive_angle_egl_rpc_u32(command_response + 8);
            if (!error) error = kGlInvalidOperation;
            if (!first_error) first_error = error;
            std::fprintf(stderr,
                         "ANGLE_EGL_BATCH_GL_ERROR client=%u op=%u request=%u error=0x%04x\n",
                         client, idrive_angle_egl_rpc_u16(command + 6),
                         idrive_angle_egl_rpc_u32(command + 24), error);
        }
        offset += header + length;
    }
    set_value(response, 0, first_error);
    return true;
}

void dispatch_request(const unsigned char *request,
                      const std::vector<unsigned char> &payload, bool frame_valid,
                      unsigned char *response, std::vector<unsigned char> &response_payload,
                      std::chrono::steady_clock::time_point started, bool trace = true,
                      bool batch_allowed = false)
{
    const unsigned int opcode = idrive_angle_egl_rpc_u16(request + 6);
    const unsigned int request_id = idrive_angle_egl_rpc_u32(request + 24);
    const unsigned int payload_size = idrive_angle_egl_rpc_u32(request + 28);
    std::memcpy(response, "I6EA", 4);
    idrive_angle_egl_rpc_put_u16(response + 4, IDRIVE_ANGLE_EGL_RPC_VERSION);
    if (!frame_valid) set_error(response, EGL_BAD_PARAMETER);
    const unsigned int client_id = idrive_angle_egl_rpc_u32(request + 8);
    const bool ok = frame_valid &&
        (opcode == IDRIVE_ANGLE_EGL_RPC_GL_BATCH && batch_allowed
            ? process_batch(request, payload, response)
            : process_request(request, payload, response, response_payload));
    if (response_payload.size() > IDRIVE_ANGLE_EGL_RPC_MAX_PAYLOAD) {
        response_payload.clear();
        set_error(response, EGL_BAD_ALLOC);
    }
    if (frame_valid && !ok && !idrive_angle_egl_rpc_u16(response + 6)) {
        set_error(response, EGL_BAD_ALLOC);
    }
    idrive_angle_egl_rpc_put_u32(response + 24,
                                 static_cast<unsigned int>(response_payload.size()));
    idrive_angle_egl_rpc_put_u32(response + 28, request_id);
    if (!trace && ok && opcode != IDRIVE_ANGLE_EGL_RPC_SWAP_WINDOW_SURFACE) return;
    const auto elapsed_us = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - started).count();
    const std::uint64_t request_hash = frame_hash(payload);
    std::fprintf(stderr,
                 "ANGLE_EGL_RPC op=%u op_name=%s client=%u status=%s error=0x%04x a=%u b=%u c=%u value0=%u request_payload=%u request_fnv1a64=%016llx response_payload=%zu service_us=%lld\n",
                 opcode, opcode_name(opcode), client_id, ok ? "ok" : "fail",
                 idrive_angle_egl_rpc_u32(response + 8),
                 idrive_angle_egl_rpc_u32(request + 12),
                 idrive_angle_egl_rpc_u32(request + 16),
                 idrive_angle_egl_rpc_u32(request + 20),
                 idrive_angle_egl_rpc_u32(response + 12), payload_size,
                 static_cast<unsigned long long>(request_hash),
                 response_payload.size(), static_cast<long long>(elapsed_us));
}

bool serve_client(int client_fd)
{
    while (!g_stop) {
        std::chrono::steady_clock::time_point started;
        unsigned char request[IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES] = {};
        const ssize_t first = recv(client_fd, request, 1, 0);
        if (first == 0) return true;
        if (first < 0) {
            if (errno == EINTR) continue;
            std::fprintf(stderr, "ANGLE_EGL_RPC_FAIL stage=read-header errno=%d\n", errno);
            return false;
        }
        started = std::chrono::steady_clock::now();
        if (!read_all(client_fd, request + 1, sizeof(request) - 1)) {
            std::fprintf(stderr, "ANGLE_EGL_RPC_FAIL stage=read-header\n");
            return false;
        }
        const bool frame_valid = valid_request(request);
        const unsigned int payload_size = idrive_angle_egl_rpc_u32(request + 28);
        std::vector<unsigned char> payload;
        if (frame_valid && payload_size) {
            payload.resize(payload_size);
            if (!read_all(client_fd, payload.data(), payload.size())) {
                std::fprintf(stderr, "ANGLE_EGL_RPC_FAIL stage=read-payload bytes=%u\n", payload_size);
                return false;
            }
        }
        unsigned char response[IDRIVE_ANGLE_EGL_RPC_RESPONSE_BYTES] = {};
        std::vector<unsigned char> response_payload;
        dispatch_request(request, payload, frame_valid, response, response_payload, started);
        if (!write_all(client_fd, response, sizeof(response)) ||
            (!response_payload.empty() &&
             !write_all(client_fd, response_payload.data(), response_payload.size()))) {
            std::fprintf(stderr, "ANGLE_EGL_RPC_FAIL stage=write-response errno=%d\n", errno);
            return false;
        }
        if (!frame_valid ||
            idrive_angle_egl_rpc_u16(request + 6) == IDRIVE_ANGLE_EGL_RPC_TERMINATE)
            return true;
    }
    return true;
}

int open_controller_socket(const std::string &path)
{
    sockaddr_un address{};
    if (path.size() >= sizeof(address.sun_path)) return -1;
    address.sun_family = AF_UNIX;
    std::memcpy(address.sun_path, path.c_str(), path.size() + 1);
    const int fd = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (fd < 0) return -1;
    if (bind(fd, reinterpret_cast<sockaddr *>(&address), sizeof(address)) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

void poll_controller(int fd, idrive_hmi_controller_ring &ring)
{
    if (fd < 0) return;
    unsigned char message[2];
    const ssize_t size = recv(fd, message, sizeof(message), MSG_DONTWAIT);
    if (size != 1 || !__atomic_load_n(&ring.ready, __ATOMIC_ACQUIRE)) return;
    const unsigned int key = message[0];
    if (!idrive_hmi_controller_valid(key, 0)) return;
    const bool rotary = idrive_hmi_controller_is_rotary(key);
    const unsigned int count = rotary ? 1 : 2;
    const unsigned int read = __atomic_load_n(&ring.read_index, __ATOMIC_ACQUIRE);
    const unsigned int write = __atomic_load_n(&ring.write_index, __ATOMIC_RELAXED);
    if (write - read > IDRIVE_HMI_CONTROLLER_SLOTS - count) {
        std::fprintf(stderr, "ANGLE_HMI_CONTROLLER_FULL key=%u\n", key);
        return;
    }
    ring.events[write % IDRIVE_HMI_CONTROLLER_SLOTS] = rotary ? key : key | 0x100;
    if (!rotary) ring.events[(write + 1) % IDRIVE_HMI_CONTROLLER_SLOTS] = key;
    __atomic_store_n(&ring.write_index, write + count, __ATOMIC_RELEASE);
    std::fprintf(stderr, "ANGLE_HMI_CONTROLLER_QUEUED key=%u events=%u\n", key, count);
}

bool serve_mailbox(const std::string &path, const std::string &controller_path)
{
    static_assert(offsetof(idrive_angle_mailbox, frame) == IDRIVE_ANGLE_MAILBOX_FRAME_OFFSET);
    static_assert(sizeof(idrive_angle_mailbox) <= IDRIVE_HMI_CONTROLLER_OFFSET);
    static_assert(IDRIVE_HMI_CONTROLLER_OFFSET + sizeof(idrive_hmi_controller_ring)
                  <= IDRIVE_ANGLE_MAILBOX_BYTES);
    static_assert(IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES == IDRIVE_ANGLE_EGL_RPC_RESPONSE_BYTES);
    const int fd = open(path.c_str(), O_RDWR);
    struct stat info{};
    if (fd < 0 || fstat(fd, &info) != 0 || info.st_size != IDRIVE_ANGLE_MAILBOX_BYTES) {
        std::fprintf(stderr, "ANGLE_EGL_MAILBOX_FAIL stage=open path=%s\n", path.c_str());
        if (fd >= 0) close(fd);
        return false;
    }
    void *mapping = mmap(nullptr, IDRIVE_ANGLE_MAILBOX_BYTES, PROT_READ | PROT_WRITE,
                         MAP_SHARED, fd, 0);
    close(fd);
    if (mapping == MAP_FAILED) {
        std::fprintf(stderr, "ANGLE_EGL_MAILBOX_FAIL stage=mmap errno=%d\n", errno);
        return false;
    }
    auto *mailbox = static_cast<idrive_angle_mailbox *>(mapping);
    if (__atomic_load_n(&mailbox->magic, __ATOMIC_ACQUIRE) != 0 ||
        __atomic_load_n(&mailbox->state, __ATOMIC_RELAXED) != IDRIVE_ANGLE_MAILBOX_IDLE) {
        std::fprintf(stderr, "ANGLE_EGL_MAILBOX_FAIL stage=already-initialized\n");
        munmap(mapping, IDRIVE_ANGLE_MAILBOX_BYTES);
        return false;
    }
    int controller_fd = -1;
    if (!controller_path.empty()) {
        controller_fd = open_controller_socket(controller_path);
        if (controller_fd < 0) {
            std::fprintf(stderr, "ANGLE_HMI_CONTROLLER_FAIL stage=bind path=%s\n",
                         controller_path.c_str());
            munmap(mapping, IDRIVE_ANGLE_MAILBOX_BYTES);
            return false;
        }
    }
    auto &controller = *reinterpret_cast<idrive_hmi_controller_ring *>(
        static_cast<unsigned char *>(mapping) + IDRIVE_HMI_CONTROLLER_OFFSET);
    const char *batch_env = std::getenv("IDRIVE_ANGLE_EGL_BATCH");
    const bool batch_allowed = batch_env && std::strcmp(batch_env, "1") == 0;
    unsigned int features = batch_allowed
        ? IDRIVE_ANGLE_MAILBOX_BATCH | IDRIVE_ANGLE_MAILBOX_BATCH_BIND : 0;
    const char *post_env = std::getenv("IDRIVE_ANGLE_EGL_IMMEDIATE_POST");
    if (post_env && std::strcmp(post_env, "1") == 0)
        features |= IDRIVE_ANGLE_MAILBOX_IMMEDIATE_POST;
    const char *fast_wait_env = std::getenv("IDRIVE_ANGLE_EGL_FAST_WAIT");
    if (fast_wait_env && std::strcmp(fast_wait_env, "1") == 0)
        features |= IDRIVE_ANGLE_MAILBOX_FAST_WAIT;
    __atomic_store_n(&mailbox->features, features, __ATOMIC_RELAXED);
    __atomic_store_n(&mailbox->magic, IDRIVE_ANGLE_MAILBOX_MAGIC, __ATOMIC_RELEASE);
    std::fprintf(stderr, "ANGLE_EGL_MAILBOX_READY physical=0x%x bytes=%u\n",
                 IDRIVE_ANGLE_MAILBOX_PHYS, IDRIVE_ANGLE_MAILBOX_BYTES);

    using Clock = std::chrono::steady_clock;
    const char *trace_env = std::getenv("IDRIVE_ANGLE_EGL_TRACE");
    const bool trace = !trace_env || std::strcmp(trace_env, "0") != 0;
    auto last_response = Clock::time_point{};
    auto next_controller_poll = Clock::time_point{};
    unsigned int screen_posts = 0;
    std::vector<unsigned char> payload;
    std::vector<unsigned char> response_payload;
    while (!g_stop) {
        const auto started = Clock::now();
        if (started >= next_controller_poll) {
            poll_controller(controller_fd, controller);
            const unsigned int posted =
                __atomic_load_n(&mailbox->screen_posts, __ATOMIC_ACQUIRE);
            if (posted != screen_posts) {
                screen_posts = posted;
                std::fprintf(stderr, "ANGLE_SCREEN_POSTED count=%u host_us=%lld buffer_cycles=%u rpc_cycles=%u post_cycles=%u\n",
                             posted, static_cast<long long>(
                                 std::chrono::duration_cast<std::chrono::microseconds>(
                                     started.time_since_epoch()).count()),
                             mailbox->screen_buffer_cycles, mailbox->screen_rpc_cycles,
                             mailbox->screen_post_cycles);
            }
            next_controller_poll = started + std::chrono::microseconds(100);
        }
        unsigned int expected = __atomic_load_n(&mailbox->state, __ATOMIC_RELAXED);
        if (expected != IDRIVE_ANGLE_MAILBOX_REQUEST ||
            !__atomic_compare_exchange_n(&mailbox->state, &expected,
                                         IDRIVE_ANGLE_MAILBOX_PROCESSING, false,
                                         __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) {
            if (expected == IDRIVE_ANGLE_MAILBOX_FAILED) break;
            // Poll promptly during bursts without occupying a core while idle.
            if (started - last_response > std::chrono::milliseconds(2))
                (void)usleep(100);
            continue;
        }
        unsigned char request[IDRIVE_ANGLE_EGL_RPC_REQUEST_BYTES];
        std::memcpy(request, mailbox->frame, sizeof(request));
        if (!valid_request(request)) {
            std::fprintf(stderr, "ANGLE_EGL_MAILBOX_FAIL stage=request-header\n");
            break;
        }
        const unsigned int payload_size = idrive_angle_egl_rpc_u32(request + 28);
        const unsigned char *source = mailbox->frame + sizeof(request);
        payload.assign(source, source + payload_size);
        unsigned char response[IDRIVE_ANGLE_EGL_RPC_RESPONSE_BYTES] = {};
        response_payload.clear();
        dispatch_request(request, payload, true, response, response_payload, started,
                         trace, batch_allowed);
        std::memcpy(mailbox->frame, response, sizeof(response));
        if (!response_payload.empty())
            std::memcpy(mailbox->frame + sizeof(response),
                        response_payload.data(), response_payload.size());
        last_response = Clock::now();
        expected = IDRIVE_ANGLE_MAILBOX_PROCESSING;
        if (!__atomic_compare_exchange_n(&mailbox->state, &expected,
                                         IDRIVE_ANGLE_MAILBOX_RESPONSE, false,
                                         __ATOMIC_RELEASE, __ATOMIC_RELAXED))
            break;
    }
    __atomic_store_n(&mailbox->state, IDRIVE_ANGLE_MAILBOX_FAILED, __ATOMIC_RELEASE);
    if (controller_fd >= 0) {
        close(controller_fd);
        unlink(controller_path.c_str());
    }
    munmap(mapping, IDRIVE_ANGLE_MAILBOX_BYTES);
    return g_stop;
}

void log_run_id()
{
    const char *run_id = std::getenv("IDRIVE_HMI_RUN_ID");
    if (run_id && *run_id) {
        bool safe_run_id = true;
        for (const unsigned char ch : std::string(run_id)) {
            if (!((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') ||
                  (ch >= '0' && ch <= '9') || ch == '_' || ch == '.' || ch == '-')) {
                safe_run_id = false;
                break;
            }
        }
        if (safe_run_id) {
            std::fprintf(stderr, "ANGLE_EGL_RPC_RUN_ID id=%s\n", run_id);
        } else {
            std::fprintf(stderr, "ANGLE_EGL_RPC_RUN_ID invalid=1\n");
        }
    }
}

int serve_tcp(unsigned int port)
{
    g_listener = socket(AF_INET, SOCK_STREAM, 0);
    if (g_listener < 0) {
        std::fprintf(stderr, "ANGLE_EGL_RPC_FAIL stage=socket errno=%d\n", errno);
        return 1;
    }
    int reuse = 1;
    (void)setsockopt(g_listener, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(static_cast<unsigned short>(port));
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(g_listener, reinterpret_cast<sockaddr *>(&address), sizeof(address)) != 0 ||
        listen(g_listener, 8) != 0) {
        std::fprintf(stderr, "ANGLE_EGL_RPC_FAIL stage=bind-listen address=127.0.0.1 port=%u errno=%d\n",
                     port, errno);
        close(g_listener);
        return 1;
    }
    std::fprintf(stderr, "ANGLE_EGL_RPC_LISTEN address=127.0.0.1 port=%u backend=%s egl=%d.%d depth=24 guest_ram=%s guest_ram_bytes=%llu\n",
                 port,
#if defined(IDRIVE_USE_MESA)
                 "mesa-surfaceless",
#elif defined(__APPLE__)
                 "metal",
#else
                 "vulkan",
#endif
                 g_major, g_minor,
                 g_guest_ram_path.empty() ? "none" : g_guest_ram_path.c_str(),
                 static_cast<unsigned long long>(g_guest_ram_size));
    while (!g_stop) {
        const int client = accept(g_listener, nullptr, nullptr);
        if (client < 0) {
            if (g_stop) break;
            if (errno == EINTR) continue;
            std::fprintf(stderr, "ANGLE_EGL_RPC_FAIL stage=accept errno=%d\n", errno);
            break;
        }
        (void)serve_client(client);
        close(client);
    }
    return 0;
}

void on_signal(int)
{
    g_stop = 1;
    if (g_listener >= 0) close(g_listener);
}

} // namespace

int main(int argc, char **argv)
{
    unsigned int port = IDRIVE_ANGLE_EGL_RPC_PORT;
    std::string mailbox_path;
    std::string controller_path;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            char *end = nullptr;
            const unsigned long parsed = std::strtoul(argv[++i], &end, 10);
            if (!end || *end || parsed < 1024 || parsed > 65535) {
                std::fprintf(stderr, "Usage: %s [--port 1024..65535]\n", argv[0]);
                return 2;
            }
            port = static_cast<unsigned int>(parsed);
        } else if (std::strcmp(argv[i], "--mailbox-file") == 0 && i + 1 < argc) {
            mailbox_path = argv[++i];
        } else if (std::strcmp(argv[i], "--controller-socket") == 0 && i + 1 < argc) {
            controller_path = argv[++i];
        } else if (std::strcmp(argv[i], "--guest-ram-file") == 0 && i + 1 < argc) {
            g_guest_ram_path = argv[++i];
        } else if (std::strcmp(argv[i], "--shader-capture-dir") == 0 && i + 1 < argc) {
            g_shader_capture_dir = argv[++i];
        } else if (std::strcmp(argv[i], "--draw-capture-dir") == 0 && i + 1 < argc) {
            g_draw_capture_dir = argv[++i];
        } else if (std::strcmp(argv[i], "--resource-capture-dir") == 0 && i + 1 < argc) {
            g_resource_capture_dir = argv[++i];
        } else if (std::strcmp(argv[i], "--draw-capture-limit") == 0 && i + 1 < argc) {
            char *end = nullptr;
            const unsigned long parsed = std::strtoul(argv[++i], &end, 10);
            if (!end || *end || parsed > 10000) {
                std::fprintf(stderr,
                             "Usage: %s [--draw-capture-limit 0..10000]\n",
                             argv[0]);
                return 2;
            }
            g_draw_capture_limit = static_cast<unsigned int>(parsed);
        } else if (std::strcmp(argv[i], "--shader-map") == 0 && i + 2 < argc) {
            const char *native_path = argv[++i];
            const char *source_path = argv[++i];
            if (!load_shader_translation(native_path, source_path)) return 2;
        } else {
            std::fprintf(stderr,
                             "Usage: %s [--port 1024..65535] [--mailbox-file PATH [--controller-socket PATH]] [--guest-ram-file PATH] [--shader-capture-dir PATH] [--draw-capture-dir PATH] [--resource-capture-dir PATH] [--draw-capture-limit 0..10000] [--shader-map NATIVE_SHD SOURCE_GLSL]...\n",
                         argv[0]);
            return 2;
        }
    }
    if (!controller_path.empty() && mailbox_path.empty()) {
        std::fprintf(stderr, "--controller-socket requires --mailbox-file\n");
        return 2;
    }
    if (!g_draw_capture_dir.empty() && g_draw_capture_limit == 0) {
        g_draw_capture_limit = 64;
    }
    if (!g_guest_ram_path.empty()) {
        struct stat info{};
        g_guest_ram_fd = open(g_guest_ram_path.c_str(), O_RDWR);
        if (g_guest_ram_fd < 0 || fstat(g_guest_ram_fd, &info) != 0 ||
            info.st_size <= 0) {
            std::fprintf(stderr,
                         "ANGLE_EGL_RPC_GUEST_RAM_FAIL path=%s errno=%d\n",
                         g_guest_ram_path.c_str(), errno);
            if (g_guest_ram_fd >= 0) close(g_guest_ram_fd);
            return 1;
        }
        g_guest_ram_size = static_cast<std::uint64_t>(info.st_size);
    }
    if (!ensure_display()) return 1;
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);

    log_run_id();
    const int status = mailbox_path.empty()
        ? serve_tcp(port) : (serve_mailbox(mailbox_path, controller_path) ? 0 : 1);
    if (eglGetCurrentContext() != EGL_NO_CONTEXT) {
        (void)eglMakeCurrent(g_display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    }
    for (auto &entry : g_clients) destroy_client_objects(entry.first, entry.second);
    if (g_display_initialized) (void)eglTerminate(g_display);
    if (g_listener >= 0) close(g_listener);
    if (g_guest_ram_fd >= 0) close(g_guest_ram_fd);
    std::fprintf(stderr, "ANGLE_EGL_RPC_STOP\n");
    return status;
}
