#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IDRIVE_CACHE_DIR="${IDRIVE_CACHE_DIR:-$SCRIPT_DIR/build/idrive6-cache}"
QEMU_SYSTEM_ARM="${IDRIVE_QEMU:-qemu-system-arm}"
MONITOR_MODE="false"
GDB_PORT="${IDRIVE_QEMU_GDB_PORT:-}"
EMULATOR_PROFILE="${IDRIVE_EMULATOR_PROFILE:-vexpress}"
MEMORY_MIB="${IDRIVE_MEMORY_MIB:-2048}"
SHARED_RAM="${IDRIVE_QEMU_SHARED_RAM:-0}"
SHARED_RAM_FILE="${IDRIVE_QEMU_SHARED_RAM_FILE:-}"
TCG_THREAD="${IDRIVE_TCG_THREAD:-multi}"
QEMU_CPUS="${IDRIVE_QEMU_CPUS:-2}"
DMM_TRACE="${IDRIVE_DMM_TRACE:-0}"
SGX_CAPTURE="${IDRIVE_SGX_CAPTURE:-0}"
SGX_STEP_BUDGET="${IDRIVE_SGX_STEP_BUDGET:-0}"
SGX_PRIMARY_VLDST_PROBE="${IDRIVE_SGX_PRIMARY_VLDST_PROBE:-0}"
SGX_SYNC_WDF_PROBE="${IDRIVE_SGX_SYNC_WDF_PROBE:-0}"
SGX_VBW_PROBE="${IDRIVE_SGX_VBW_PROBE:-0}"
CDC_NETWORK="${IDRIVE_QEMU_CDC_NETWORK:-1}"
MOST_SIPC_HOST_PORT="${IDRIVE_MOST_SIPC_HOST_PORT:-}"
NETWORK_PCAP="${IDRIVE_QEMU_NETWORK_PCAP:-}"
GUESTFWD_LOG="${IDRIVE_QEMU_GUESTFWD_LOG:-}"
GLES_RPC_SMOKE="${IDRIVE_GLES_RPC_SMOKE:-0}"
ANGLE_EGL_RPC_SMOKE="${IDRIVE_ANGLE_EGL_RPC_SMOKE:-0}"
ANGLE_EGL_HMI="${IDRIVE_ANGLE_EGL_HMI:-0}"
ANGLE_EGL_MAILBOX="${IDRIVE_ANGLE_EGL_MAILBOX:-0}"
ANGLE_HMI_SURFACE_WIDTH="${IDRIVE_ANGLE_HMI_SURFACE_WIDTH:-}"
ANGLE_HMI_SURFACE_HEIGHT="${IDRIVE_ANGLE_HMI_SURFACE_HEIGHT:-}"
HMI_CODING_ID6_LIGHT="${IDRIVE_HMI_CODING_ID6_LIGHT:-0}"
HMI_CODING_CID_1440="${IDRIVE_HMI_CODING_CID_1440:-0}"
HMI_CODING_CID_TOUCH="${IDRIVE_HMI_CODING_CID_TOUCH:-0}"
HMI_BENCH_INPUT="${IDRIVE_HMI_BENCH_INPUT:-0}"
HMI_RESOURCE_EN_US="${IDRIVE_HMI_RESOURCE_EN_US:-0}"
HMI_CID_POINTER="${IDRIVE_HMI_CID_POINTER:-0}"
HMI_CONTROLLER="${IDRIVE_HMI_CONTROLLER:-0}"
HMI_CID_PORT=43567
HMI_CODING_DEVELOPER_MENU="${IDRIVE_HMI_CODING_DEVELOPER_MENU:-0}"
HMI_CODING_CAMERA_RVC="${IDRIVE_HMI_CODING_CAMERA_RVC:-0}"
HMI_VARIANTREGISTRY_F32="${IDRIVE_HMI_VARIANTREGISTRY_F32:-0}"
QNX_HMI_WEB_INSPECTOR="${IDRIVE_QNX_HMI_WEB_INSPECTOR:-0}"
HMI_COMM_MODULES="${IDRIVE_HMI_COMM_MODULES:-DSI,MOSTSubSystem}"
# Pin the last verified shader map generation. The unversioned manifests carry
# stale ESSL source hashes and fail validation against the checked-in sources.
HMI_VERTEX_SHADER_MAP_MANIFEST="${IDRIVE_HMI_VERTEX_SHADER_MAP_MANIFEST:-$SCRIPT_DIR/tools/shaders/native-reconstructions/hmi-vertex-map-v67.json}"
HMI_FRAGMENT_SHADER_MAP_MANIFEST="${IDRIVE_HMI_FRAGMENT_SHADER_MAP_MANIFEST:-$SCRIPT_DIR/tools/shaders/native-reconstructions/hmi-fragment-map-v112.json}"
ANGLE_SCREEN_BRIDGE="${IDRIVE_ANGLE_SCREEN_BRIDGE:-0}"
OTF_CAPTURE="${IDRIVE_OTF_CAPTURE:-0}"
OTF_CAPTURE_OUTPUT="${IDRIVE_OTF_CAPTURE_OUTPUT:-$IDRIVE_CACHE_DIR/otf-viewer-stream.bin}"
OTF_CAPTURE_SERVER_LOG="${IDRIVE_OTF_CAPTURE_SERVER_LOG:-$IDRIVE_CACHE_DIR/otf-capture-server.log}"
OTF_CAPTURE_LOCAL_PORT="${IDRIVE_OTF_CAPTURE_LOCAL_PORT:-41000}"
QEMU_RPC_FORWARDER_SCRIPT="$SCRIPT_DIR/tools/qemu-guestfwd-proxy.py"
QEMU_STATE_FILE="${IDRIVE_QEMU_STATE_FILE:-}"
QEMU_LOADVM="${IDRIVE_QEMU_LOADVM:-}"
QEMU_QMP_SOCKET="${IDRIVE_QEMU_QMP_SOCKET:-}"
QEMU_USB_TRACE="${IDRIVE_QEMU_USB_TRACE:-0}"
QEMU_USB_TRACE_FILE="${IDRIVE_QEMU_USB_TRACE_FILE:-$IDRIVE_CACHE_DIR/qemu-usb-trace.bin}"
QEMU_STATE_SIZE="${IDRIVE_QEMU_STATE_SIZE:-4G}"
ROOTFS_READY_HOLD_SECONDS="${IDRIVE_ROOTFS_READY_HOLD_SECONDS:-0}"
CAPTURE_OMAP_UARTS="${IDRIVE_CAPTURE_OMAP_UARTS:-0}"
QNX_PDEBUG="${IDRIVE_QNX_PDEBUG:-0}"
QNX_PDEBUG_PORT="${IDRIVE_QNX_PDEBUG_PORT:-8001}"
QNX_PDEBUG_HOST_PORT="${IDRIVE_QNX_PDEBUG_HOST_PORT:-42001}"
SERIAL0_BACKEND="${IDRIVE_SERIAL0_BACKEND:-}"
SERIAL0_SOCKET="${IDRIVE_SERIAL0_SOCKET:-}"
SERIAL_LOG="${IDRIVE_SERIAL_LOG:-/tmp/idrive6-serial.log}"
SCREEN_HMI_CONTRACT="${IDRIVE_SCREEN_HMI_CONTRACT:-0}"
SCREEN_SHARED_RAM_POST="${IDRIVE_SCREEN_SHARED_RAM_POST:-0}"
SCREEN_SHARED_RAM_POST_MODE="${IDRIVE_SCREEN_SHARED_RAM_POST_MODE:-read-write}"
SCREEN_NATIVE_SHARED_IMAGE="${IDRIVE_SCREEN_NATIVE_SHARED_IMAGE:-0}"

# Keep the optional unauthenticated RFB listener private. Accept only a fixed
# numeric loopback address and display number, never QEMU's extra VNC options.
if [[ -n "${IDRIVE_VNC:-}" ]]; then
  if [[ ! "$IDRIVE_VNC" =~ ^127\.0\.0\.1:([0-9]{1,5})$ ]] ||
      (( 10#${BASH_REMATCH[1]} > 59635 )); then
    echo "IDRIVE_VNC must be 127.0.0.1:DISPLAY (0..59635), without options." >&2
    exit 1
  fi
fi

if [[ -z "${IDRIVE_ROOTFS_TREE:-}" && -d "$IDRIVE_CACHE_DIR/rootfs-x20511i" ]]; then
  IDRIVE_ROOTFS_TREE="$IDRIVE_CACHE_DIR/rootfs-x20511i"
fi
if [[ -n "${IDRIVE_ROOTFS_TREE:-}" && -z "${IDRIVE_REALIZED_ROOTFS:-}" ]]; then
  IDRIVE_REALIZED_ROOTFS="$IDRIVE_ROOTFS_TREE"
fi

if [[ ! "$MEMORY_MIB" =~ ^[0-9]+$ ]] || (( MEMORY_MIB < 1024 || MEMORY_MIB > 4096 )); then
  echo "IDRIVE_MEMORY_MIB must be an integer between 1024 and 4096." >&2
  exit 2
fi
if [[ "$SHARED_RAM" != "0" && "$SHARED_RAM" != "1" ]]; then
  echo "IDRIVE_QEMU_SHARED_RAM must be 0 or 1." >&2
  exit 2
fi
if [[ "$SHARED_RAM" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ||
        -n "$QEMU_LOADVM" ) ]]; then
  echo "IDRIVE_QEMU_SHARED_RAM requires a fresh omap5/omap5-graphics boot (no restored snapshot)." >&2
  exit 2
fi
if [[ -n "$SHARED_RAM_FILE" && "$SHARED_RAM" != "1" ]]; then
  echo "IDRIVE_QEMU_SHARED_RAM_FILE requires IDRIVE_QEMU_SHARED_RAM=1." >&2
  exit 2
fi
if [[ "$SHARED_RAM_FILE" == *,* ]]; then
  echo "IDRIVE_QEMU_SHARED_RAM_FILE cannot contain a comma." >&2
  exit 2
fi
if [[ "$TCG_THREAD" != "single" && "$TCG_THREAD" != "multi" ]]; then
  echo "IDRIVE_TCG_THREAD must be single or multi." >&2
  exit 2
fi
if [[ "$QEMU_CPUS" != "1" && "$QEMU_CPUS" != "2" ]]; then
  echo "IDRIVE_QEMU_CPUS must be 1 or 2." >&2
  exit 2
fi
if [[ "$DMM_TRACE" != "0" && "$DMM_TRACE" != "1" ]]; then
  echo "IDRIVE_DMM_TRACE must be 0 or 1." >&2
  exit 2
fi
if [[ "$SGX_CAPTURE" != "0" && "$SGX_CAPTURE" != "1" ]]; then
  echo "IDRIVE_SGX_CAPTURE must be 0 or 1." >&2
  exit 2
fi
if [[ ! "$SGX_STEP_BUDGET" =~ ^(0|[1-9][0-9]{0,2})$ ]] ||
   (( SGX_STEP_BUDGET > 256 )); then
  echo "IDRIVE_SGX_STEP_BUDGET must be 0 or an integer between 1 and 256." >&2
  exit 2
fi
if [[ "$SGX_PRIMARY_VLDST_PROBE" != "0" && "$SGX_PRIMARY_VLDST_PROBE" != "1" ]]; then
  echo "IDRIVE_SGX_PRIMARY_VLDST_PROBE must be 0 or 1." >&2
  exit 2
fi
if [[ "$SGX_PRIMARY_VLDST_PROBE" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "$SGX_STEP_BUDGET" == "0" ) ]]; then
  echo "IDRIVE_SGX_PRIMARY_VLDST_PROBE requires an OMAP5 profile and a nonzero IDRIVE_SGX_STEP_BUDGET." >&2
  exit 2
fi
if [[ "$SGX_SYNC_WDF_PROBE" != "0" && "$SGX_SYNC_WDF_PROBE" != "1" ]]; then
  echo "IDRIVE_SGX_SYNC_WDF_PROBE must be 0 or 1." >&2
  exit 2
fi
if [[ "$SGX_SYNC_WDF_PROBE" == "1" &&
      ( "$SGX_PRIMARY_VLDST_PROBE" != "1" ||
        "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "$SGX_STEP_BUDGET" == "0" ) ]]; then
  echo "IDRIVE_SGX_SYNC_WDF_PROBE requires IDRIVE_SGX_PRIMARY_VLDST_PROBE=1, an OMAP5 profile, and a nonzero step budget." >&2
  exit 2
fi
if [[ "$SGX_VBW_PROBE" != "0" && "$SGX_VBW_PROBE" != "1" ]]; then
  echo "IDRIVE_SGX_VBW_PROBE must be 0 or 1." >&2
  exit 2
fi
if [[ "$SGX_VBW_PROBE" == "1" &&
      ( "$SGX_PRIMARY_VLDST_PROBE" != "1" || "$SGX_SYNC_WDF_PROBE" != "1" ||
        "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "$SGX_STEP_BUDGET" == "0" ) ]]; then
  echo "IDRIVE_SGX_VBW_PROBE requires the primary VLDST and sync-WDF probes, an OMAP5 profile, and a nonzero step budget." >&2
  exit 2
fi
if [[ "$CDC_NETWORK" != "0" && "$CDC_NETWORK" != "1" ]]; then
  echo "IDRIVE_QEMU_CDC_NETWORK must be 0 or 1." >&2
  exit 2
fi
# The generated QNX startup helper reads this setting while the launcher keeps
# its normalized default in CDC_NETWORK. Pass the effective value downstream.
export IDRIVE_QEMU_CDC_NETWORK="$CDC_NETWORK"
if [[ -n "$MOST_SIPC_HOST_PORT" ]]; then
  if [[ "$CDC_NETWORK" != "1" || "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "$ANGLE_EGL_HMI" != "1" || "${IDRIVE_HMI_FORCE_START:-0}" != "1" ||
        -z "${IDRIVE_ROOTFS_TREE:-}" || -n "$QEMU_LOADVM" ]]; then
    echo "IDRIVE_MOST_SIPC_HOST_PORT requires the native HMI profile and its isolated CDC stack." >&2
    exit 1
  fi
  if [[ ! "$MOST_SIPC_HOST_PORT" =~ ^[0-9]{1,5}$ ]] ||
     (( 10#$MOST_SIPC_HOST_PORT < 1 || 10#$MOST_SIPC_HOST_PORT > 65535 )); then
    echo "IDRIVE_MOST_SIPC_HOST_PORT must be a TCP port between 1 and 65535." >&2
    exit 1
  fi
  if [[ "$QEMU_RPC_FORWARDER_SCRIPT" == *,* ]]; then
    echo "The MOST SIPC forwarder path must not contain commas." >&2
    exit 1
  fi
fi
if [[ -n "$NETWORK_PCAP" ]]; then
  if [[ "$CDC_NETWORK" != "1" ||
        ( "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ) ]]; then
    echo "IDRIVE_QEMU_NETWORK_PCAP requires CDC networking on an OMAP5 profile." >&2
    exit 2
  fi
  if [[ "$NETWORK_PCAP" == *,* ]]; then
    echo "IDRIVE_QEMU_NETWORK_PCAP must be a path without commas." >&2
    exit 2
  fi
fi
if [[ -n "$GUESTFWD_LOG" ]]; then
  if [[ "$CDC_NETWORK" != "1" ||
        ( "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ) ||
        ( "$GLES_RPC_SMOKE" != "1" && "$ANGLE_EGL_RPC_SMOKE" != "1" && "$ANGLE_EGL_HMI" != "1" ) ]]; then
    echo "IDRIVE_QEMU_GUESTFWD_LOG requires CDC networking with an RPC/HMI profile." >&2
    exit 2
  fi
  if [[ "$GUESTFWD_LOG" == *,* ]]; then
    echo "IDRIVE_QEMU_GUESTFWD_LOG must be a path without commas." >&2
    exit 2
  fi
fi
if [[ "$GLES_RPC_SMOKE" != "0" && "$GLES_RPC_SMOKE" != "1" ]]; then
  echo "IDRIVE_GLES_RPC_SMOKE must be 0 or 1." >&2
  exit 2
fi
if [[ "$GLES_RPC_SMOKE" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "$CDC_NETWORK" != "1" || -z "${IDRIVE_ROOTFS_TREE:-}" ||
        -z "${IDRIVE_REALIZED_ROOTFS:-}" || -n "$QEMU_LOADVM" ) ]]; then
  echo "IDRIVE_GLES_RPC_SMOKE requires a fresh OMAP5 boot, CDC networking, and staged/realized roots." >&2
  exit 2
fi
if [[ "$ANGLE_EGL_RPC_SMOKE" != "0" && "$ANGLE_EGL_RPC_SMOKE" != "1" ]]; then
  echo "IDRIVE_ANGLE_EGL_RPC_SMOKE must be 0 or 1." >&2
  exit 2
fi
if [[ "$ANGLE_EGL_HMI" != "0" && "$ANGLE_EGL_HMI" != "1" ]]; then
  echo "IDRIVE_ANGLE_EGL_HMI must be 0 or 1." >&2
  exit 2
fi
if [[ -n "$ANGLE_HMI_SURFACE_WIDTH" || -n "$ANGLE_HMI_SURFACE_HEIGHT" ]]; then
  if [[ "$ANGLE_EGL_HMI" != "1" ]]; then
    echo "IDRIVE_ANGLE_HMI_SURFACE_WIDTH/HEIGHT require IDRIVE_ANGLE_EGL_HMI=1." >&2
    exit 2
  fi
  case "$ANGLE_HMI_SURFACE_WIDTH:$ANGLE_HMI_SURFACE_HEIGHT" in
    800:480|1280:480|1440:540|1600:600|1920:720) ;;
    *)
      echo "IDRIVE_ANGLE_HMI_SURFACE_WIDTH/HEIGHT must select a supported BMW CID size: 800x480, 1280x480, 1440x540, 1600x600 or 1920x720." >&2
      exit 2
      ;;
  esac
fi
if [[ "$HMI_CODING_ID6_LIGHT" != "0" && "$HMI_CODING_ID6_LIGHT" != "1" ]]; then
  echo "IDRIVE_HMI_CODING_ID6_LIGHT must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_CODING_ID6_LIGHT" == "1" &&
      ( "$ANGLE_EGL_HMI" != "1" || "$EMULATOR_PROFILE" != "omap5-graphics" ||
        -n "$QEMU_LOADVM" || -z "${IDRIVE_ROOTFS_TREE:-}" ) ]]; then
  echo "IDRIVE_HMI_CODING_ID6_LIGHT requires a fresh omap5-graphics ANGLE HMI boot with a staged root." >&2
  exit 2
fi
if [[ "$HMI_CODING_CID_1440" != "0" && "$HMI_CODING_CID_1440" != "1" ]]; then
  echo "IDRIVE_HMI_CODING_CID_1440 must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_CODING_CID_1440" == "1" && "$HMI_CODING_ID6_LIGHT" != "1" ]]; then
  echo "IDRIVE_HMI_CODING_CID_1440 requires IDRIVE_HMI_CODING_ID6_LIGHT=1." >&2
  exit 2
fi
if [[ "$HMI_CODING_CID_TOUCH" != "0" && "$HMI_CODING_CID_TOUCH" != "1" ]]; then
  echo "IDRIVE_HMI_CODING_CID_TOUCH must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_CODING_CID_TOUCH" == "1" && "$HMI_CODING_ID6_LIGHT" != "1" ]]; then
  echo "IDRIVE_HMI_CODING_CID_TOUCH requires IDRIVE_HMI_CODING_ID6_LIGHT=1." >&2
  exit 2
fi
if [[ "$HMI_RESOURCE_EN_US" != "0" && "$HMI_RESOURCE_EN_US" != "1" ]]; then
  echo "IDRIVE_HMI_RESOURCE_EN_US must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_RESOURCE_EN_US" == "1" && "$HMI_CODING_ID6_LIGHT" != "1" ]]; then
  echo "IDRIVE_HMI_RESOURCE_EN_US requires IDRIVE_HMI_CODING_ID6_LIGHT=1." >&2
  exit 2
fi
if [[ "$HMI_BENCH_INPUT" != "0" && "$HMI_BENCH_INPUT" != "1" ]]; then
  echo "IDRIVE_HMI_BENCH_INPUT must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_BENCH_INPUT" == "1" &&
      ( "$HMI_CODING_CID_TOUCH" != "1" || "${IDRIVE_HMI_FORCE_START:-0}" != "1" ) ]]; then
  echo "IDRIVE_HMI_BENCH_INPUT requires CID touch coding and the direct HMI launch." >&2
  exit 2
fi
if [[ "$HMI_CID_POINTER" != "0" && "$HMI_CID_POINTER" != "1" ]]; then
  echo "IDRIVE_HMI_CID_POINTER must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_CID_POINTER" == "1" &&
      ( "$HMI_CODING_CID_TOUCH" != "1" || "$CDC_NETWORK" != "1" ||
        -z "$ANGLE_HMI_SURFACE_WIDTH" || -z "$ANGLE_HMI_SURFACE_HEIGHT" ) ]]; then
  echo "IDRIVE_HMI_CID_POINTER requires CID touch coding, CDC networking, and explicit CID dimensions." >&2
  exit 2
fi
if [[ "$HMI_CODING_DEVELOPER_MENU" != "0" && "$HMI_CODING_DEVELOPER_MENU" != "1" ]]; then
  echo "IDRIVE_HMI_CODING_DEVELOPER_MENU must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_CODING_DEVELOPER_MENU" == "1" &&
      ( "$ANGLE_EGL_HMI" != "1" || "$EMULATOR_PROFILE" != "omap5-graphics" ||
        -n "$QEMU_LOADVM" || -z "${IDRIVE_ROOTFS_TREE:-}" ||
        "${IDRIVE_HMI_FORCE_START:-0}" != "1" ) ]]; then
  echo "IDRIVE_HMI_CODING_DEVELOPER_MENU requires a fresh direct-HMI omap5-graphics boot with a staged root." >&2
  exit 2
fi
if [[ "$HMI_CODING_CAMERA_RVC" != "0" && "$HMI_CODING_CAMERA_RVC" != "1" ]]; then
  echo "IDRIVE_HMI_CODING_CAMERA_RVC must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_CODING_CAMERA_RVC" == "1" &&
      ( "$HMI_CODING_ID6_LIGHT" != "1" || "$HMI_VARIANTREGISTRY_F32" != "1" ||
        "$ANGLE_EGL_HMI" != "1" || "$EMULATOR_PROFILE" != "omap5-graphics" ||
        -n "$QEMU_LOADVM" || -z "${IDRIVE_ROOTFS_TREE:-}" ||
        "${IDRIVE_HMI_FORCE_START:-0}" != "1" ) ]]; then
  echo "IDRIVE_HMI_CODING_CAMERA_RVC requires the fresh F32 ID6 Light direct-HMI omap5-graphics profile." >&2
  exit 2
fi
if [[ "$HMI_VARIANTREGISTRY_F32" != "0" && "$HMI_VARIANTREGISTRY_F32" != "1" ]]; then
  echo "IDRIVE_HMI_VARIANTREGISTRY_F32 must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_VARIANTREGISTRY_F32" == "1" &&
      ( "$HMI_CODING_ID6_LIGHT" != "1" || "$ANGLE_EGL_HMI" != "1" ||
        "$EMULATOR_PROFILE" != "omap5-graphics" || -n "$QEMU_LOADVM" ||
        -z "${IDRIVE_ROOTFS_TREE:-}" || "${IDRIVE_HMI_FORCE_START:-0}" != "1" ) ]]; then
  echo "IDRIVE_HMI_VARIANTREGISTRY_F32 requires the fresh F32-coded direct-HMI omap5-graphics profile." >&2
  exit 2
fi
if [[ "$QNX_HMI_WEB_INSPECTOR" != "0" && "$QNX_HMI_WEB_INSPECTOR" != "1" ]]; then
  echo "IDRIVE_QNX_HMI_WEB_INSPECTOR must be 0 or 1." >&2
  exit 2
fi
if [[ "$QNX_HMI_WEB_INSPECTOR" == "1" &&
      ( "$ANGLE_EGL_HMI" != "1" || "$CDC_NETWORK" != "1" ||
        "$EMULATOR_PROFILE" != "omap5-graphics" || -n "$QEMU_LOADVM" ||
        "${IDRIVE_HMI_FORCE_START:-0}" != "1" ) ]]; then
  echo "IDRIVE_QNX_HMI_WEB_INSPECTOR requires a fresh direct-HMI omap5-graphics boot with CDC networking." >&2
  exit 2
fi
if [[ "$OTF_CAPTURE" != "0" && "$OTF_CAPTURE" != "1" ]]; then
  echo "IDRIVE_OTF_CAPTURE must be 0 or 1." >&2
  exit 2
fi
if [[ "$OTF_CAPTURE" == "1" ]]; then
  case "$OTF_CAPTURE_LOCAL_PORT" in
    ''|*[!0-9]*)
      echo "IDRIVE_OTF_CAPTURE_LOCAL_PORT must be a decimal TCP port." >&2
      exit 2
      ;;
  esac
  OTF_CAPTURE_LOCAL_PORT=$((10#$OTF_CAPTURE_LOCAL_PORT))
  if (( OTF_CAPTURE_LOCAL_PORT < 1024 || OTF_CAPTURE_LOCAL_PORT > 65535 )); then
    echo "IDRIVE_OTF_CAPTURE_LOCAL_PORT must be between 1024 and 65535." >&2
    exit 2
  fi
fi
if [[ "$OTF_CAPTURE" == "1" &&
      ( "$ANGLE_EGL_HMI" != "1" || "$CDC_NETWORK" != "1" ||
        "$EMULATOR_PROFILE" != "omap5-graphics" || -n "$QEMU_LOADVM" ||
        -z "${IDRIVE_ROOTFS_TREE:-}" || -z "${IDRIVE_REALIZED_ROOTFS:-}" ) ]]; then
  echo "IDRIVE_OTF_CAPTURE requires a fresh omap5-graphics HMI run with CDC networking and staged roots." >&2
  exit 2
fi
if [[ "$OTF_CAPTURE" == "1" &&
      "$SERIAL0_BACKEND" != "file" && "$SERIAL0_BACKEND" != "socket" ]]; then
  echo "IDRIVE_OTF_CAPTURE requires IDRIVE_SERIAL0_BACKEND=file or socket so the host viewer can wait for BMWOTFagent readiness." >&2
  exit 2
fi
if [[ "$OTF_CAPTURE" == "1" &&
      ( "$OTF_CAPTURE_OUTPUT" == *,* || "$OTF_CAPTURE_SERVER_LOG" == *,* ) ]]; then
  echo "IDRIVE_OTF_CAPTURE_OUTPUT and IDRIVE_OTF_CAPTURE_SERVER_LOG must not contain commas." >&2
  exit 2
fi
if [[ "$QNX_PDEBUG" != "0" && "$QNX_PDEBUG" != "1" ]]; then
  echo "IDRIVE_QNX_PDEBUG must be 0 or 1." >&2
  exit 2
fi
if [[ "$QNX_PDEBUG" == "1" ]]; then
  if [[ "$ANGLE_EGL_HMI" != "1" || "$CDC_NETWORK" != "1" ||
        "$EMULATOR_PROFILE" != "omap5-graphics" || -n "$QEMU_LOADVM" ||
        "${IDRIVE_HMI_FORCE_START:-0}" != "1" ]]; then
    echo "IDRIVE_QNX_PDEBUG requires a fresh direct-HMI omap5-graphics run with CDC networking and ANGLE's isolated QNX stack." >&2
    exit 2
  fi
  for debug_port in "$QNX_PDEBUG_PORT" "$QNX_PDEBUG_HOST_PORT"; do
    case "$debug_port" in
      ''|*[!0-9]*)
        echo "QNX pdebug target and host ports must be decimal TCP ports." >&2
        exit 2
        ;;
    esac
  done
  QNX_PDEBUG_PORT=$((10#$QNX_PDEBUG_PORT))
  QNX_PDEBUG_HOST_PORT=$((10#$QNX_PDEBUG_HOST_PORT))
  if (( QNX_PDEBUG_PORT < 1024 || QNX_PDEBUG_PORT > 65535 ||
        QNX_PDEBUG_HOST_PORT < 1024 || QNX_PDEBUG_HOST_PORT > 65535 )); then
    echo "QNX pdebug target and host ports must be between 1024 and 65535." >&2
    exit 2
  fi
  if [[ "$OTF_CAPTURE" == "1" && "$QNX_PDEBUG_HOST_PORT" == "$OTF_CAPTURE_LOCAL_PORT" ]]; then
    echo "QNX pdebug host port must differ from the OTF forwarding port." >&2
    exit 2
  fi
  export IDRIVE_QNX_PDEBUG_PORT="$QNX_PDEBUG_PORT"
  export IDRIVE_QNX_PDEBUG_HOST_PORT="$QNX_PDEBUG_HOST_PORT"
fi
if [[ "$QNX_HMI_WEB_INSPECTOR" == "1" ]]; then
  if [[ "$OTF_CAPTURE" == "1" &&
        ( "$OTF_CAPTURE_LOCAL_PORT" == "43000" || "$OTF_CAPTURE_LOCAL_PORT" == "43001" ) ]]; then
    echo "OTF host port must differ from HMI inspector ports 43000 and 43001." >&2
    exit 2
  fi
  if [[ "$QNX_PDEBUG" == "1" &&
        ( "$QNX_PDEBUG_HOST_PORT" == "43000" || "$QNX_PDEBUG_HOST_PORT" == "43001" ) ]]; then
    echo "QNX pdebug host port must differ from HMI inspector ports 43000 and 43001." >&2
    exit 2
  fi
fi
if [[ ( "$GLES_RPC_SMOKE" == "1" || "$ANGLE_EGL_RPC_SMOKE" == "1" || "$ANGLE_EGL_HMI" == "1" ) &&
      ( ! -f "$QEMU_RPC_FORWARDER_SCRIPT" ||
        "$QEMU_RPC_FORWARDER_SCRIPT" == *,* ) ]]; then
  echo "RPC smokes require tools/qemu-guestfwd-proxy.py at a path without commas." >&2
  exit 2
fi
if [[ ( "$GLES_RPC_SMOKE" == "1" || "$ANGLE_EGL_RPC_SMOKE" == "1" || "$ANGLE_EGL_HMI" == "1" ) ]] &&
   ! command -v python3 >/dev/null 2>&1; then
  echo "RPC smokes require python3 in the Nix development shell." >&2
  exit 2
fi
if [[ "$ANGLE_SCREEN_BRIDGE" != "0" && "$ANGLE_SCREEN_BRIDGE" != "1" ]]; then
  echo "IDRIVE_ANGLE_SCREEN_BRIDGE must be 0 or 1." >&2
  exit 2
fi
if [[ "$ANGLE_SCREEN_BRIDGE" == "1" &&
      ( "$ANGLE_EGL_RPC_SMOKE" != "1" || "$SHARED_RAM" != "1" ) ]]; then
  echo "IDRIVE_ANGLE_SCREEN_BRIDGE requires IDRIVE_ANGLE_EGL_RPC_SMOKE=1 and IDRIVE_QEMU_SHARED_RAM=1." >&2
  exit 2
fi
if [[ "$ANGLE_EGL_RPC_SMOKE" == "1" &&
      ( "$GLES_RPC_SMOKE" == "1" ||
        "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "$CDC_NETWORK" != "1" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ||
        -z "${IDRIVE_ROOTFS_TREE:-}" || -z "${IDRIVE_REALIZED_ROOTFS:-}" ||
        -n "$QEMU_LOADVM" ) ]]; then
  echo "IDRIVE_ANGLE_EGL_RPC_SMOKE requires a fresh omap5-graphics boot, CDC networking, software Screen, staged/realized roots, and no frame-RPC smoke or snapshot." >&2
  exit 2
fi
if [[ "$ANGLE_EGL_RPC_SMOKE" == "1" &&
      ( "${IDRIVE_EGL_DIAGNOSTICS:-0}" == "1" ||
        "${IDRIVE_EGL_PROVIDER_TRACE:-0}" == "1" ||
        "$SCREEN_HMI_CONTRACT" == "1" ||
        "$SCREEN_SHARED_RAM_POST" == "1" ||
        "$SCREEN_NATIVE_SHARED_IMAGE" == "1" ||
        "${IDRIVE_SCREEN_TEST:-0}" == "1" ||
        "${IDRIVE_SCREEN_UI_PROBE:-0}" == "1" ||
        "${IDRIVE_NATIVE_SGX_PROBE:-0}" == "1" ||
        "${IDRIVE_HMI_FORCE_START:-0}" == "1" ||
        -n "${IDRIVE_STARTER_VARIANT:-}" ) ]]; then
  echo "IDRIVE_ANGLE_EGL_RPC_SMOKE is isolated: disable other EGL, Screen, SGX and HMI probes." >&2
  exit 2
fi
if [[ "$ANGLE_EGL_HMI" == "1" &&
      ( "$ANGLE_EGL_RPC_SMOKE" == "1" || "$ANGLE_SCREEN_BRIDGE" == "1" ||
        "$GLES_RPC_SMOKE" == "1" || "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "$CDC_NETWORK" != "1" || "$SHARED_RAM" != "1" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ||
        "${IDRIVE_HMI_FORCE_START:-0}" != "1" ||
        -z "${IDRIVE_STARTER_VARIANT:-}" ||
        "${IDRIVE_EGL_DIAGNOSTICS:-0}" == "1" ||
        "${IDRIVE_EGL_PROVIDER_TRACE:-0}" == "1" ||
        "$SCREEN_HMI_CONTRACT" == "1" || "$SCREEN_SHARED_RAM_POST" == "1" ||
        "$SCREEN_NATIVE_SHARED_IMAGE" == "1" ||
        "${IDRIVE_SCREEN_TEST:-0}" == "1" ||
        "${IDRIVE_SCREEN_UI_PROBE:-0}" == "1" ||
        "${IDRIVE_NATIVE_SGX_PROBE:-0}" == "1" ||
        -z "${IDRIVE_ROOTFS_TREE:-}" || -z "${IDRIVE_REALIZED_ROOTFS:-}" ||
        -n "$QEMU_LOADVM" ) ]]; then
  echo "IDRIVE_ANGLE_EGL_HMI requires a fresh shared-RAM omap5-graphics boot, CDC networking, software Screen, one direct HMI launch with a development variant, and no competing EGL/RPC smoke or snapshot." >&2
  exit 2
fi
export IDRIVE_ANGLE_EGL_HMI="$ANGLE_EGL_HMI"
if [[ "$ANGLE_EGL_MAILBOX" != "0" && "$ANGLE_EGL_MAILBOX" != "1" ]]; then
  echo "IDRIVE_ANGLE_EGL_MAILBOX must be 0 or 1." >&2
  exit 2
fi
if [[ "$ANGLE_EGL_MAILBOX" == "1" && "$ANGLE_EGL_HMI" != "1" ]]; then
  echo "IDRIVE_ANGLE_EGL_MAILBOX requires the native HMI graphics profile." >&2
  exit 2
fi
export IDRIVE_ANGLE_EGL_MAILBOX="$ANGLE_EGL_MAILBOX"
if [[ "$HMI_CONTROLLER" != "0" && "$HMI_CONTROLLER" != "1" ]]; then
  echo "IDRIVE_HMI_CONTROLLER must be 0 or 1." >&2
  exit 2
fi
if [[ "$HMI_CONTROLLER" == "1" &&
      ( "$ANGLE_EGL_MAILBOX" != "1" || "$HMI_CID_POINTER" != "1" ) ]]; then
  echo "IDRIVE_HMI_CONTROLLER requires the graphics mailbox and the CID input relay." >&2
  exit 2
fi
if [[ "$SCREEN_HMI_CONTRACT" != "0" && "$SCREEN_HMI_CONTRACT" != "1" ]]; then
  echo "IDRIVE_SCREEN_HMI_CONTRACT must be 0 or 1." >&2
  exit 2
fi
if [[ "$SCREEN_HMI_CONTRACT" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ||
        -z "${IDRIVE_ROOTFS_TREE:-}" ) ]]; then
  echo "IDRIVE_SCREEN_HMI_CONTRACT requires omap5-graphics, the software Screen probe, and a staged root." >&2
  exit 2
fi
if [[ "$SCREEN_SHARED_RAM_POST" != "0" && "$SCREEN_SHARED_RAM_POST" != "1" ]]; then
  echo "IDRIVE_SCREEN_SHARED_RAM_POST must be 0 or 1." >&2
  exit 2
fi
if [[ "$SCREEN_SHARED_RAM_POST_MODE" != "read-write" &&
      "$SCREEN_SHARED_RAM_POST_MODE" != "hmi-gles2" ]]; then
  echo "IDRIVE_SCREEN_SHARED_RAM_POST_MODE must be read-write or hmi-gles2." >&2
  exit 2
fi
if [[ "$SCREEN_SHARED_RAM_POST_MODE" != "read-write" &&
      "$SCREEN_SHARED_RAM_POST" != "1" ]]; then
  echo "IDRIVE_SCREEN_SHARED_RAM_POST_MODE requires IDRIVE_SCREEN_SHARED_RAM_POST=1." >&2
  exit 2
fi
if [[ "$SCREEN_NATIVE_SHARED_IMAGE" != "0" && "$SCREEN_NATIVE_SHARED_IMAGE" != "1" ]]; then
  echo "IDRIVE_SCREEN_NATIVE_SHARED_IMAGE must be 0 or 1." >&2
  exit 2
fi
if [[ "$SCREEN_NATIVE_SHARED_IMAGE" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ||
        -z "${IDRIVE_ROOTFS_TREE:-}" ||
        -n "$QEMU_LOADVM" ||
        "${IDRIVE_SCREEN_TEST:-0}" != "0" ||
        "$SCREEN_HMI_CONTRACT" != "0" ||
        "$SCREEN_SHARED_RAM_POST" != "0" ||
        "${IDRIVE_SCREEN_UI_PROBE:-0}" != "0" ||
        "${IDRIVE_HMI_FORCE_START:-0}" != "0" ||
        "${IDRIVE_NATIVE_SGX_PROBE:-0}" != "0" ||
        "${IDRIVE_EGL_DIAGNOSTICS:-0}" != "0" ) ]]; then
  echo "IDRIVE_SCREEN_NATIVE_SHARED_IMAGE requires a fresh isolated software-Screen omap5-graphics boot with a staged root and no competing Screen/HMI/EGL probes." >&2
  exit 2
fi
if [[ "$SCREEN_SHARED_RAM_POST" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ||
        "$SHARED_RAM" != "1" ||
        -n "$QEMU_LOADVM" ||
        -z "${IDRIVE_ROOTFS_TREE:-}" ||
        "${IDRIVE_SCREEN_TEST:-0}" != "0" ||
        "$SCREEN_HMI_CONTRACT" != "0" ||
        "${IDRIVE_SCREEN_UI_PROBE:-0}" != "0" ||
        "${IDRIVE_HMI_FORCE_START:-0}" != "0" ) ]]; then
  echo "IDRIVE_SCREEN_SHARED_RAM_POST requires a fresh shared-RAM omap5-graphics boot, software Screen, a staged root, and no competing Screen/HMI probes." >&2
  exit 2
fi
if [[ -n "$QEMU_LOADVM" && -z "$QEMU_STATE_FILE" ]]; then
  echo "IDRIVE_QEMU_LOADVM requires IDRIVE_QEMU_STATE_FILE." >&2
  exit 2
fi
if [[ -n "$QEMU_STATE_FILE" && "$QEMU_STATE_FILE" == *,* ]]; then
  echo "IDRIVE_QEMU_STATE_FILE cannot contain a comma." >&2
  exit 2
fi
if [[ "$QEMU_QMP_SOCKET" == *,* ]]; then
  echo "IDRIVE_QEMU_QMP_SOCKET cannot contain a comma." >&2
  exit 2
fi
if [[ "$QEMU_USB_TRACE" != "0" && "$QEMU_USB_TRACE" != "1" ]]; then
  echo "IDRIVE_QEMU_USB_TRACE must be 0 or 1." >&2
  exit 2
fi
if [[ "$QEMU_USB_TRACE_FILE" == *,* ]]; then
  echo "IDRIVE_QEMU_USB_TRACE_FILE cannot contain a comma." >&2
  exit 2
fi
if [[ ! "$ROOTFS_READY_HOLD_SECONDS" =~ ^[0-9]+$ ]] ||
   (( ROOTFS_READY_HOLD_SECONDS > 300 )); then
  echo "IDRIVE_ROOTFS_READY_HOLD_SECONDS must be an integer between 0 and 300." >&2
  exit 2
fi
if [[ "$CAPTURE_OMAP_UARTS" != "0" && "$CAPTURE_OMAP_UARTS" != "1" ]]; then
  echo "IDRIVE_CAPTURE_OMAP_UARTS must be 0 or 1." >&2
  exit 2
fi
if [[ -n "$SERIAL0_BACKEND" && "$SERIAL0_BACKEND" != "file" &&
      "$SERIAL0_BACKEND" != "pty" && "$SERIAL0_BACKEND" != "stdio" &&
      "$SERIAL0_BACKEND" != "socket" ]]; then
  echo "IDRIVE_SERIAL0_BACKEND must be file, pty, stdio, or socket." >&2
  exit 2
fi
if [[ "$SERIAL0_BACKEND" == "socket" && ( -z "$SERIAL0_SOCKET" || "$SERIAL0_SOCKET" == *,* ) ]]; then
  echo "The socket serial backend requires IDRIVE_SERIAL0_SOCKET without commas." >&2
  exit 2
fi

case "$EMULATOR_PROFILE" in
  vexpress)
    PREPARE_PROFILE="vexpress"
    export IDRIVE_STARTER_PLUGIN="${IDRIVE_STARTER_PLUGIN:-none}"
    ;;
  vehicle)
    PREPARE_PROFILE="vexpress"
    export IDRIVE_STARTER_PLUGIN="${IDRIVE_STARTER_PLUGIN:-libnbt_starter_plugin-omap.so}"
    ;;
  omap5)
    PREPARE_PROFILE="omap5"
    export IDRIVE_STARTER_PLUGIN="${IDRIVE_STARTER_PLUGIN:-none}"
    ;;
  omap5-graphics)
    PREPARE_PROFILE="omap5"
    export IDRIVE_STARTER_PLUGIN="${IDRIVE_STARTER_PLUGIN:-none}"
    ;;
  *)
    echo "Unknown IDRIVE_EMULATOR_PROFILE: $EMULATOR_PROFILE (use vexpress, omap5, omap5-graphics, or vehicle)." >&2
    exit 2
    ;;
esac

if [[ -n "${IDRIVE_STARTER_VARIANT:-}" && "$EMULATOR_PROFILE" != "omap5-graphics" ]]; then
  echo "IDRIVE_STARTER_VARIANT requires the omap5-graphics profile." >&2
  exit 2
fi
if (( SGX_STEP_BUDGET > 0 )) &&
   [[ "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ]]; then
  echo "IDRIVE_SGX_STEP_BUDGET requires the omap5 or omap5-graphics profile." >&2
  exit 2
fi
if [[ "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" == "1" && "$EMULATOR_PROFILE" != "omap5-graphics" ]]; then
  echo "IDRIVE_SOFTWARE_SCREEN_PROBE requires the omap5-graphics profile." >&2
  exit 2
fi
if [[ "${IDRIVE_NATIVE_SGX_PROBE:-0}" == "1" && "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ]]; then
  echo "IDRIVE_NATIVE_SGX_PROBE requires IDRIVE_SOFTWARE_SCREEN_PROBE=1." >&2
  exit 2
fi
if [[ "${IDRIVE_HMI_FORCE_START:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5-graphics" ||
        -z "${IDRIVE_STARTER_VARIANT:-}" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ) ]]; then
  echo "IDRIVE_HMI_FORCE_START requires the graphics profile, a development variant, and software Screen." >&2
  exit 2
fi
if [[ "${IDRIVE_SCREEN_FRAME_BRIDGE:-0}" != "0" &&
      "${IDRIVE_SCREEN_FRAME_BRIDGE:-0}" != "1" ]]; then
  echo "IDRIVE_SCREEN_FRAME_BRIDGE must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_SCREEN_FRAME_BRIDGE:-0}" == "1" ]]; then
  echo "The unfinished frame-transport prototype is paused; see IMPLEMENTATION_PLAN.md." >&2
  exit 2
fi
if [[ "${IDRIVE_EGL_DIAGNOSTICS:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ) ]]; then
  echo "IDRIVE_EGL_DIAGNOSTICS requires the graphics profile and software Screen." >&2
  exit 2
fi
if [[ "${IDRIVE_EGL_PROVIDER_TRACE:-0}" != "0" && "${IDRIVE_EGL_PROVIDER_TRACE:-0}" != "1" ]]; then
  echo "IDRIVE_EGL_PROVIDER_TRACE must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_EGL_PROVIDER_TRACE:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ||
        "${IDRIVE_HMI_FORCE_START:-0}" != "1" || -z "${IDRIVE_ROOTFS_TREE:-}" ) ]]; then
  echo "IDRIVE_EGL_PROVIDER_TRACE requires the graphics profile, software Screen, HMI force-start, and a staged root." >&2
  exit 2
fi
if [[ "${IDRIVE_SHADER_PARSER_PROBE:-0}" != "0" &&
      "${IDRIVE_SHADER_PARSER_PROBE:-0}" != "1" ]]; then
  echo "IDRIVE_SHADER_PARSER_PROBE must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_SHADER_PROBE_FINALIZE:-0}" != "0" &&
      "${IDRIVE_SHADER_PROBE_FINALIZE:-0}" != "1" ]]; then
  echo "IDRIVE_SHADER_PROBE_FINALIZE must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_SHADER_PROBE_BATCH:-0}" != "0" &&
      "${IDRIVE_SHADER_PROBE_BATCH:-0}" != "1" ]]; then
  echo "IDRIVE_SHADER_PROBE_BATCH must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_SHADER_PROBE_FINALIZE:-0}" == "1" &&
      "${IDRIVE_SHADER_PARSER_PROBE:-0}" != "1" ]]; then
  echo "IDRIVE_SHADER_PROBE_FINALIZE requires IDRIVE_SHADER_PARSER_PROBE=1." >&2
  exit 2
fi
if [[ "${IDRIVE_SHADER_PROBE_BATCH:-0}" == "1" &&
      ( "${IDRIVE_SHADER_PARSER_PROBE:-0}" != "1" ||
        "${IDRIVE_SHADER_PROBE_FINALIZE:-0}" == "1" ||
        -z "${IDRIVE_SHADER_PROBE_BATCH_MANIFEST:-}" ) ]]; then
  echo "IDRIVE_SHADER_PROBE_BATCH requires the parser probe, a batch manifest, and IDRIVE_SHADER_PROBE_FINALIZE=0." >&2
  exit 2
fi
if [[ "${IDRIVE_SHADER_PARSER_PROBE:-0}" == "1" && -z "${IDRIVE_ROOTFS_TREE:-}" ]]; then
  echo "IDRIVE_SHADER_PARSER_PROBE requires IDRIVE_ROOTFS_TREE." >&2
  exit 2
fi
if [[ "${IDRIVE_HMI_NO_COMMS:-0}" != "0" && "${IDRIVE_HMI_NO_COMMS:-0}" != "1" ]]; then
  echo "IDRIVE_HMI_NO_COMMS must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_HMI_NO_COMMS:-0}" == "1" && "$EMULATOR_PROFILE" != "omap5-graphics" ]]; then
  echo "IDRIVE_HMI_NO_COMMS requires the omap5-graphics profile." >&2
  exit 2
fi
case "$HMI_COMM_MODULES" in
  DSI|MOSTSubSystem|DSI,MOSTSubSystem) ;;
  *)
    echo "IDRIVE_HMI_COMM_MODULES must be DSI, MOSTSubSystem, or DSI,MOSTSubSystem." >&2
    exit 2
    ;;
esac
export IDRIVE_HMI_COMM_MODULES="$HMI_COMM_MODULES"
if [[ "${IDRIVE_ANGLE_EGL_HMI_PREFLIGHT:-0}" != "0" &&
      "${IDRIVE_ANGLE_EGL_HMI_PREFLIGHT:-0}" != "1" ]]; then
  echo "IDRIVE_ANGLE_EGL_HMI_PREFLIGHT must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_ANGLE_EGL_HMI_PREFLIGHT:-0}" == "1" &&
      "${IDRIVE_ANGLE_EGL_HMI:-0}" != "1" ]]; then
  echo "IDRIVE_ANGLE_EGL_HMI_PREFLIGHT requires IDRIVE_ANGLE_EGL_HMI=1." >&2
  exit 2
fi
if [[ "${IDRIVE_ANGLE_EGL_HMI_POST_OTF_PREFLIGHT:-0}" != "0" &&
      "${IDRIVE_ANGLE_EGL_HMI_POST_OTF_PREFLIGHT:-0}" != "1" ]]; then
  echo "IDRIVE_ANGLE_EGL_HMI_POST_OTF_PREFLIGHT must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_ANGLE_EGL_HMI_POST_OTF_PREFLIGHT:-0}" == "1" &&
      "${IDRIVE_ANGLE_EGL_HMI_PREFLIGHT:-0}" != "1" ]]; then
  echo "IDRIVE_ANGLE_EGL_HMI_POST_OTF_PREFLIGHT requires IDRIVE_ANGLE_EGL_HMI_PREFLIGHT=1." >&2
  exit 2
fi
if [[ "${IDRIVE_SGX_MISCINFO_PROBE:-0}" != "0" &&
      "${IDRIVE_SGX_MISCINFO_PROBE:-0}" != "1" ]]; then
  echo "IDRIVE_SGX_MISCINFO_PROBE must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_SGX_MISCINFO_PROBE:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "${IDRIVE_SGX_INIT_STATUS_PROBE:-0}" != "1" ) ]]; then
  echo "IDRIVE_SGX_MISCINFO_PROBE requires OMAP5 and IDRIVE_SGX_INIT_STATUS_PROBE=1." >&2
  exit 2
fi
if [[ "${IDRIVE_SGX_SIZE_LOG_PROBE:-0}" != "0" &&
      "${IDRIVE_SGX_SIZE_LOG_PROBE:-0}" != "1" ]]; then
  echo "IDRIVE_SGX_SIZE_LOG_PROBE must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_SGX_SIZE_LOG_PROBE:-0}" == "1" &&
      "${IDRIVE_SGX_MISCINFO_PROBE:-0}" != "1" ]]; then
  echo "IDRIVE_SGX_SIZE_LOG_PROBE requires IDRIVE_SGX_MISCINFO_PROBE=1." >&2
  exit 2
fi
if [[ "${IDRIVE_SCREEN_TEST:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ) ]]; then
  echo "IDRIVE_SCREEN_TEST requires the graphics profile and software Screen." >&2
  exit 2
fi
if [[ "${IDRIVE_SCREEN_UI_PROBE:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" != "1" ) ]]; then
  echo "IDRIVE_SCREEN_UI_PROBE requires the graphics profile and software Screen." >&2
  exit 2
fi
if [[ "${IDRIVE_OMAP5_PREVIEW_SCANOUT:-0}" != "0" &&
      "${IDRIVE_OMAP5_PREVIEW_SCANOUT:-0}" != "1" ]]; then
  echo "IDRIVE_OMAP5_PREVIEW_SCANOUT must be 0 or 1." >&2
  exit 2
fi
if [[ "${IDRIVE_OMAP5_PREVIEW_SCANOUT:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" != "omap5-graphics" ||
        "${IDRIVE_SCREEN_UI_PROBE:-0}" != "1" ) ]]; then
  echo "IDRIVE_OMAP5_PREVIEW_SCANOUT requires IDRIVE_SCREEN_UI_PROBE=1 on omap5-graphics." >&2
  exit 2
fi
PREVIEW_FB_BASE="${IDRIVE_PREVIEW_FB_BASE:-0xce400000}"
if [[ "${IDRIVE_OMAP5_PREVIEW_SCANOUT:-0}" == "1" &&
      ! "$PREVIEW_FB_BASE" =~ ^0x[0-9a-fA-F]{8}$ ]]; then
  echo "IDRIVE_PREVIEW_FB_BASE must be a 32-bit hexadecimal address such as 0xce400000." >&2
  exit 2
fi

if [[ "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" == "1" ]]; then
  for required in bin/cp bin/screen lib/screen-sw.so lib/libswblit.so.1 \
                  lib/graphics/omap5430/libWFDomap5430ES2_0.so; do
    if [[ -z "${IDRIVE_ROOTFS_TREE:-}" || ! -f "$IDRIVE_ROOTFS_TREE/$required" ]]; then
      echo "Software Screen probe needs the recovered root file: $required" >&2
      exit 1
    fi
  done
fi

if [[ "${1:-}" == "--monitor" ]]; then
  MONITOR_MODE="true"
  shift
fi

if (( $# > 0 )); then
  echo "Usage: $0 [--monitor]" >&2
  exit 2
fi

if ! command -v "$QEMU_SYSTEM_ARM" >/dev/null 2>&1; then
  echo "Patched QEMU is not available: $QEMU_SYSTEM_ARM" >&2
  exit 1
fi

HMI_SHADER_MAP_PAIRS=""
HMI_FRAGMENT_SHADER_MAP_PAIRS=""
if [[ "$ANGLE_EGL_HMI" == "1" ]]; then
  RECTANGLE_SHADER_DIR="$IDRIVE_ROOTFS_TREE/opt/hmi/ID5/data/ro/common/shader"
  RECTANGLE_VERTEX_SHD="$RECTANGLE_SHADER_DIR/Rectangle_vertex.shd"
  RECTANGLE_FRAGMENT_SHD="$RECTANGLE_SHADER_DIR/Rectangle_fragment.shd"
  if [[ ! -f "$RECTANGLE_VERTEX_SHD" || ! -f "$RECTANGLE_FRAGMENT_SHD" ]]; then
    echo "ANGLE HMI shader translation requires the staged Rectangle vertex/fragment pair under $RECTANGLE_SHADER_DIR." >&2
    exit 1
  fi
  for shader_map in "$HMI_VERTEX_SHADER_MAP_MANIFEST" "$HMI_FRAGMENT_SHADER_MAP_MANIFEST"; do
    if [[ ! -f "$shader_map" ]]; then
      echo "ANGLE HMI shader translation requires a map manifest: $shader_map" >&2
      exit 1
    fi
  done
  echo "Validating native HMI shader source hashes before image preparation."
  HMI_SHADER_MAP_PAIRS="$(python3 "$SCRIPT_DIR/tools/prepare-hmi-native-essl-map.py" \
    "$HMI_VERTEX_SHADER_MAP_MANIFEST" "$IDRIVE_ROOTFS_TREE" "$SCRIPT_DIR")" || exit 1
  HMI_FRAGMENT_SHADER_MAP_PAIRS="$(python3 "$SCRIPT_DIR/tools/prepare-hmi-native-essl-map.py" \
    "$HMI_FRAGMENT_SHADER_MAP_MANIFEST" "$IDRIVE_ROOTFS_TREE" "$SCRIPT_DIR")" || exit 1
fi

BOOT_IMAGE="${IDRIVE_BOOT_IMAGE:-}"
if [[ -z "$BOOT_IMAGE" || ! -f "$BOOT_IMAGE" ]]; then
  echo "No staged QNX boot image. Run 'nix run .#idrive6 -- --prepare-only' first." >&2
  exit 1
fi

TMP_ROOT="${TMPDIR:-/tmp}"
WORK_DIR="$(mktemp -d "${TMP_ROOT%/}/idrive6-${EMULATOR_PROFILE}.XXXXXX")"
ANGLE_EGL_SERVER_PID=""
OTF_CAPTURE_SERVER_PID=""
HMI_CID_POINTER_PID=""
cleanup_run()
{
  if [[ -n "$HMI_CID_POINTER_PID" ]]; then
    kill -TERM "$HMI_CID_POINTER_PID" 2>/dev/null || true
    wait "$HMI_CID_POINTER_PID" 2>/dev/null || true
  fi
  if [[ -n "$OTF_CAPTURE_SERVER_PID" ]]; then
    kill -TERM "$OTF_CAPTURE_SERVER_PID" 2>/dev/null || true
    wait "$OTF_CAPTURE_SERVER_PID" 2>/dev/null || true
  fi
  if [[ -n "$ANGLE_EGL_SERVER_PID" ]]; then
    kill "$ANGLE_EGL_SERVER_PID" 2>/dev/null || true
    wait "$ANGLE_EGL_SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$WORK_DIR"
}
trap cleanup_run EXIT
PREPARED_IMAGE="$WORK_DIR/boot.ifs"
SECONDARY_STUB="$WORK_DIR/cpu1-wait.bin"
mkdir -p "$IDRIVE_CACHE_DIR"
if [[ "$SHARED_RAM" == "1" ]]; then
  SHARED_RAM_FILE="${SHARED_RAM_FILE:-$WORK_DIR/omap5430-guest-ram.bin}"
  if [[ -e "$SHARED_RAM_FILE" ]]; then
    echo "Refusing to replace existing shared guest RAM file: $SHARED_RAM_FILE" >&2
    echo "Remove it or select a new IDRIVE_QEMU_SHARED_RAM_FILE path." >&2
    exit 2
  fi
  mkdir -p "$(dirname -- "$SHARED_RAM_FILE")"
  if [[ "$ANGLE_SCREEN_BRIDGE" == "1" || "$ANGLE_EGL_HMI" == "1" ]]; then
    truncate -s "${MEMORY_MIB}M" "$SHARED_RAM_FILE"
    echo "Pre-created $MEMORY_MIB MiB shared RAM so the ANGLE bridge can map it before QEMU starts."
  fi
  echo "QEMU shared guest RAM: $SHARED_RAM_FILE (guest address 0x80000000 maps to file offset 0)."
fi
if [[ "$ANGLE_EGL_MAILBOX" == "1" ]]; then
  ANGLE_EGL_MAILBOX_FILE="$WORK_DIR/angle-mailbox.bin"
  truncate -s 17M "$ANGLE_EGL_MAILBOX_FILE"
fi
if [[ "$HMI_CONTROLLER" == "1" ]]; then
  HMI_CONTROLLER_SOCKET="$WORK_DIR/controller.sock"
  echo "HMI controller socket (available when the renderer is ready): $HMI_CONTROLLER_SOCKET"
fi
QEMU_DEBUG_LOG="${IDRIVE_QEMU_DEBUG_LOG:-$IDRIVE_CACHE_DIR/qemu-debug-${EMULATOR_PROFILE}.log}"
if [[ -n "${IDRIVE_STARTER_VARIANT:-}" ]]; then
  if [[ -z "${IDRIVE_ROOTFS_TREE:-}" ]]; then
    echo "IDRIVE_STARTER_VARIANT requires a staged root filesystem." >&2
    exit 2
  fi
  export IDRIVE_STARTER_VARIANT_HELPER="$WORK_DIR/starter-variant"
  "$SCRIPT_DIR/tools/build-qnx-starter-variant.sh" "$IDRIVE_STARTER_VARIANT" "$IDRIVE_STARTER_VARIANT_HELPER"
fi
if [[ "${IDRIVE_SCREEN_TEST:-0}" == "1" ]]; then
  if [[ -z "${IDRIVE_ROOTFS_TREE:-}" ]]; then
    echo "IDRIVE_SCREEN_TEST requires IDRIVE_ROOTFS_TREE." >&2
    exit 2
  fi
  export IDRIVE_SCREEN_TEST_HELPER="$WORK_DIR/screen-test"
  "$SCRIPT_DIR/tools/build-qnx-screen-test.sh" "$IDRIVE_ROOTFS_TREE" "$IDRIVE_SCREEN_TEST_HELPER"
fi
if [[ "$SCREEN_HMI_CONTRACT" == "1" ]]; then
  export IDRIVE_SCREEN_HMI_CONTRACT_HELPER="$WORK_DIR/screen-hmi-contract"
  "$SCRIPT_DIR/tools/build-qnx-screen-hmi-contract.sh" \
    "$IDRIVE_ROOTFS_TREE" "$IDRIVE_SCREEN_HMI_CONTRACT_HELPER"
fi
if [[ "$SCREEN_SHARED_RAM_POST" == "1" ]]; then
  export IDRIVE_SCREEN_SHARED_RAM_POST_HELPER="$WORK_DIR/screen-shared-ram-post"
  "$SCRIPT_DIR/tools/build-qnx-screen-shared-ram-post.sh" \
    "$IDRIVE_ROOTFS_TREE" "$IDRIVE_SCREEN_SHARED_RAM_POST_HELPER" \
    "$SCREEN_SHARED_RAM_POST_MODE"
fi
if [[ "$SCREEN_NATIVE_SHARED_IMAGE" == "1" ]]; then
  export IDRIVE_SCREEN_NATIVE_SHARED_IMAGE_HELPER="$WORK_DIR/screen-native-shared-image-probe"
  "$SCRIPT_DIR/tools/build-qnx-screen-native-shared-image-probe.sh" \
    "$IDRIVE_ROOTFS_TREE" "$IDRIVE_SCREEN_NATIVE_SHARED_IMAGE_HELPER"
fi
if [[ "${IDRIVE_SCREEN_UI_PROBE:-0}" == "1" ]]; then
  if [[ -z "${IDRIVE_ROOTFS_TREE:-}" ]]; then
    echo "IDRIVE_SCREEN_UI_PROBE requires IDRIVE_ROOTFS_TREE." >&2
    exit 2
  fi
  export IDRIVE_SCREEN_UI_HELPER="$WORK_DIR/screen-idrive6-preview"
  "$SCRIPT_DIR/tools/build-qnx-screen-idrive6-preview.sh" \
    "$IDRIVE_ROOTFS_TREE" "$IDRIVE_SCREEN_UI_HELPER"
fi
if [[ "${IDRIVE_EGL_DIAGNOSTICS:-0}" == "1" ]]; then
  if [[ -z "${IDRIVE_ROOTFS_TREE:-}" ]]; then
    echo "IDRIVE_EGL_DIAGNOSTICS requires IDRIVE_ROOTFS_TREE." >&2
    exit 2
  fi
  export IDRIVE_EGL_DIAGNOSTIC_HELPER="$WORK_DIR/egl-config-diagnostic"
  "$SCRIPT_DIR/tools/build-qnx-egl-config-diagnostic.sh" \
    "$IDRIVE_ROOTFS_TREE" "$IDRIVE_EGL_DIAGNOSTIC_HELPER"
fi
if [[ "${IDRIVE_EGL_PROVIDER_TRACE:-0}" == "1" ]]; then
  export IDRIVE_EGL_PROVIDER_TRACE_HELPER="$WORK_DIR/libidriveegltrace.so"
  "$SCRIPT_DIR/tools/build-qnx-egl-provider-trace.sh" \
    "$IDRIVE_ROOTFS_TREE" "$IDRIVE_EGL_PROVIDER_TRACE_HELPER"
fi
if [[ "${IDRIVE_SHADER_PARSER_PROBE:-0}" == "1" ]]; then
  export IDRIVE_SHADER_PARSER_PROBE_HELPER="$WORK_DIR/shader-parser-probe"
  SHADER_PARSER_PROBE_ARGS=(
    "$IDRIVE_ROOTFS_TREE" "$IDRIVE_SHADER_PARSER_PROBE_HELPER"
  )
  if [[ "${IDRIVE_SHADER_PROBE_BATCH:-0}" == "1" ]]; then
    SHADER_PARSER_PROBE_ARGS+=( --finalize-batch )
  elif [[ "${IDRIVE_SHADER_PROBE_FINALIZE:-0}" == "1" ]]; then
    SHADER_PARSER_PROBE_ARGS+=( --finalize )
  fi
  "$SCRIPT_DIR/tools/build-qnx-shader-parser-probe.sh" \
    "${SHADER_PARSER_PROBE_ARGS[@]}"
fi
if [[ "$GLES_RPC_SMOKE" == "1" ]]; then
  export IDRIVE_ANGLE_RPC_CLIENT_HELPER="$IDRIVE_CACHE_DIR/angle-rpc-client"
  "$SCRIPT_DIR/tools/build-qnx-angle-frame-client.sh" \
    "$IDRIVE_REALIZED_ROOTFS" "$IDRIVE_ANGLE_RPC_CLIENT_HELPER"
fi
if [[ "$ANGLE_EGL_RPC_SMOKE" == "1" || "$ANGLE_EGL_HMI" == "1" ]]; then
  export IDRIVE_ANGLE_EGL_PROVIDER="$IDRIVE_CACHE_DIR/libidrive-angle-provider.so"
  if [[ "$ANGLE_EGL_HMI" == "1" ]]; then
    IDRIVE_ANGLE_EGL_TRACE="${IDRIVE_ANGLE_EGL_TRACE:-1}" "$SCRIPT_DIR/tools/build-qnx-angle-egl-provider.sh" \
      "$IDRIVE_REALIZED_ROOTFS" "$IDRIVE_ANGLE_EGL_PROVIDER"
    if [[ "${IDRIVE_ANGLE_EGL_HMI_PREFLIGHT:-0}" == "1" ]]; then
      export IDRIVE_ANGLE_EGL_SMOKE_HELPER="$IDRIVE_CACHE_DIR/egl-angle-provider-smoke"
      "$SCRIPT_DIR/tools/build-qnx-angle-egl-provider-smoke.sh" \
        "$IDRIVE_REALIZED_ROOTFS" "$IDRIVE_ANGLE_EGL_SMOKE_HELPER"
    fi
  else
    "$SCRIPT_DIR/tools/build-qnx-angle-egl-provider.sh" \
      "$IDRIVE_REALIZED_ROOTFS" "$IDRIVE_ANGLE_EGL_PROVIDER"
  fi
  if [[ "$ANGLE_EGL_RPC_SMOKE" == "1" ]]; then
    export IDRIVE_ANGLE_EGL_SMOKE_HELPER="$IDRIVE_CACHE_DIR/egl-angle-provider-smoke"
    "$SCRIPT_DIR/tools/build-qnx-angle-egl-provider-smoke.sh" \
      "$IDRIVE_REALIZED_ROOTFS" "$IDRIVE_ANGLE_EGL_SMOKE_HELPER"
    if [[ "$ANGLE_SCREEN_BRIDGE" == "1" ]]; then
      export IDRIVE_ANGLE_SCREEN_SMOKE_HELPER="$IDRIVE_CACHE_DIR/angle-screen-window-smoke"
      "$SCRIPT_DIR/tools/build-qnx-angle-egl-screen-smoke.sh" \
        "$IDRIVE_REALIZED_ROOTFS" "$IDRIVE_ANGLE_SCREEN_SMOKE_HELPER"
    fi
  fi
  if [[ -z "${IDRIVE_ANGLE_EGL_SERVER_BIN:-}" || ! -x "$IDRIVE_ANGLE_EGL_SERVER_BIN" ]]; then
    echo "The Nix ANGLE host server is unavailable: ${IDRIVE_ANGLE_EGL_SERVER_BIN:-unset}" >&2
    exit 1
  fi
fi
if [[ "$HMI_CONTROLLER" == "1" ]]; then
  python3 - "$IDRIVE_ROOTFS_TREE" <<'PY'
import hashlib
from pathlib import Path
import sys

root = Path(sys.argv[1]) / "opt/hmi/ID5"
expected = {
    "bin/HmiMain3D": "418906bf10aeebcee6a02b8687b63a6c6e530a9263dc7171892c568e4d86845e",
    "lib/libhmicom.so": "c8a9bf058f7cd2d6b2b3c4d49fad983a82226a713552d6886c06749d8a7d7303",
}
for name, digest in expected.items():
    path = root / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f"Unsupported binary for the X20511I native controller: {path}")
PY
  export IDRIVE_HMI_CONTROLLER_LIBRARY="$WORK_DIR/libidrive-hmi-controller.so"
  "$SCRIPT_DIR/tools/build-qnx-hmi-controller.sh" "$IDRIVE_HMI_CONTROLLER_LIBRARY"
fi
python3 "$SCRIPT_DIR/tools/prepare-vexpress-ifs.py" \
  --profile "$PREPARE_PROFILE" \
  "$BOOT_IMAGE" "$PREPARED_IMAGE" "$SECONDARY_STUB"

if [[ -n "${IDRIVE_ROOTFS_TREE:-}" && -z "$QEMU_LOADVM" ]]; then
  if [[ ! -d "$IDRIVE_ROOTFS_TREE" ]]; then
    echo "iDrive root tree not found: $IDRIVE_ROOTFS_TREE" >&2
    exit 1
  fi
  if [[ -z "${IDRIVE_REALIZED_ROOTFS:-}" ]]; then
    echo "Set IDRIVE_REALIZED_ROOTFS to the materialized sda0 tree containing QNX tools." >&2
    exit 1
  fi
  for required in \
    "$IDRIVE_REALIZED_ROOTFS/bin/mkqnx6fs" \
    "$IDRIVE_REALIZED_ROOTFS/bin/dd" \
    "$IDRIVE_REALIZED_ROOTFS/bin/sleep" \
    "$IDRIVE_REALIZED_ROOTFS/bin/devb-loopback" \
    "$IDRIVE_REALIZED_ROOTFS/bin/bsdtar" \
    "$IDRIVE_REALIZED_ROOTFS/bin/mount" \
    "$IDRIVE_REALIZED_ROOTFS/lib/libbz2.so.1" \
    "$IDRIVE_REALIZED_ROOTFS/lib/libz.so.2"; do
    if [[ ! -f "$required" ]]; then
      echo "Missing realized QNX root tool or library: $required" >&2
      exit 1
    fi
  done
  if [[ "$QNX_PDEBUG" == "1" ]]; then
    if [[ ! -f "$IDRIVE_REALIZED_ROOTFS/bin/pdebug" ]]; then
      echo "QNX pdebug observer is missing its staged target utility: $IDRIVE_REALIZED_ROOTFS/bin/pdebug" >&2
      exit 1
    fi
    STARTER_CONFIG="$IDRIVE_REALIZED_ROOTFS/opt/sys/etc/starter.cfg"
    if [[ ! -f "$STARTER_CONFIG" ]] || ! grep -q '<Name>/bin/devc-pty</Name>' "$STARTER_CONFIG"; then
      echo "QNX pdebug requires /bin/devc-pty to be started by the realized root's starter.cfg: $STARTER_CONFIG" >&2
      exit 1
    fi
  fi
  mkdir -p "$IDRIVE_CACHE_DIR"
  ROOT_ARCHIVE="$IDRIVE_CACHE_DIR/idrive-rootfs-${EMULATOR_PROFILE}.tar.gz"
  if [[ "$HMI_CODING_CID_1440" == "1" ]]; then
    ROOT_ARCHIVE="$IDRIVE_CACHE_DIR/idrive-rootfs-${EMULATOR_PROFILE}-cid1440.tar.gz"
  fi
  ROOT_ARCHIVE="${IDRIVE_ROOT_ARCHIVE_OUTPUT:-$ROOT_ARCHIVE}"
  ROOTED_IMAGE="$WORK_DIR/boot-root.ifs"
  ARCHIVE_PROFILE_ARGS=(--gzip --cache-unchanged --emulator-profile "$EMULATOR_PROFILE")
  if [[ -n "$MOST_SIPC_HOST_PORT" ]]; then
    ROOT_ARCHIVE="${ROOT_ARCHIVE%.tar.gz}-most-sipc.tar.gz"
    ARCHIVE_PROFILE_ARGS+=(--most-sipc-stack)
  fi
  if [[ -n "${IDRIVE_STARTER_VARIANT:-}" && "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--software-screen-variant)
  fi
  if [[ "${IDRIVE_HMI_NO_COMMS:-0}" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--hmi-without-comms)
  fi
  if [[ "${IDRIVE_HMI_FORCE_START:-0}" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--suppress-hmi)
  fi
  if [[ "$HMI_CODING_ID6_LIGHT" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--hmi-coding-id6-light)
  fi
  if [[ "$HMI_CODING_CID_1440" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--hmi-coding-cid-1440)
  fi
  if [[ "$HMI_CODING_CID_TOUCH" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--hmi-coding-cid-touch)
  fi
  if [[ "$HMI_BENCH_INPUT" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--hmi-bench-input)
  fi
  if [[ "$HMI_RESOURCE_EN_US" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--hmi-resource-en-us)
  fi
  if [[ "$HMI_CODING_DEVELOPER_MENU" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--hmi-coding-developer-menu)
  fi
  if [[ "$HMI_CODING_CAMERA_RVC" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--hmi-coding-camera-rvc)
  fi
  if [[ "$HMI_VARIANTREGISTRY_F32" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--hmi-variantregistry-f32)
  fi
  # The direct release HMI must not start the BMW OTF agent unless its
  # explicitly enabled host capture path is ready. Keep the starter-managed
  # service deferred for normal runs too; the OTF viewer client stays opt-in.
  if [[ "$EMULATOR_PROFILE" == "omap5-graphics" &&
        "${IDRIVE_HMI_FORCE_START:-0}" == "1" ]]; then
    ARCHIVE_PROFILE_ARGS+=(--defer-otf-agent)
  fi
  if [[ "${IDRIVE_HMI_TITLE_CACHE_PROBE:-0}" == "1" ]]; then
    if [[ "${IDRIVE_HMI_FORCE_START:-0}" != "1" ]]; then
      echo 'IDRIVE_HMI_TITLE_CACHE_PROBE requires the direct HMI launch.' >&2
      exit 1
    fi
    export IDRIVE_HMI_TITLE_CACHE_HELPER="$WORK_DIR/hmi-title-cache"
    "$SCRIPT_DIR/tools/build-qnx-hmi-title-cache.sh" "$IDRIVE_HMI_TITLE_CACHE_HELPER"
  fi
  # Keep the argument array nonempty for macOS Bash 3.2 with set -u.
  python3 "$SCRIPT_DIR/tools/archive-idrive-rootfs.py" \
    "${ARCHIVE_PROFILE_ARGS[@]}" \
    "$IDRIVE_ROOTFS_TREE" "$ROOT_ARCHIVE"
  python3 "$SCRIPT_DIR/tools/embed-qnx6-rootfs.py" \
    "$PREPARED_IMAGE" "$ROOT_ARCHIVE" \
    "$IDRIVE_REALIZED_ROOTFS/bin/mkqnx6fs" \
    "$IDRIVE_REALIZED_ROOTFS/bin/dd" \
    "$IDRIVE_REALIZED_ROOTFS/bin/devb-loopback" \
    "$IDRIVE_REALIZED_ROOTFS/bin/bsdtar" \
    "$IDRIVE_REALIZED_ROOTFS/bin/mount" \
    "$IDRIVE_REALIZED_ROOTFS/lib/libbz2.so.1" \
    "$IDRIVE_REALIZED_ROOTFS/lib/libz.so.2" \
    "$ROOTED_IMAGE"
  export IDRIVE_ROOT_ARCHIVE="$ROOT_ARCHIVE"
  PREPARED_IMAGE="$ROOTED_IMAGE"
elif [[ -n "$QEMU_LOADVM" ]]; then
  echo "Restoring guest RAM from snapshot; skipping root archive creation and IFS embedding."
fi

if [[ "$ANGLE_EGL_RPC_SMOKE" == "1" || "$ANGLE_EGL_HMI" == "1" ]]; then
  ANGLE_EGL_SERVER_LOG="${IDRIVE_ANGLE_EGL_SERVER_LOG:-$IDRIVE_CACHE_DIR/angle-egl-rpc-server.log}"
  ANGLE_EGL_SERVER_ARGS=( --port 41416 )
  ANGLE_EGL_READY_MARKER="ANGLE_EGL_RPC_LISTEN address=127.0.0.1 port=41416"
  if [[ "$ANGLE_EGL_MAILBOX" == "1" ]]; then
    ANGLE_EGL_SERVER_ARGS=( --mailbox-file "$ANGLE_EGL_MAILBOX_FILE" )
    ANGLE_EGL_READY_MARKER="ANGLE_EGL_MAILBOX_READY"
  fi
  if [[ "$HMI_CONTROLLER" == "1" ]]; then
    ANGLE_EGL_SERVER_ARGS+=( --controller-socket "$HMI_CONTROLLER_SOCKET" )
  fi
  if [[ "$ANGLE_SCREEN_BRIDGE" == "1" || "$ANGLE_EGL_HMI" == "1" ]]; then
    ANGLE_EGL_SERVER_ARGS+=( --guest-ram-file "$SHARED_RAM_FILE" )
  fi
  if [[ -n "${IDRIVE_ANGLE_SHADER_CAPTURE_DIR:-}" ]]; then
    mkdir -p "$IDRIVE_ANGLE_SHADER_CAPTURE_DIR"
    ANGLE_EGL_SERVER_ARGS+=( --shader-capture-dir "$IDRIVE_ANGLE_SHADER_CAPTURE_DIR" )
  fi
  if [[ -n "${IDRIVE_ANGLE_DRAW_CAPTURE_DIR:-}" ]]; then
    mkdir -p "$IDRIVE_ANGLE_DRAW_CAPTURE_DIR"
    ANGLE_EGL_SERVER_ARGS+=( --draw-capture-dir "$IDRIVE_ANGLE_DRAW_CAPTURE_DIR" )
    ANGLE_EGL_SERVER_ARGS+=( --draw-capture-limit "${IDRIVE_ANGLE_DRAW_CAPTURE_LIMIT:-64}" )
  fi
  if [[ -n "${IDRIVE_ANGLE_RESOURCE_CAPTURE_DIR:-}" ]]; then
    mkdir -p "$IDRIVE_ANGLE_RESOURCE_CAPTURE_DIR"
    ANGLE_EGL_SERVER_ARGS+=( --resource-capture-dir "$IDRIVE_ANGLE_RESOURCE_CAPTURE_DIR" )
  fi
  if [[ "$ANGLE_EGL_HMI" == "1" ]]; then
    ANGLE_EGL_SERVER_ARGS+=(
      --shader-map "$RECTANGLE_FRAGMENT_SHD" \
        "$SCRIPT_DIR/tools/shaders/native-reconstructions/Rectangle_fragment.glsl"
    )
    while IFS=$'\t' read -r native_shader host_source; do
      [[ -n "$native_shader" && -n "$host_source" ]] || continue
      ANGLE_EGL_SERVER_ARGS+=( --shader-map "$native_shader" "$host_source" )
    done <<< "$HMI_SHADER_MAP_PAIRS"
    while IFS=$'\t' read -r native_shader host_source; do
      [[ -n "$native_shader" && -n "$host_source" ]] || continue
      ANGLE_EGL_SERVER_ARGS+=( --shader-map "$native_shader" "$host_source" )
    done <<< "$HMI_FRAGMENT_SHADER_MAP_PAIRS"
  fi
  "$IDRIVE_ANGLE_EGL_SERVER_BIN" "${ANGLE_EGL_SERVER_ARGS[@]}" >"$ANGLE_EGL_SERVER_LOG" 2>&1 &
  ANGLE_EGL_SERVER_PID=$!
  server_ready=0
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if ! kill -0 "$ANGLE_EGL_SERVER_PID" 2>/dev/null; then
      cat "$ANGLE_EGL_SERVER_LOG" >&2
      echo "Host ANGLE EGL RPC server exited during startup." >&2
      exit 1
    fi
    if grep -q "$ANGLE_EGL_READY_MARKER" "$ANGLE_EGL_SERVER_LOG"; then
      server_ready=1
      break
    fi
    sleep 0.25
  done
  if [[ "$server_ready" != "1" ]]; then
    cat "$ANGLE_EGL_SERVER_LOG" >&2
    echo "Host ANGLE EGL RPC server did not become ready; see $ANGLE_EGL_SERVER_LOG." >&2
    exit 1
  fi
  echo "Host ANGLE EGL RPC server ready ($ANGLE_EGL_READY_MARKER); log: $ANGLE_EGL_SERVER_LOG."
fi

if [[ "$OTF_CAPTURE" == "1" ]]; then
  mkdir -p "$(dirname -- "$OTF_CAPTURE_OUTPUT")"
  mkdir -p "$(dirname -- "$OTF_CAPTURE_SERVER_LOG")"
  mkdir -p "$(dirname -- "$SERIAL_LOG")"
  : > "$SERIAL_LOG"
  python3 "$SCRIPT_DIR/tools/otf-capture-client.py" \
    --host 127.0.0.1 --port "$OTF_CAPTURE_LOCAL_PORT" --duration 86400 \
    --retry-interval 2 --wait-for-log "$SERIAL_LOG" \
    --wait-for-marker "BMW OTF agent ready pid=" \
    --output "$OTF_CAPTURE_OUTPUT" >"$OTF_CAPTURE_SERVER_LOG" 2>&1 &
  OTF_CAPTURE_SERVER_PID=$!
  echo "BMW OTF host viewer will connect through loopback TCP $OTF_CAPTURE_LOCAL_PORT; stream: $OTF_CAPTURE_OUTPUT."
fi

if [[ "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ]]; then
  QEMU_MACHINE="omap5430"
  echo "Loading the prepared QNX image at 0x80100000 with the experimental OMAP5430 machine."
  echo "Its OMAP5 model includes the Cortex-A15 cluster, GIC, UARTs, USB, and DSS framebuffer scanout."
  if [[ "$EMULATOR_PROFILE" == "omap5-graphics" ]]; then
    echo "The graphics profile requests BMW's TILER and SCREEN packages."
    if [[ "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" == "1" ]]; then
      if [[ "${IDRIVE_NATIVE_SGX_PROBE:-0}" == "1" ]]; then
        echo "The native PowerVR probe will load BMW's service and GPU initializer."
      else
        echo "The experimental software Screen probe will try immediately, even if TILER is absent."
      fi
    fi
    if [[ -n "${IDRIVE_STARTER_VARIANT:-}" && "${IDRIVE_SOFTWARE_SCREEN_PROBE:-0}" == "1" ]]; then
      echo "The development variant will be injected after software Screen is ready."
    fi
    if [[ "${IDRIVE_HMI_FORCE_START:-0}" == "1" ]]; then
      echo "HmiMain3D will also be launched directly after the ziploader is ready."
    fi
    if [[ "$ANGLE_EGL_HMI" == "1" ]]; then
      echo "The HMI's QNX EGL/GLES dispatcher will use the host ANGLE provider."
    fi
    if [[ "${IDRIVE_HMI_NO_COMMS:-0}" == "1" ]]; then
      echo "The native HmiMain3D launch omits its DSI/MOST communication option."
    else
      echo "The native HmiMain3D launch enables communications modules: $HMI_COMM_MODULES."
    fi
    if (( ROOTFS_READY_HOLD_SECONDS > 0 )); then
      echo "The guest will hold after root extraction for $ROOTFS_READY_HOLD_SECONDS seconds for a pre-starter snapshot."
    fi
    if [[ "${IDRIVE_SCREEN_TEST:-0}" == "1" ]]; then
      echo "The QNX Screen test will post three color bands after the software server starts."
    fi
    if [[ "$SCREEN_SHARED_RAM_POST" == "1" ]]; then
      if [[ "$SCREEN_SHARED_RAM_POST_MODE" == "hmi-gles2" ]]; then
        echo "The host will fill both HMI-style GLES2 QNX Screen buffers through shared guest RAM; the guest Screen client will post both diagnostic frames."
      else
        echo "The host will fill two CPU-readable QNX Screen buffers through shared guest RAM; the guest Screen client will post both host frames."
      fi
    fi
    if [[ "$ANGLE_SCREEN_BRIDGE" == "1" ]]; then
      echo "The second ANGLE smoke will draw through a QNX Screen GLES2 window surface, copy the ANGLE frame into shared guest RAM, then post the corresponding physical Screen buffer."
    fi
    if [[ "$SCREEN_NATIVE_SHARED_IMAGE" == "1" ]]; then
      echo "The bounded QNX shared-image producer probe will exercise shm_open, mmap/mlock, mem_offset64, Screen buffer/pixmap setup and screen_read_window."
    fi
    if [[ "${IDRIVE_SCREEN_UI_PROBE:-0}" == "1" ]]; then
      echo "A CPU-rendered F32 iDrive preview will start with Screen."
      if [[ "${IDRIVE_OMAP5_PREVIEW_SCANOUT:-0}" == "1" ]]; then
        echo "The OMAP DSS GFX plane will scan out guest buffer $PREVIEW_FB_BASE."
      fi
    fi
  fi
else
  QEMU_MACHINE="vexpress-a15"
  echo "Loading the prepared QNX image at 0x80100000 with QEMU's vexpress-a15 board."
  echo "This is a Cortex-A15 substitute, not an OMAP5430 model. Press Ctrl+C to stop."
fi
echo "Using QEMU TCG with thread=$TCG_THREAD and cpus=$QEMU_CPUS."
echo "QEMU debug log: $QEMU_DEBUG_LOG"

QEMU_AUX_SERIAL_ARGS=()
if [[ "$CAPTURE_OMAP_UARTS" == "1" &&
      ( "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ) ]]; then
  # QEMU's legacy serial backends provide serial0 through serial3. The OMAP5
  # model maps its first three non-console UARTs to those backends; later OMAP
  # UARTs remain guest-visible but have no host character backend.
  for serial_index in 1 2 3; do
    serial_log_var="IDRIVE_SERIAL${serial_index}_LOG"
    serial_backend_var="IDRIVE_SERIAL${serial_index}_BACKEND"
    serial_backend="${!serial_backend_var:-file}"
    if [[ "$serial_backend" == "pty" ]]; then
      QEMU_AUX_SERIAL_ARGS+=( -serial pty )
      echo "Opening OMAP UART backend $serial_index as a PTY."
    elif [[ "$serial_backend" == "file" ]]; then
      serial_log="${!serial_log_var:-${TMPDIR:-/tmp}/idrive6-serial${serial_index}.log}"
      QEMU_AUX_SERIAL_ARGS+=( -serial "file:$serial_log" )
      echo "Capturing OMAP UART backend $serial_index to $serial_log."
    else
      echo "IDRIVE_SERIAL${serial_index}_BACKEND must be file or pty." >&2
      exit 2
    fi
  done
fi

if [[ "$SHARED_RAM" == "1" ]]; then
  QEMU_MACHINE_OPTIONS="$QEMU_MACHINE,memory-backend=idrive-shared-ram"
  QEMU_MAILBOX_ARGS=()
  if [[ "$ANGLE_EGL_MAILBOX" == "1" ]]; then
    QEMU_MAILBOX_ARGS=( -object "memory-backend-file,id=idrive-angle-mailbox,size=17M,mem-path=$ANGLE_EGL_MAILBOX_FILE,share=on" )
    QEMU_MACHINE_OPTIONS+=",graphics-mailbox=idrive-angle-mailbox"
  fi
  QEMU_RAM_ARGS=(
    -object "memory-backend-file,id=idrive-shared-ram,size=${MEMORY_MIB}M,mem-path=$SHARED_RAM_FILE,share=on"
    "${QEMU_MAILBOX_ARGS[@]}"
    -M "$QEMU_MACHINE_OPTIONS"
  )
else
  QEMU_RAM_ARGS=( -M "$QEMU_MACHINE" -m "$MEMORY_MIB" )
fi

QEMU_LOG_TYPES="guest_errors,unimp"
if [[ "$HMI_CID_POINTER" == "1" ]]; then
  QEMU_LOG_TYPES+=",trace:input_event_abs,trace:input_event_btn,trace:input_event_key_qcode,trace:input_event_sync"
fi
QEMU_ARGS=(
  "${QEMU_RAM_ARGS[@]}" \
  -accel "tcg,thread=$TCG_THREAD" \
  -cpu cortex-a15 \
  -smp "$QEMU_CPUS" \
  -device "loader,file=$PREPARED_IMAGE,addr=0x80100000,force-raw=on,cpu-num=0" \
  -device loader,data=0x1,data-len=4,addr=0xbffe6110 \
  -device loader,data=0x1,data-len=4,addr=0xbffe6104 \
  -device loader,data=0x10a04,data-len=4,addr=0xbffe416c \
  -device loader,data=0x2,data-len=4,addr=0xbffe4170 \
  -device loader,data=0x0,data-len=4,addr=0xbffe2204 \
  -device loader,data=0x1,data-len=4,addr=0xbffe0014 \
  -device loader,data=0x2,data-len=4,addr=0xbffe8804 \
  -audio driver=none \
  -no-reboot \
  -d "$QEMU_LOG_TYPES" \
  -D "$QEMU_DEBUG_LOG"
)
if [[ "$QEMU_USB_TRACE" == "1" ]]; then
  mkdir -p "$(dirname -- "$QEMU_USB_TRACE_FILE")"
  QEMU_ARGS+=(
    -trace enable=usb_packet_state_change
    -trace enable=usb_port_attach
    -trace enable=usb_ehci_packet_submit
    -trace enable=usb_ehci_qtd_fields
    -trace enable=usb_ehci_packet_action
    -trace enable=usb_ehci_guest_bug
    -trace enable=usb_ohci_td_bad_pid
    -trace enable=usb_ohci_td_pkt_hdr
    -trace enable=usb_ohci_td_bad_direction
    -trace "file=$QEMU_USB_TRACE_FILE"
  )
  echo "QEMU USB endpoint trace: $QEMU_USB_TRACE_FILE"
fi
if [[ "$QEMU_CPUS" == "2" ]]; then
  QEMU_ARGS+=( -device "loader,file=$SECONDARY_STUB,addr=0xbfff0000,force-raw=on,cpu-num=1" )
fi

if [[ "$DMM_TRACE" == "1" && "$EMULATOR_PROFILE" == "omap5-graphics" ]]; then
  QEMU_ARGS+=( -global omap5430-dss.trace-dmm=true )
  echo "Tracing OMAP5 DMM register traffic in $QEMU_DEBUG_LOG."
fi

if [[ -n "$QEMU_STATE_FILE" ]]; then
  if [[ ! -e "$QEMU_STATE_FILE" ]]; then
    mkdir -p "$(dirname -- "$QEMU_STATE_FILE")"
    qemu-img create -f qcow2 "$QEMU_STATE_FILE" "$QEMU_STATE_SIZE"
  fi
  QEMU_ARGS+=( -drive "if=none,file=$QEMU_STATE_FILE,format=qcow2,id=idrive-state" )
  echo "QEMU VM snapshots will use $QEMU_STATE_FILE."
fi
if [[ -n "$QEMU_LOADVM" ]]; then
  QEMU_ARGS+=( -loadvm "$QEMU_LOADVM" )
  echo "Restoring QEMU snapshot '$QEMU_LOADVM'."
fi
if [[ -n "$QEMU_QMP_SOCKET" ]]; then
  QEMU_ARGS+=( -qmp "unix:$QEMU_QMP_SOCKET,server=on,wait=off" )
  echo "QEMU management socket: $QEMU_QMP_SOCKET"
fi

if [[ "${IDRIVE_OMAP5_PREVIEW_SCANOUT:-0}" == "1" ]]; then
  # Configure the OMAP5 GFX plane to scan out the preview window presented
  # through QNX Screen. Screen owns the buffer and updates the plane address.
  QEMU_ARGS+=(
    -device loader,data=0x01df04ff,data-len=4,addr=0x5800107c
    -device "loader,data=$PREVIEW_FB_BASE,data-len=4,addr=0x58001080"
    -device "loader,data=$PREVIEW_FB_BASE,data-len=4,addr=0x58001084"
    -device loader,data=0x0,data-len=4,addr=0x58001088
    -device loader,data=0x01df04ff,data-len=4,addr=0x5800108c
    -device loader,data=0x17,data-len=4,addr=0x580010a0
    -device loader,data=0x42,data-len=4,addr=0x58001040
  )
fi

if [[ "${IDRIVE_SDMA_TRACE:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ) ]]; then
  QEMU_ARGS+=( -global omap5430-sdma.trace=true )
  echo "OMAP5 SDMA trace is logged to $QEMU_DEBUG_LOG."
fi

if [[ "${IDRIVE_SGX_TRACE:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ) ]]; then
  QEMU_ARGS+=( -global omap5430-sgx.trace=true )
  echo "OMAP5 SGX register trace is logged to $QEMU_DEBUG_LOG."
fi

if [[ "$SGX_CAPTURE" == "1" &&
      ( "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ) ]]; then
  QEMU_ARGS+=( -global omap5430-sgx.capture-firmware=true )
  echo "OMAP5 SGX will capture the first init event's PDS page, MMU descriptors, and USE code-base candidates."
elif [[ "$SGX_CAPTURE" == "1" ]]; then
  echo "IDRIVE_SGX_CAPTURE=1 requires the omap5 or omap5-graphics profile." >&2
  exit 2
fi

if (( SGX_STEP_BUDGET > 0 )); then
  QEMU_ARGS+=( -global "omap5430-sgx.usse-step-budget=$SGX_STEP_BUDGET" )
  echo "OMAP5 SGX will execute at most $SGX_STEP_BUDGET validated USSE entry instructions, then stop at unsupported behavior."
fi

if [[ "$SGX_PRIMARY_VLDST_PROBE" == "1" ]]; then
  QEMU_ARGS+=( -global omap5430-sgx.usse-primary-vldst-probe=true )
  echo "OMAP5 SGX diagnostic applies the SGX543 scalar-load model to two captured words, assuming primary-program context."
fi

if [[ "$SGX_SYNC_WDF_PROBE" == "1" ]]; then
  QEMU_ARGS+=( -global omap5430-sgx.usse-sync-wdf-probe=true )
  echo "OMAP5 SGX diagnostic assumes the captured WDF wait is satisfied after the preceding synchronous memory read."
fi

if [[ "$SGX_VBW_PROBE" == "1" ]]; then
  QEMU_ARGS+=( -global omap5430-sgx.usse-vbw-probe=true )
  echo "OMAP5 SGX diagnostic applies the SGX543-reference AND to one exact captured word, assuming primary-program TEMP banks."
fi

if [[ "${IDRIVE_SGX_INIT_STATUS_PROBE:-0}" == "1" &&
      ( "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ) ]]; then
  QEMU_ARGS+=( -global omap5430-sgx.init-status-probe=true )
  echo "OMAP5 SGX INIT_COMPLETE probe signals at most two matching init kicks; it does not emulate SGX."
fi

if [[ "${IDRIVE_SGX_MISCINFO_PROBE:-0}" == "1" ]]; then
  QEMU_ARGS+=( -global omap5430-sgx.miscinfo-probe=true )
  echo "OMAP5 SGX GETMISCINFO probe returns BMW DDK/build/options and the driver-derived 13-field ABI table; it does not execute SGX firmware."
fi
if [[ "${IDRIVE_SGX_SIZE_LOG_PROBE:-0}" == "1" ]]; then
  echo "QNX sloginfo will stream SGXMKIF size-check records to the serial log before Screen starts."
fi

if [[ -n "${IDRIVE_VNC:-}" ]]; then
  QEMU_ARGS+=( -vnc "$IDRIVE_VNC" )
fi
if [[ -n "${IDRIVE_DISPLAY:-}" ]]; then
  QEMU_ARGS+=( -display "$IDRIVE_DISPLAY" )
elif [[ "$EMULATOR_PROFILE" != "omap5" && "$EMULATOR_PROFILE" != "omap5-graphics" ]]; then
  QEMU_ARGS+=( -display none )
fi

# The graphics profile removes QNX's OMAP5 xHCI host driver because it crashes
# with QEMU's generic xHCI model, so attach the CDC NIC to the guest's EHCI bus.
if [[ "$CDC_NETWORK" == "1" &&
      ( "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ) ]]; then
  if [[ "$GLES_RPC_SMOKE" == "1" || "$ANGLE_EGL_RPC_SMOKE" == "1" || "$ANGLE_EGL_HMI" == "1" ]]; then
    GUESTFWD_OPTIONS=""
    if [[ -n "$MOST_SIPC_HOST_PORT" ]]; then
      GUESTFWD_OPTIONS=",guestfwd=tcp:160.48.199.253:5555-cmd:python3 \"$QEMU_RPC_FORWARDER_SCRIPT\" 127.0.0.1 $MOST_SIPC_HOST_PORT"
      echo "Guest MOST SIPC port 5555 forwards to host loopback TCP $MOST_SIPC_HOST_PORT."
    fi
    if [[ "$ANGLE_EGL_MAILBOX" == "0" ]]; then
      GUESTFWD_COMMAND="python3 \"$QEMU_RPC_FORWARDER_SCRIPT\" 127.0.0.1 41416"
      if [[ -n "$GUESTFWD_LOG" ]]; then
        GUESTFWD_COMMAND+=" \"$GUESTFWD_LOG\""
      fi
      GUESTFWD_OPTIONS+=",guestfwd=tcp:160.48.199.253:41416-cmd:$GUESTFWD_COMMAND"
      echo "Guest TCP port 41416 starts a per-connection Python bridge to the loopback-only host ANGLE RPC server."
      if [[ -n "$GUESTFWD_LOG" ]]; then
        echo "QEMU guestfwd child events will be logged to $GUESTFWD_LOG."
      fi
    fi
    OTF_HOSTFWD_OPTION=""
    if [[ "$OTF_CAPTURE" == "1" ]]; then
      OTF_HOSTFWD_OPTION=",hostfwd=tcp:127.0.0.1:$OTF_CAPTURE_LOCAL_PORT-160.48.199.225:1000"
    fi
    if [[ "$QNX_PDEBUG" == "1" ]]; then
      OTF_HOSTFWD_OPTION+=",hostfwd=tcp:127.0.0.1:$QNX_PDEBUG_HOST_PORT-160.48.199.225:$QNX_PDEBUG_PORT"
      echo "QNX pdebug will listen in the guest on port $QNX_PDEBUG_PORT; host access is loopback-only on 127.0.0.1:$QNX_PDEBUG_HOST_PORT. qconn retains guest port 8000."
    fi
    if [[ "$QNX_HMI_WEB_INSPECTOR" == "1" ]]; then
      OTF_HOSTFWD_OPTION+=",hostfwd=tcp:127.0.0.1:43000-160.48.199.225:8080,hostfwd=tcp:127.0.0.1:43001-160.48.199.225:8081"
      echo "HMI VariantRegistry inspector candidates 8080/8081 are forwarded only to host loopback ports 43000/43001."
    fi
    if [[ "$HMI_CID_POINTER" == "1" ]]; then
      OTF_HOSTFWD_OPTION+=",hostfwd=udp:127.0.0.1:$HMI_CID_PORT-160.48.199.225:30567"
    fi
    QEMU_ARGS+=(
      -netdev "user,id=idrive-net,net=160.48.199.0/24,host=160.48.199.253$OTF_HOSTFWD_OPTION$GUESTFWD_OPTIONS"
      -device usb-net,bus=usb-bus.0,netdev=idrive-net
    )
    if [[ "$OTF_CAPTURE" == "1" ]]; then
      echo "Host loopback TCP $OTF_CAPTURE_LOCAL_PORT forwards to the BMW OTF agent listening on guest port 1000."
    fi
  else
    QEMU_ARGS+=(
      -netdev user,id=idrive-net,net=160.48.199.0/24,host=160.48.199.253
      -device usb-net,bus=usb-bus.0,netdev=idrive-net
    )
  fi
  if [[ -n "$NETWORK_PCAP" ]]; then
    QEMU_ARGS+=( -object "filter-dump,id=idrive-net-dump,netdev=idrive-net,file=$NETWORK_PCAP" )
    echo "QEMU guest network packets will be captured to $NETWORK_PCAP."
  fi
elif [[ "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ]]; then
  # Without -nic none, QEMU creates a default USB NIC for the OMAP machine's
  # qemu_create_nic_device() loop even when no network option was requested.
  # Disabling it also permits VM snapshots, since usb-net is not migratable.
  QEMU_ARGS+=( -nic none )
  echo "QEMU USB CDC Ethernet and QEMU's default NIC are disabled for this OMAP5 run."
fi

if [[ "$EMULATOR_PROFILE" == "omap5-graphics" ]]; then
  QEMU_ARGS+=( -device usb-kbd )
  if [[ "$HMI_CID_POINTER" == "1" ]]; then
    QEMU_ARGS+=( -device usb-tablet,bus=usb-bus.1 )
    : > "$QEMU_DEBUG_LOG"
    CONTROLLER_RELAY_ARGS=()
    if [[ "$HMI_CONTROLLER" == "1" ]]; then
      CONTROLLER_RELAY_ARGS=( --controller-socket "$HMI_CONTROLLER_SOCKET" )
    fi
    python3 "$SCRIPT_DIR/tools/idrive-cid-input.py" --port "$HMI_CID_PORT" \
      --width "$ANGLE_HMI_SURFACE_WIDTH" --height "$ANGLE_HMI_SURFACE_HEIGHT" \
      "${CONTROLLER_RELAY_ARGS[@]}" \
      relay "$QEMU_DEBUG_LOG" &
    HMI_CID_POINTER_PID=$!
  else
    QEMU_ARGS+=( -device usb-mouse )
  fi
fi

if [[ -n "$GDB_PORT" ]]; then
  QEMU_ARGS+=( -S -gdb "tcp::$GDB_PORT" )
  echo "QEMU is paused for GDB on TCP port $GDB_PORT."
fi

if [[ "$MONITOR_MODE" == "true" ]]; then
  SERIAL0_BACKEND="${SERIAL0_BACKEND:-file}"
  if [[ "$SERIAL0_BACKEND" == "file" ]]; then
    QEMU_SERIAL0_ARGS=( -serial "file:$SERIAL_LOG" )
    echo "QEMU monitor is on this terminal; primary serial output is logged to $SERIAL_LOG."
  elif [[ "$SERIAL0_BACKEND" == "pty" ]]; then
    QEMU_SERIAL0_ARGS=( -serial pty )
    echo "QEMU monitor is on this terminal; primary serial output is a PTY."
  elif [[ "$SERIAL0_BACKEND" == "socket" ]]; then
    QEMU_SERIAL0_ARGS=( -chardev "socket,id=idrive-uart0,path=$SERIAL0_SOCKET,server=on,wait=off,logfile=$SERIAL_LOG" -serial chardev:idrive-uart0 )
    echo "Guest serial socket: $SERIAL0_SOCKET; log: $SERIAL_LOG"
  else
    QEMU_SERIAL0_ARGS=( -serial stdio )
    echo "QEMU monitor is on this terminal; primary serial output shares this terminal."
  fi
  if [[ "$CAPTURE_OMAP_UARTS" == "1" &&
        ( "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ) ]]; then
    QEMU_SERIAL0_ARGS+=( "${QEMU_AUX_SERIAL_ARGS[@]}" )
  fi
  if [[ -n "${IDRIVE_HMI_RUN_MANIFEST:-}" ]]; then
    python3 "$SCRIPT_DIR/tools/write-hmi-run-manifest.py" \
      --output "$IDRIVE_HMI_RUN_MANIFEST" \
      --profile-file "$IDRIVE_HMI_PROFILE_FILE" \
      --prepared-image "$PREPARED_IMAGE" \
      -- "$QEMU_SYSTEM_ARM" "${QEMU_ARGS[@]}" "${QEMU_SERIAL0_ARGS[@]}" -monitor stdio
  fi
  "$QEMU_SYSTEM_ARM" "${QEMU_ARGS[@]}" "${QEMU_SERIAL0_ARGS[@]}" -monitor stdio
else
  SERIAL0_BACKEND="${SERIAL0_BACKEND:-stdio}"
  if [[ "$SERIAL0_BACKEND" == "file" ]]; then
    QEMU_SERIAL0_ARGS=( -serial "file:$SERIAL_LOG" )
  elif [[ "$SERIAL0_BACKEND" == "pty" ]]; then
    QEMU_SERIAL0_ARGS=( -serial pty )
  elif [[ "$SERIAL0_BACKEND" == "socket" ]]; then
    QEMU_SERIAL0_ARGS=( -chardev "socket,id=idrive-uart0,path=$SERIAL0_SOCKET,server=on,wait=off,logfile=$SERIAL_LOG" -serial chardev:idrive-uart0 )
    echo "Guest serial socket: $SERIAL0_SOCKET; log: $SERIAL_LOG"
  else
    QEMU_SERIAL0_ARGS=( -serial stdio )
  fi
  if [[ "$CAPTURE_OMAP_UARTS" == "1" &&
        ( "$EMULATOR_PROFILE" == "omap5" || "$EMULATOR_PROFILE" == "omap5-graphics" ) ]]; then
    QEMU_SERIAL0_ARGS+=( "${QEMU_AUX_SERIAL_ARGS[@]}" )
  fi
  if [[ -n "${IDRIVE_HMI_RUN_MANIFEST:-}" ]]; then
    python3 "$SCRIPT_DIR/tools/write-hmi-run-manifest.py" \
      --output "$IDRIVE_HMI_RUN_MANIFEST" \
      --profile-file "$IDRIVE_HMI_PROFILE_FILE" \
      --prepared-image "$PREPARED_IMAGE" \
      -- "$QEMU_SYSTEM_ARM" "${QEMU_ARGS[@]}" "${QEMU_SERIAL0_ARGS[@]}" -monitor none
  fi
  "$QEMU_SYSTEM_ARM" "${QEMU_ARGS[@]}" "${QEMU_SERIAL0_ARGS[@]}" -monitor none
fi
