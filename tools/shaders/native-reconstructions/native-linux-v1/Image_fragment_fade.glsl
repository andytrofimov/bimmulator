#version 300 es
// Original reconstruction from exact native-finalized X20511I instructions.
// ImageRGBA_fragment_fade and ImageLuminanceAlpha_fragment_fade are identical:
// .shd SHA256 ea1e898c16fc7127d5c9faa31f336cddeac368ae4309c6c6a6d897f4073776f6
// Primary SHA256 65eb3ada79873e0d2cc5075cfa5e491051a4d8d32431c968e10fd6ef85ed72e6
// table44 SHA256 1061ebfe8f22c752e8f631b33f20f640300e3176b2c8aebb3d4a912f30162393
// table54 SHA256 32401ffb6b6915745132c802601803584112b2637a89cd93b55fbf3bc4deb7ce
// Seven primary ops: placeholder, F32 MAX/MIN, F32 MUL of clamped fade,
// F16 MUL sampled RGBA * tint, F16 MUL of ALPHA ONLY by fade, U8 VPCK.
// table44 binds sample0 to PA1, fade to PA0.xy; table54 packs u_color
// into SA10/11 as F16 pairs. Preserve those F16 storage boundaries explicitly.
// Normalized host RGBA sample/packed output lane mapping remains inherited
// reference uncertainty; native GL_LUMINANCE_ALPHA expands to L,L,L,A.
precision highp float;
uniform sampler2D tex0;
uniform vec4 u_color;
in vec2 vTexCoord;
in vec2 vFading;
layout(location = 0) out vec4 bmwFragmentColor;

vec4 half4(vec4 value)
{
    return vec4(unpackHalf2x16(packHalf2x16(value.xy)),
                unpackHalf2x16(packHalf2x16(value.zw)));
}

void main()
{
    vec2 fade = clamp(vFading, 0.0, 1.0);
    float coverage = fade.x * fade.y;
    vec4 color = half4(half4(u_color) * half4(texture(tex0, vTexCoord)));
    color.a = unpackHalf2x16(packHalf2x16(vec2(color.a * coverage, 0.0))).x;
    bmwFragmentColor = round(clamp(color, 0.0, 1.0) * 255.0) / 255.0;
}
