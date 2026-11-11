#version 300 es
// Original host reconstruction, reusing IconRGBA_fragment.glsl's finalized SOP2.
// Exact .shd SHA256: 95504122ff43b1115c468962076a83ac2c2beeef7346733e7b6e1bf67fc0ce66
// Reference .shd SHA256: befb1737d8e7110cea4f797343c2eaca51c2d9d95249f45774c34d0982fc9819
// Both PSU programs, constants and symbols [68:EOF] are byte-identical.
// Differences are restricted to container hash and stage metadata bytes
// 4..7, 59..61, 65..67. Native texture lane/quantization remain unverified,
// as in the reference. Host texture must provide normalized RGBA semantics
// (GL_LUMINANCE_ALPHA expands to L,L,L,A), not a red-only glyph adapter.
precision highp float;

uniform sampler2D tex0;
uniform vec4 u_color;
in vec2 vTexCoord;
layout(location = 0) out vec4 bmwFragmentColor;

void main()
{
    vec4 tint = clamp(u_color, 0.0, 1.0);
    vec4 color = tint * texture(tex0, vTexCoord);
    bmwFragmentColor = round(clamp(color, 0.0, 1.0) * 255.0) / 255.0;
}
