# Explicit Linux native shader selection

These optional full manifests retain the existing baseline and select a bounded set of additional host ESSL reconstructions:

- [Vertex selection](<../tools/shaders/native-reconstructions/hmi-linux-native-vertex-v1.json>): 34 mappings.
- [Fragment selection](<../tools/shaders/native-reconstructions/hmi-linux-native-fragment-v1.json>): 36 mappings.

The F32 profile explicitly selects both stages together. The older default manifests and their source files remain available and unchanged; the selection is not a replacement for every renderer or firmware profile. Sources resolve relative to the repository; native asset paths resolve under the operator's separately staged `opt/hmi/ID5/data/ro`. No private root, cache path, starter, application or service mock is a dependency of these manifests.

## Bounded source provenance

The selections flatten the previously used vertex UV-projection delta and fragment nativeB delta over their corresponding ConnectedDrive full maps. The selection/base SHA-256 metadata records exactly which manifest texts were consulted; those old proposal files are not runtime dependencies and are not copied here.

| Stage | Historical selected delta SHA-256 | Historical full base SHA-256 |
| --- | --- | --- |
| Vertex | `f868ee0df193995595cb560b93be39f378d1e25bd911ee34653259daff8e9a30` | `a3cedca7ec8788616a2ebde13937d9ffe63e1004536f180b7bee26a046b70155` |
| Fragment | `6992f571394566f07453ebb6f4dc5de8ea09f21cff61bd2a0bac0d821b83e1f7` | `f46278dc744adb6b057799b72699dfce2fac8fac02344107335d1ea6de1b94b3` |

Of 70 distinct referenced GLSL sources, 64 are byte-identical to public baseline `bf03f2e` and are reused in place. Only six additional sources (379 lines) are copied into the versioned [native-linux-v1 directory](<../tools/shaders/native-reconstructions/native-linux-v1>):

| Source | Own ESSL SHA-256 |
| --- | --- |
| [Image vertex/fade](<../tools/shaders/native-reconstructions/native-linux-v1/Image_vertex_fadeVertical.glsl>) | `038fdfea4ff235b5df34d17046ae51f0b401da3ae7938c7b66ee1ba33d6f75b7` |
| [Text vertex/UV](<../tools/shaders/native-reconstructions/native-linux-v1/Text_ColorFading_vertex_fadeVertical_uv_projection.glsl>) | `f7e62334f23d25e0fad0ff9649500469b8616e0506e3925935984539df5b3635` |
| [Luminance-alpha image fragment](<../tools/shaders/native-reconstructions/native-linux-v1/ImageLuminanceAlpha_fragment.glsl>) | `d625d7ddc52c8baa415806881268c0ca2f7547e2ed192bb6f7c3963372249895` |
| [Image fade fragment](<../tools/shaders/native-reconstructions/native-linux-v1/Image_fragment_fade.glsl>) | `d78d3ffc2639669c7d294f2794227b2239d2b982b7605b186cc034a2e87bce3d` |
| [Line fragment/nativeB](<../tools/shaders/native-reconstructions/native-linux-v1/MatLine_fragment_nativeB.glsl>) | `3298ade77f94720c7bf4ca82ed6a3196b76b9bdfab4ccaadf468d69340062e6b` |
| [Text fade fragment/nativeB](<../tools/shaders/native-reconstructions/native-linux-v1/Text_fragment_fade_nativeB.glsl>) | `5fc0909cf259f0b051a004c9a54d2847bf9bf80ebccd6158b136452932c40c49` |

These are readable host arithmetic reconstructions, not vendor shader binaries or embedded binary/bytecode arrays. The text vertex retains generated host SSA/register-model scaffolding from the existing reconstruction; it is not asserted to be a clean-room implementation. Headers identify instruction/symbol/finalizer-derived basis and hashes. Native hashes are matching/provenance metadata only. No OEM binary, texture, image, SDK header, capture, instruction decoder or finalizer was read or executed for this port. This bounded audit cannot independently establish original authorship or grant publication rights. No overall project license was found; no blanket MIT/GPL grant or additional rights over external inputs are invented here. Preserve existing notices and review licensing separately before distribution.

## Historical evidence is not current qualification

The prior nativeB result recorded these exact selected delta hashes and observed readable native labels/icons and joint use of the text/line corrections. That run used a private prepared starter and both service/availability mocks. It does **not** qualify the new app-free/mock-free profile or prove every mapping independently. Historical admissions in mapping metadata are deliberately retained: normalized texture-to-native sample lanes, output packing/rounding and some UV/layout assumptions remain candidates, not universally verified firmware contracts. Joint historical visual acceptance does not turn these into universal proofs.

The additional image/fade and basic native text mappings have no direct mock dependency, but actual rendering of the new profile still requires an independently authorized fresh native run. These maps do not promise full ConnectedDrive functionality, a working own app, all firmware variants, complete SGX semantics or any vehicle result. They also do not fix missing GL state forwarding by themselves.

## Host validation and limits

Run:

```sh
python3 -m unittest discover -s tests -p test_personal_shader_maps.py -v
```

The [tests](<../tests/test_personal_shader_maps.py>) invoke the actual [map validator](<../tools/prepare-hmi-native-essl-map.py>) against disposable synthetic native-input bytes, never firmware. All shipped ESSL SHA pins remain unchanged. They check 34/36 complete mappings, source/native pin failures, missing sources, traversal/absolute/control-character rejection, no partial TSV output on failure, and cross-stage delta rejection. Optional existing software EGL/GLES3 compiles all six additions and links text, image/fade, luminance-alpha and baseline-line/nativeB stage pairs, checking fragment output location zero. No extra packages, server, guest or VM is required.

This is source/hash/parser/link-interface evidence, not pixel correctness or native loading. Native payload hashes cannot be revalidated without separately authorized external inputs. The inherited Rectangle vertex mapping lacks a native SHA pin; this port preserves that baseline exception rather than inventing a hash. The validator's existing lexical path checks are tested, not claimed to provide symlink containment. The F32 profile selects this map pair explicitly; firmware metadata/HMI pins are unchanged.
