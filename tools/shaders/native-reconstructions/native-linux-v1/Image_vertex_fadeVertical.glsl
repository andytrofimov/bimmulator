#version 300 es
// Original reconstruction from exact native-finalized X20511I instructions.
// .shd SHA256 d31e0a8b63c7a1dc9d23f167fac9aca8e47e020c3ca058087b878889604b0548
// Primary SHA256 6d1e438f01c22760bc16b66fc19f1cfe217ce38e2ebcb2884100a9b7247e6eab
// Secondary SHA256 ed88b80414d24d5860b220343612a7889aeb49277a815ce7412e1478d626b3b9
// table54 SHA256 d72752e164e331c427b07cfb21d79e50a61189b6ebd98d3a87ed2d54fa69a304
// 12 primary ops include leading scheduling placeholder. UV VMAD2; VPCK
// copies the position to internal0; VMUL/VMAD chain transforms XYZ + column3
// (native clip transform uses literal1, not position.w). Secondary shuffles
// MC1's row2 for VDP4: MC1[0][2], [1][2], [2][2], [3][2]. VADD/VMUL/VMAD2
// form the two fade ramps. The VDP4 consumes the ORIGINAL position.w.
precision highp float;
in vec4 a_Position;
in vec2 a_TextureCoordinate;
uniform vec4 uTextureRectangle;
uniform mat4 u_MVPMatrix;
uniform mat4 u_MC1Matrix;
uniform vec4 u_scrollAreaFadeParameters;
out vec2 vTexCoord;
out vec2 vFading;

void main()
{
    vTexCoord = a_TextureCoordinate * uTextureRectangle.zw + uTextureRectangle.xy;
    vec4 clip = u_MVPMatrix[0] * a_Position.x;
    clip = u_MVPMatrix[1] * a_Position.y + clip;
    clip = u_MVPMatrix[2] * a_Position.z + clip;
    gl_Position = u_MVPMatrix[3] + clip;
    float coordinate = dot(vec4(u_MC1Matrix[0][2], u_MC1Matrix[1][2],
                                u_MC1Matrix[2][2], u_MC1Matrix[3][2]), a_Position);
    vFading.x = (coordinate - u_scrollAreaFadeParameters.x) * u_scrollAreaFadeParameters.y;
    vFading.y = (coordinate - u_scrollAreaFadeParameters.z) * (-u_scrollAreaFadeParameters.w) + 1.0;
}
