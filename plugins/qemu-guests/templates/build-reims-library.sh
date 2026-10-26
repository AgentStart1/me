#!/usr/bin/env bash
set -euo pipefail
export PATH="/ucrt64/bin:/usr/bin:$PATH"
export PYTHONUTF8=1
work="$(cygpath -u "$1")"
export CARGO_TARGET_DIR="$(cygpath -m "$work/target")"
export CARGO_BUILD_JOBS="$2"
cd "$work/reims-vgpu"
cargo +stable-x86_64-pc-windows-gnu rustc --locked --release \
    -p reims-vgpu-c --no-default-features --features vulkan \
    -- --print native-static-libs 2>&1 | tee "$work/native-static-libs.log"
cd firmware
MSYS2_ARG_CONV_EXCL='*' make
