#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

cfg="${1:?usage: ./scripts/scale/run.sh PolyChipC1Config}"

case "$cfg" in
  PolyChipC1Config|PolyChipC2Config|PolyChipC3Config|PolyChipC4Config) ;;
  *)
    echo "unknown scale config: $cfg" >&2
    exit 1
    ;;
esac

full_cfg="examples.poly.${cfg}"
out="output/scale/${cfg}"
build="${out}/build"
bitstream="${build}/fpgaCompDir/bitstream.bit"
log="${out}/sim"

test -f "$bitstream"

mkdir -p "$log"

echo "[scale run] config=${full_cfg}"
echo "[scale run] bitstream=${bitstream}"
echo "[scale run] log=${log}"

bbdev bebop-p2e --runworkload "--config ${full_cfg} --image fw_payload --bitstream ${bitstream} --build-dir ${build} --log-dir ${log}"

echo "[scale run] simulation log=${log}"
echo "[scale run] performance result=${log}"
