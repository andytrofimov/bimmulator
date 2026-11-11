#version 300 es
// Original reconstruction from nativeB CPU-finalized X20511I Text_fragment_fade.
// .shd SHA256 77140b130ca8a7cee0aab7ea128babdcb43afe8e8818e5b21c5e36695054b6e4
// Primary SHA256 e8df432afc6008c36dda1d0e99d8f4d29c9ec5299815f39cae6fadb8b79cf0df
// table44 SHA256 9c06a396e257c6928cccf1dc0c76ef294250c3cc1c169f97b6d22d49514cf3b6
// table54 SHA256 8b795201ad9699db7cdb56f5f45810d1b56a0876a225ea3b79d9e550942077ea
// Exact source11 -> SA9 high F16 lane is u_opacity, NOT zero. Native PA0/1
// holds packed vColor; sample occupies PA2/3; PA4..6 carries F32 vFading.
// MAX/MIN clamp three fades; F16 MUL/MUL forms their product; F16 MUL/MUL
// forms opacity * glyph * fade and OVERWRITES color alpha. vColor.a is not
// multiplied. Final VPCK converts F16 RGBA to normalized U8. Glyph is sampled
// red, supported by the live GL_LUMINANCE atlas contract of V112 Text.
// Native texture-to-PA/packed output lane equivalence remains a candidate;
// the CPU-only finalizer used RGBA8, not an observed native glyph draw.
precision highp float;
uniform sampler2D tex0;
uniform float u_opacity;
in vec3 vFading;
in vec4 vColor;
in vec2 vTexCoord;
layout(location = 0) out vec4 bmwFragmentColor;

float half1(float value)
{
    return unpackHalf2x16(packHalf2x16(vec2(value, 0.0))).x;
}

void main()
{
    vec3 fading = clamp(vFading, 0.0, 1.0);
    float fade = half1(fading.x * fading.y);
    fade = half1(fade * fading.z);
    float glyph = half1(texture(tex0, vTexCoord).r);
    float alpha = half1(half1(u_opacity) * glyph);
    alpha = half1(alpha * fade);
    vec3 color = vec3(unpackHalf2x16(packHalf2x16(vColor.xy)), half1(vColor.z));
    bmwFragmentColor = round(clamp(vec4(color, alpha), 0.0, 1.0) * 255.0) / 255.0;
}
