#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

cfg="${1:?usage: ./scripts/scale/build.sh PolyChipC1Config}"

case "$cfg" in
  PolyChipC1Config|PolyChipC2Config|PolyChipC3Config|PolyChipC4Config)
    full_cfg="examples.poly.${cfg}"
    ;;
  *)
    echo "unknown scale config: $cfg" >&2
    exit 1
    ;;
esac

out="output/scale/${cfg}"
vsrc="${out}/vsrc"
build="${out}/build"

if ! command -v bbdev >/dev/null 2>&1; then
  echo "missing command: bbdev" >&2
  echo "enter nix develop first, or run: nix develop -c ./scripts/scale/build.sh ${cfg}" >&2
  exit 1
fi

mkdir -p "$out"

echo "[scale build] config=${full_cfg}"
echo "[scale build] vsrc=${vsrc}"
echo "[scale build] build=${build}"

bbdev bebop-p2e --verilog "--config ${full_cfg} --output-dir ${vsrc}"
bbdev bebop-p2e --buildbitstream "--config ${full_cfg} --vsrc-dir ${vsrc} --build-dir ${build}"

test -f "${build}/fpgaCompDir/bitstream.bit"
echo "[scale build] bitstream=${build}/fpgaCompDir/bitstream.bit"
