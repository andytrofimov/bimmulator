# Third-party notices

## QEMU

The OMAP5430 and Capricorn-M patches under `nix/patches/` modify QEMU
11.1.2 source fetched by the pinned Nix package. QEMU is distributed under GPL-2.0-or-later. The upstream
source and its notices are not copied into this repository. The license text
is included in [`licenses/GPL-2.0.txt`](licenses/GPL-2.0.txt).

## Vita3K USSE visitor

The optional shader arithmetic diagnostics in `tools/usse-recompiler/` reuse
the Vita3K USSE visitor from revision
`62727b58322ea7be10aaade575ac9ef82c58f5e8`, fetched by the `shader` Nix
development shell. Vita3K is distributed under GPL-2.0-or-later. Its license
text is included in [`licenses/GPL-2.0.txt`](licenses/GPL-2.0.txt); the upstream
source itself remains external to this repository.

## Optional browser client dependencies

The browser client uses external noVNC 1.6.0 and websockify 0.13.0 source
extracts; neither is vendored or downloaded by the server. noVNC's `LICENSE.txt`
identifies its core JavaScript as MPL-2.0, its pako dependency as MIT, and DES
code as BSD-style licensed. websockify's `COPYING` contains LGPL version 3 and
its `setup.py` declares LGPLv3. Keep the complete upstream source extracts,
license texts and per-file notices together. Exact source archive URLs and
SHA-256 pins are in the [browser client guide](tools/web-client/README.md).
These dependency notices do not assign a license to the rest of this project.

The launcher also depends on QEMU, ANGLE (macOS), Mesa and libglvnd (Linux),
and other packages built from the pinned Nixpkgs revision. Their source licenses
and notices remain with those upstream packages; this repository does not
vendor their source.
