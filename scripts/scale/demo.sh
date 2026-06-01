#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

configs=(
  PolyChipC1Config
  PolyChipC2Config
  PolyChipC3Config
  PolyChipC4Config
)

for cfg in "${configs[@]}"; do
  ./scripts/scale/build.sh "$cfg"
  ./scripts/scale/run.sh "$cfg"
done

echo "[scale demo] output=output/scale"
