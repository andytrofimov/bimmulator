# Credits and provenance

## Original emulator

This fork builds on [agent00jackson/bimmulator](https://github.com/agent00jackson/bimmulator) (⭐ 14, checked 2026-11-11), maintained by [agent00jackson](https://github.com/agent00jackson). The upstream emulator, OMAP5430/Capricorn-M integration, firmware staging, graphics bridge and original launch profiles remain the foundation of this work. Upstream history and existing notices are retained.

The Linux x86_64 host port and local browser-client contributions are maintained by [andytrofimov](https://github.com/andytrofimov). Their independent upstream drafts are [Linux host support](https://github.com/agent00jackson/bimmulator/pull/1) and [noVNC/iDrive client](https://github.com/agent00jackson/bimmulator/pull/2). Implementation, tests and contribution descriptions were prepared with an AI coding agent; this is not a claim of human review or qualification on every platform.

## Dependencies and prior work

- **QEMU contributors** — the machine emulation and device framework. The repository's QEMU patches retain their original provenance and GPL notices.
- **ANGLE contributors** — the existing macOS host graphics path.
- **Mesa and libglvnd contributors** — the Linux EGL/GLES implementation and vendor dispatch.
- **noVNC and websockify contributors** — the external browser RFB client and WebSocket bridge. Their complete source/license notices are preserved with the pinned dependency packages.
- **Vita3K contributors** — the optional USSE visitor used by the existing shader diagnostic tooling.
- **Nix/Nixpkgs contributors** — the reproducible dependency and host-package infrastructure.

See [third-party notices](THIRD_PARTY_NOTICES.md), the retained license texts and pinned source references for details. Dependency notices do not grant a license to unrelated code or firmware.

## Windows reference — not integrated

[Ahmet Karaçalı's Windows/WSL2 work](https://github.com/AhmetKaracali/bimmulator-windows) (⭐ 0, checked 2026-11-11) was reviewed as a reference. Windows integration is deferred; its code has **not** been merged into this fork. Its additions carry separate PolyForm Noncommercial terms, which are not silently applied to this project. This acknowledgment does not claim native Windows support or reuse of that implementation.

## Firmware, assets and screenshots

BMW firmware and vehicle assets are supplied externally by the user and are not distributed by this repository. BMW, QNX and other product names and marks belong to their respective owners. Any demonstration screenshot shows an actual local emulator session, not a reimplementation of the BMW interface in HTML; it does not provide firmware or imply endorsement.
