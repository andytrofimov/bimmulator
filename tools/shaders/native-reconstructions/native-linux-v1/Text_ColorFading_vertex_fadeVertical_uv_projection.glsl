#version 300 es
// Reconstructed host ESSL from exact BMW .shd symbols and finalized USSE.
// .shd sha256: 21bd82bd8d53570bd6f330770809bd6f6cdce5907d6dc17e8568ffffba0c4ade
// Candidate module sha256: 5b550a00cc6e8921f6202f9b830e6d2539bf267851c40552763258567a7ea6a5
// Constant-copy table sha256: 1f6b6ae2b9a6b7610a7216649e3c68bb608221fb4b2d9dbb2cafff0df3d3be66
uniform mat4 u_MVPMatrix;
uniform mat4 u_MC1Matrix;
uniform vec4 u_scrollAreaFadeParameters;
uniform vec4 u_color;

const vec4 _53[32] = vec4[](vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0));
const int _66[4] = int[](0, 0, 0, 0);
const bool _72[4] = bool[](false, false, false, false);

in vec4 a_Position;
in vec2 a_TextureCoordinate;
in float a_Custom;
const vec4 attribute_register_3 = vec4(0.0);
const vec4 attribute_register_4 = vec4(0.0);
const vec4 attribute_register_5 = vec4(0.0);
const vec4 attribute_register_6 = vec4(0.0);
const vec4 attribute_register_7 = vec4(0.0);
const vec4 attribute_register_8 = vec4(0.0);
const vec4 attribute_register_9 = vec4(0.0);
const vec4 attribute_register_10 = vec4(0.0);
const vec4 attribute_register_11 = vec4(0.0);
const vec4 attribute_register_12 = vec4(0.0);
const vec4 attribute_register_13 = vec4(0.0);
const vec4 attribute_register_14 = vec4(0.0);
const vec4 attribute_register_15 = vec4(0.0);
out vec4 vColor;
out vec3 vFading;
out vec2 vTexCoord;

vec4 pa[32] = _53;
vec4 sa[32] = _53;
vec4 internal[4] = vec4[](vec4(0.0), vec4(0.0), vec4(0.0), vec4(0.0));
vec4 _output[32] = _53;

void secondary_program()
{
    vec4 _254 = sa[9];
    _254.z = sa[8].w;
    sa[9] = _254;
    vec4 _262 = sa[9];
    _262.w = sa[8].z;
    sa[9] = _262;
    vec4 _274 = sa[10];
    _274.x = uintBitsToFloat(floatBitsToUint(sa[9].x));
    sa[10] = _274;
    vec4 _283 = sa[10];
    _283.y = sa[8].y;
    sa[10] = _283;
}

void primary_program()
{
    vec2 _293 = vec2(sa[5].z, sa[5].w);
    _output[1] = vec4(_293.x, _293.y, _output[1].z, _output[1].w);
    vec2 _303 = vec2(sa[6].x, sa[6].y);
    _output[1] = vec4(_output[1].x, _output[1].y, _303.x, _303.y);
    vec4 _316 = _output[2];
    _316.w = uintBitsToFloat(floatBitsToUint(pa[1].x));
    _output[2] = _316;
    vec4 _326 = _output[3];
    _326.x = uintBitsToFloat(floatBitsToUint(pa[1].y));
    _output[3] = _326;
    vec2 _337 = vec2(pa[0].x, pa[0].y);
    vec2 _344 = vec2(pa[0].z, pa[0].w);
    internal[0] = vec4(_337.x, _337.y, _344.x, _344.y);
    internal[1] = vec4(sa[4].z, sa[4].w, sa[5].x, sa[5].y) * vec4(internal[0].x, internal[0].x, internal[0].x, internal[0].x);
    internal[1] = vec4(internal[0].y, internal[0].y, internal[0].y, internal[0].y) * vec4(sa[3].z, sa[3].w, sa[4].x, sa[4].y) + internal[1];
    internal[1] = vec4(internal[0].z, internal[0].z, internal[0].z, internal[0].z) * vec4(sa[2].z, sa[2].w, sa[3].x, sa[3].y) + internal[1];
    vec2 _434 = vec2(1.0) * vec2(sa[6].z, sa[6].w) + vec2(internal[1].x, internal[1].y);
    _output[0] = vec4(_434.x, _434.y, _output[0].z, _output[0].w);
    vec2 _452 = vec2(sa[7].x, sa[7].y) + vec2(internal[1].z, internal[1].w);
    _output[0] = vec4(_output[0].x, _output[0].y, _452.x, _452.y);
    vec4 _473 = internal[0];
    _473.x = dot(vec4(sa[10].x, sa[9].z, sa[9].w, sa[10].y), internal[0]);
    internal[0] = _473;
    vec2 _489 = (vec2(0.0) - vec2(sa[7].z, sa[8].x)) + vec2(internal[0].x, internal[0].x);
    pa[0] = vec4(_489.x, _489.y, pa[0].z, pa[0].w);
    vec4 _502 = _output[2];
    _502.x = uintBitsToFloat(floatBitsToUint(pa[2].x));
    _output[2] = _502;
    vec4 _516 = _output[2];
    _516.y = pa[0].x * sa[7].w;
    _output[2] = _516;
    vec4 _531 = _output[2];
    _531.z = pa[0].y * (0.0 - sa[9].y) + 1.0;
    _output[2] = _531;
}

void main()
{
    pa[0] = a_Position;
    pa[1] = vec4(a_TextureCoordinate, 0.0, 1.0);
    pa[2] = vec4(a_Custom, 0.0, 0.0, 1.0);
    pa[3] = attribute_register_3;
    pa[4] = attribute_register_4;
    pa[5] = attribute_register_5;
    pa[6] = attribute_register_6;
    pa[7] = attribute_register_7;
    pa[8] = attribute_register_8;
    pa[9] = attribute_register_9;
    pa[10] = attribute_register_10;
    pa[11] = attribute_register_11;
    pa[12] = attribute_register_12;
    pa[13] = attribute_register_13;
    pa[14] = attribute_register_14;
    pa[15] = attribute_register_15;
































    // Native uniform/constants copied through the IMG table.
    sa[2].z = u_MVPMatrix[2][0];
    sa[2].w = u_MVPMatrix[2][1];
    sa[3].x = u_MVPMatrix[2][2];
    sa[3].y = u_MVPMatrix[2][3];
    sa[3].z = u_MVPMatrix[1][0];
    sa[3].w = u_MVPMatrix[1][1];
    sa[4].x = u_MVPMatrix[1][2];
    sa[4].y = u_MVPMatrix[1][3];
    sa[4].z = u_MVPMatrix[0][0];
    sa[4].w = u_MVPMatrix[0][1];
    sa[5].x = u_MVPMatrix[0][2];
    sa[5].y = u_MVPMatrix[0][3];
    sa[5].z = u_color.x;
    sa[5].w = u_color.y;
    sa[6].x = u_color.z;
    sa[6].y = u_color.w;
    sa[6].z = u_MVPMatrix[3][0];
    sa[6].w = u_MVPMatrix[3][1];
    sa[7].x = u_MVPMatrix[3][2];
    sa[7].y = u_MVPMatrix[3][3];
    sa[7].z = u_scrollAreaFadeParameters.x;
    sa[7].w = u_scrollAreaFadeParameters.y;
    sa[8].x = u_scrollAreaFadeParameters.z;
    sa[8].y = u_MC1Matrix[3][2];
    sa[8].z = u_MC1Matrix[2][2];
    sa[8].w = u_MC1Matrix[1][2];
    sa[9].x = u_MC1Matrix[0][2];
    sa[9].y = u_scrollAreaFadeParameters.w;
































    secondary_program();
    primary_program();
    gl_Position = _output[0];
    vColor = _output[1];
    vFading = _output[2].xyz;
    vTexCoord = vec2(_output[2].w, _output[3].x);

}
