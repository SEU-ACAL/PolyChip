#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DELAY="${DELAY:-30}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"
demo_args=()
if [[ "${SKIP_AREA:-0}" == "1" ]]; then
  demo_args+=(--skip-area)
fi

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
    echo "cmd=python3 scripts/poly/demo.py ${test} ${demo_args[*]}"
    echo
    python3 scripts/poly/demo.py "$test" "${demo_args[@]}"
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
python3 - "$log_root" <<'PY' | tee -a "${log_root}/launcher.log"
import json
import re
import statistics
import sys
from pathlib import Path

log_root = Path(sys.argv[1])
summary_re = re.compile(r"^summary:\s*(.+summary\.csv)\s*$", re.MULTILINE)
rows = []

for stdout_log in sorted(log_root.glob("*/stdout.log")):
    text = stdout_log.read_text(encoding="utf-8", errors="replace")
    match = summary_re.search(text)
    if not match:
        print(f"Missing summary path in {stdout_log}")
        continue
    summary_json = Path(match.group(1)).with_suffix(".json")
    if not summary_json.exists():
        print(f"Missing summary json: {summary_json}")
        continue
    data = json.loads(summary_json.read_text(encoding="utf-8"))
    rows.extend(data)

print()
print("Timing summary (minutes):")
if not rows:
    print("  no completed summaries found")
else:
    for row in sorted(rows, key=lambda r: (int(r.get("cores", 0)), str(r.get("family", "")))):
        print(
            "  {test}: total={total:.3f}, workload={workload:.3f}, area={area:.3f}, "
            "codegen={codegen:.3f}, simulation={simulation:.3f}".format(
                test=row.get("test", ""),
                total=float(row.get("total_min", 0.0)),
                workload=float(row.get("workload_min", 0.0)),
                area=float(row.get("area_time", 0.0)),
                codegen=float(row.get("codegen_time", 0.0)),
                simulation=float(row.get("simulation_time", 0.0)),
            )
        )

    by_family = {}
    for row in rows:
        by_family.setdefault(row.get("family"), []).append(float(row.get("total_min", 0.0)))

    poly = by_family.get("poly", [])
    chipyard = by_family.get("chipyard", [])
    if poly and chipyard:
        poly_avg = statistics.fmean(poly)
        chipyard_avg = statistics.fmean(chipyard)
        faster_pct = ((chipyard_avg - poly_avg) / chipyard_avg * 100.0) if chipyard_avg else 0.0
        print()
        print(f"poly average total_min: {poly_avg:.3f}")
        print(f"chipyard average total_min: {chipyard_avg:.3f}")
        print(f"poly is faster by: {faster_pct:.2f}%")
    else:
        print()
        print("poly/chipyard average unavailable: missing one family")
PY
exit "$rc"
