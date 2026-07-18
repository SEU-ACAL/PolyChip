#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

./scripts/scale/build.sh PolyChipC1Config
./scripts/scale/build.sh PolyChipC2Config
./scripts/scale/build.sh PolyChipC3Config
./scripts/scale/build.sh PolyChipC4Config

./scripts/scale/run.sh PolyChipC1Config embench_top
./scripts/scale/run.sh PolyChipC1Config dnntest_top

./scripts/scale/run.sh PolyChipC2Config embench_top
./scripts/scale/run.sh PolyChipC2Config dnntest_top

./scripts/scale/run.sh PolyChipC3Config embench_top
./scripts/scale/run.sh PolyChipC3Config dnntest_top

./scripts/scale/run.sh PolyChipC4Config embench_top
./scripts/scale/run.sh PolyChipC4Config dnntest_top

echo "[scale demo] output=output/scale"
