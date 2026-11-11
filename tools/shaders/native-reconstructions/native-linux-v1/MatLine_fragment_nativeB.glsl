#version 300 es
// Original reconstruction from nativeB CPU-finalized X20511I mat_line.frag.
// .shd SHA256 97c1c6620721dd924eb601633826d20b2575201e584978c57c88ef2924375ce1
// Primary SHA256 d9e4863b7d35e88ea2a07d552e4e615eeb5592018c1c5f2f80a3d6053e4b3566
// Secondary SHA256 fe737efa5495e62b0f5bd9c9118f947d65b4f38457c7c4eb0a14eedf5cb97128
// table44 SHA256 4d78ece692dc75bafda8f2a9534767b3dd2c99132bdc668d29871cf784902dea
// table54 SHA256 e909a9b6fd004628835745f1c4c45648f5e0f9fa9078241861775ca81c24b05e
// table54 packs SA10=(CO.x,CO.y), SA11=(CO.z,opacity), all F16. Secondary
// VPCK quantizes CO RGB; SOP2M copies it to output RGB. Sample is packed in
// PA0/1, v_main_menu in PA2 low F16. Two F16 VMAD2 operations compute
// first=menu*sample.B+sample.G, then coverage=first-menu*sample.G. Retain
// BOTH half-rounding boundaries, rather than replacing with an ideal mix().
// V16NMAD multiplies coverage by opacity; final VPCK writes ONLY alpha.
// Normalized RGBA texture-to-native lane mapping remains a candidate. This
// fixes source-bound packing, not yet an attribution of any live green line.
precision highp float;
uniform sampler2D t;
uniform vec3 CO;
uniform float opacity;
in vec2 uv;
in float v_main_menu;
layout(location = 0) out vec4 bmwFragmentColor;

float half1(float value)
{
    return unpackHalf2x16(packHalf2x16(vec2(value, 0.0))).x;
}

void main()
{
    vec4 sampleColor = texture(t, uv);
    float green = half1(sampleColor.g);
    float blue = half1(sampleColor.b);
    float menu = half1(v_main_menu);
    float first = half1(menu * blue + green);
    float coverage = half1((-green) * menu + first);
    float alpha = half1(coverage * half1(opacity));
    vec3 color = vec3(unpackHalf2x16(packHalf2x16(CO.xy)), half1(CO.z));
    bmwFragmentColor = round(clamp(vec4(color, alpha), 0.0, 1.0) * 255.0) / 255.0;
}
