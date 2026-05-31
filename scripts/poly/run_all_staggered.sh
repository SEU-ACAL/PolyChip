#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DELAY="${DELAY:-30}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"

tests=(
  chipyard-2-test
  chipyard-4-test
  chipyard-8-test
  chipyard-16-test
  chipyard-32-test
  poly-2-test
  poly-4-test
  poly-8-test
  poly-16-test
  poly-32-test
)

pids=()

cd "$ROOT"
log_root="output/poly/launcher-logs/${RUN_ID}"
mkdir -p "$log_root"
echo "Launcher log dir: ${log_root}"

for test in "${tests[@]}"; do
  test_log_dir="${log_root}/${test}"
  mkdir -p "$test_log_dir"
  log="${test_log_dir}/stdout.log"
  echo "Starting ${test}, stdout: ${log}" | tee -a "${log_root}/launcher.log"
  {
    echo "test=${test}"
    echo "start=$(date --iso-8601=seconds)"
    echo "cmd=python3 scripts/poly/demo.py ${test}"
    echo
    python3 scripts/poly/demo.py "$test"
    echo
    echo "end=$(date --iso-8601=seconds)"
  } >"$log" 2>&1 &
  pids+=("$!")
  sleep "$DELAY"
done

rc=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    rc=1
  fi
done

echo "Done, rc=${rc}" | tee -a "${log_root}/launcher.log"
exit "$rc"
