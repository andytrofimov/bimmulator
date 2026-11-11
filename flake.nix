{
  description = "F32 BMW iDrive 6 emulator with user-supplied PSdZData";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs, ... }:
    let
      systems = [ "aarch64-darwin" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      qemuPatches = {
        omap5-core = ./nix/patches/qemu/0001-omap5-core.patch;
        sgx-diagnostics = ./nix/patches/qemu/0002-sgx-diagnostics.patch;
        usb-network = ./nix/patches/qemu/0003-usb-network.patch;
        graphics-mailbox = ./nix/patches/qemu/0004-graphics-mailbox.patch;
      };
      qemuPatchSeries = import ./nix/qemu-patches.nix { inherit qemuPatches; };
      host = system:
        let
          pkgs = import nixpkgs {
            inherit system;
            overlays = [ self.overlays.default ];
          };
          source = pkgs.lib.cleanSourceWith {
            src = ./.;
            filter = path: _type:
              let
                name = baseNameOf path;
                localData = [
                  ".git"
                  "build"
                  "captures"
                  "firmware"
                  "idrive6-cache"
                  "idrive6.toml"
                  "psdzdata"
                ];
              in !(builtins.elem name localData);
          };
          isLinux = pkgs.stdenv.hostPlatform.isLinux;
          qemu = pkgs.qemu-omap5;
          shaderPython = pkgs.python3.withPackages (pythonPackages: [
            pythonPackages.capstone
            pythonPackages.pyyaml
          ]);
          # Match the pinned Vita3K translator's private builder API used by the
          # optional, host-side shader arithmetic diagnostics.
          glslangBuilder = pkgs.fetchFromGitHub {
            owner = "KhronosGroup";
            repo = "glslang";
            rev = "fc9889c889561c5882e83819dcaffef5ed45529b";
            hash = "sha256-HwFP4KJuA+BMQVvBWV0BCRj9U5I3CLEU+5bBtde2f6w=";
          };
          vitaShaderSource = pkgs.fetchFromGitHub {
            owner = "Vita3K";
            repo = "Vita3K";
            rev = "62727b58322ea7be10aaade575ac9ef82c58f5e8";
            hash = "sha256-iZoBhLMQy6k9u7ww7XPe3youFeWFUa3Wvv2gDjsobPo=";
          };
          angleServer = pkgs.stdenv.mkDerivation {
            pname = "idrive6-angle-rpc-server";
            version = "1";
            src = source;
            nativeBuildInputs = [ pkgs.clang ];
            buildInputs = [ pkgs.angle ];
            buildPhase = ''
              runHook preBuild
              clang++ -std=c++17 -O2 -Wall -Wextra -Werror \
                -I${pkgs.angle}/include -I$src/tools \
                $src/tools/angle-egl-rpc-server.cpp \
                -L${pkgs.angle}/lib -Wl,-rpath,${pkgs.angle}/lib -lEGL -lGLESv2 \
                -o angle-egl-rpc-server
              runHook postBuild
            '';
            installPhase = ''
              mkdir -p $out/bin
              install -m755 angle-egl-rpc-server $out/bin/angle-egl-rpc-server
            '';
          };
          mesaServer = pkgs.stdenv.mkDerivation {
            pname = "idrive6-mesa-rpc-server";
            version = "1";
            src = source;
            nativeBuildInputs = [ pkgs.clang pkgs.pkg-config pkgs.makeWrapper ];
            buildInputs = [ pkgs.libglvnd ];
            buildPhase = ''
              runHook preBuild
              IDRIVE_HOST_CXX=clang++ bash tools/build-mesa-egl-rpc-server.sh mesa-egl-rpc-server
              runHook postBuild
            '';
            installPhase = ''
              mkdir -p $out/bin
              install -m755 mesa-egl-rpc-server $out/bin/mesa-egl-rpc-server
              # Select the bundled Mesa vendor and software drivers on non-NixOS
              # hosts too, without relying on /run/opengl-driver or a display server.
              wrapProgram $out/bin/mesa-egl-rpc-server \
                --set LIBGL_ALWAYS_SOFTWARE 1 \
                --set LIBGL_DRIVERS_PATH ${pkgs.mesa}/lib/dri \
                --set __EGL_VENDOR_LIBRARY_FILENAMES ${pkgs.mesa}/share/glvnd/egl_vendor.d/50_mesa.json
            '';
          };
          graphicsServer = if isLinux then mesaServer else angleServer;
          serverName = if isLinux then "mesa-egl-rpc-server" else "angle-egl-rpc-server";
          lzoLibrary = "${pkgs.lzo}/lib/liblzo2.${if isLinux then "so" else "dylib"}";
          webSource = name: version: url: sha256: pkgs.stdenvNoCC.mkDerivation {
            pname = "idrive6-${name}-source";
            inherit version;
            src = pkgs.fetchurl { inherit url sha256; name = "${name}-${version}.tar.gz"; };
            dontBuild = true;
            installPhase = ''
              mkdir -p $out
              cp -R . $out/
            '';
          };
          novnc = webSource "novnc" "1.6.0"
            "https://codeload.github.com/novnc/noVNC/tar.gz/refs/tags/v1.6.0"
            "5066103959ef4e9b10f37e5a148627360dd8414e4cf8a7db92bdbd022e728aaa";
          websockify = webSource "websockify" "0.13.0"
            "https://codeload.github.com/novnc/websockify/tar.gz/refs/tags/v0.13.0"
            "b6413e364efd04f3c92ec8c17747e3c4adc20157c2ef1c5d019a26d944a46df8";
          launcher = pkgs.writeShellApplication {
            name = "idrive6";
            runtimeInputs = [
              pkgs.python3
              novnc
              websockify
              pkgs.nix
              pkgs.coreutils
              pkgs.findutils
              pkgs.gnugrep
              pkgs.gawk
              pkgs.gnused
              pkgs.gnutar
              pkgs.gzip
              pkgs.bash
              pkgs.lzo
              pkgs.llvmPackages.lld
              pkgs.llvmPackages.llvm
              pkgs.clang
              qemu
              graphicsServer
            ];
            text = ''
              export IDRIVE_SOURCE_ROOT="$PWD"
              export IDRIVE_QEMU="${qemu}/bin/qemu-system-arm"
              export IDRIVE_KOMBI_QEMU="${pkgs.qemu-capricorn-m}/bin/qemu-system-mips64el"
              export IDRIVE_QNX_CLANG="${pkgs.llvmPackages.clang-unwrapped}/bin/clang"
              ${pkgs.lib.optionalString (!isLinux) ''export IDRIVE_ANGLE_ROOT="${pkgs.angle}"''}
              export IDRIVE_LZO_LIBRARY="${lzoLibrary}"
              export IDRIVE_HOST_CXX="${pkgs.clang}/bin/clang++"
              export IDRIVE_ANGLE_SERVER="${graphicsServer}/bin/${serverName}"
              export IDRIVE_NOVNC="${novnc}"
              export IDRIVE_WEBSOCKIFY="${websockify}"
              export IDRIVE_NIX="${pkgs.nix}/bin/nix"
              exec ${pkgs.python3}/bin/python3 ${source}/tools/idrive6-launch.py "$@"
            '';
          };
        in
        {
          packages = {
            default = launcher;
            idrive6 = launcher;
            novnc-source = novnc;
            websockify-source = websockify;
            qemu-omap5 = qemu;
            qemu-capricorn-m = pkgs.qemu-capricorn-m;
          } // pkgs.lib.optionalAttrs isLinux {
            mesa-egl-rpc-server = mesaServer;
          } // pkgs.lib.optionalAttrs (!isLinux) {
            angle-egl-rpc-server = angleServer;
          };

          apps.idrive6 = {
            type = "app";
            program = "${launcher}/bin/idrive6";
          };

          devShells = {
            default = pkgs.mkShell ({
              packages = [
                qemu
                graphicsServer
                (if isLinux then pkgs.libglvnd else pkgs.angle)
                pkgs.pkg-config
                pkgs.lzo
                pkgs.python3Packages.capstone
                pkgs.python3Packages.pyyaml
                pkgs.clang
                pkgs.llvmPackages.clang-unwrapped
                pkgs.llvmPackages.llvm
                pkgs.llvmPackages.lld
                pkgs.git
              ];
              IDRIVE_QEMU = "${qemu}/bin/qemu-system-arm";
              IDRIVE_ANGLE_SERVER = "${graphicsServer}/bin/${serverName}";
              IDRIVE_HOST_CXX = "${pkgs.clang}/bin/clang++";
              IDRIVE_KOMBI_QEMU = "${pkgs.qemu-capricorn-m}/bin/qemu-system-mips64el";
              IDRIVE_QNX_CLANG = "${pkgs.llvmPackages.clang-unwrapped}/bin/clang";
              IDRIVE_LZO_LIBRARY = lzoLibrary;
            } // pkgs.lib.optionalAttrs (!isLinux) {
              IDRIVE_ANGLE_ROOT = "${pkgs.angle}";
            });

            shader = pkgs.mkShell {
              packages = with pkgs; [
                shaderPython
                clang
                lld
                cmake
                ninja
                spirv-tools
                spirv-cross
                vulkan-tools
              ];
              buildInputs = with pkgs; [ fmt vulkan-loader vulkan-headers ]
                ++ pkgs.lib.optionals pkgs.stdenv.hostPlatform.isDarwin [ pkgs.moltenvk ];
              IDRIVE_QNX_CLANG = "${pkgs.llvmPackages.clang-unwrapped}/bin/clang";
              IDRIVE_GLSLANG_INCLUDE = "${glslangBuilder}";
              IDRIVE_VITA3K_SOURCE = "${vitaShaderSource}";
              shellHook = pkgs.lib.optionalString pkgs.stdenv.hostPlatform.isDarwin ''
                export VK_DRIVER_FILES="${pkgs.moltenvk}/share/vulkan/icd.d/MoltenVK_icd.json"
              '';
            };
          };
        };
    in
    {
      overlays.default = final: prev: {
        qemu-capricorn-m =
          assert prev.qemu.version == "11.1.2";
          (prev.qemu.override {
            # nixpkgs creates qemu-kvm -> qemu-system-${prev.stdenv.hostPlatform.qemuArch}.
            hostCpuTargets = [ "mips64el-softmmu" "${prev.stdenv.hostPlatform.qemuArch}-softmmu" ];
            sdlSupport = true;
            openGLSupport = false;
          }).overrideAttrs (old: {
            patches = (old.patches or [ ]) ++ [
              ./nix/patches/capricorn-m/0001-add-capricorn-m-machine.patch
            ];
          });

        qemu-omap5 =
          assert prev.qemu.version == "11.1.2";
          (prev.qemu.override {
            # Keep the ARMv7 guest and nixpkgs' native-host qemu-kvm alias target.
            hostCpuTargets = [ "arm-softmmu" "${prev.stdenv.hostPlatform.qemuArch}-softmmu" ];
            gtkSupport = prev.stdenv.hostPlatform.isLinux;
          }).overrideAttrs (old: {
            patches = (old.patches or [ ]) ++ qemuPatchSeries;
          });
      };

      packages = forAllSystems (system: (host system).packages);
      apps = forAllSystems (system: (host system).apps);
      devShells = forAllSystems (system: (host system).devShells);
    };
}
