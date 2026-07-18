#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DELAY="${DELAY:-30}"
RUN_ID="$(date +%Y%m%d-%H%M%S)"

cores=(2 4 8 16 32)

cd "$ROOT"
log_root="output/poly/launcher-logs/${RUN_ID}"
mkdir -p "$log_root"
echo "Launcher log dir: ${log_root}"

rc=0
for core in "${cores[@]}"; do
  group_tests=(
    "chipyard-${core}-test"
    "poly-${core}-test"
  )
  group_pids=()

  echo "Starting ${core}-core group" | tee -a "${log_root}/launcher.log"
  for test in "${group_tests[@]}"; do
    test_log_dir="${log_root}/${test}"
    mkdir -p "$test_log_dir"
    log="${test_log_dir}/stdout.log"
    echo "Starting ${test}, stdout: ${log}" | tee -a "${log_root}/launcher.log"
    {
      echo "test=${test}"
      echo "group=${core}-core"
      echo "start=$(date --iso-8601=seconds)"
      echo "cmd=python3 scripts/poly/demo.py ${test}"
      echo
      python3 scripts/poly/demo.py "$test"
      echo
      echo "end=$(date --iso-8601=seconds)"
    } >"$log" 2>&1 &
    group_pids+=("$!")
    sleep "$DELAY"
  done

  group_rc=0
  for pid in "${group_pids[@]}"; do
    if ! wait "$pid"; then
      group_rc=1
    fi
  done

  echo "Finished ${core}-core group, rc=${group_rc}" | tee -a "${log_root}/launcher.log"
  if [[ "$group_rc" != "0" ]]; then
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

    by_pair = {}
    for row in rows:
        by_pair[(int(row.get("cores", 0)), row.get("family"))] = row

    print()
    print("Per-core comparisons:")
    for core in [2, 4, 8, 16, 32]:
        chip = by_pair.get((core, "chipyard"))
        poly_row = by_pair.get((core, "poly"))
        if not chip or not poly_row:
            print(f"  {core}-core comparison unavailable")
            continue
        chip_total = float(chip.get("total_min", 0.0))
        poly_total = float(poly_row.get("total_min", 0.0))
        chip_area = float(chip.get("area_time", 0.0))
        poly_area = float(poly_row.get("area_time", 0.0))
        total_faster = ((chip_total - poly_total) / chip_total * 100.0) if chip_total else 0.0
        area_faster = ((chip_area - poly_area) / chip_area * 100.0) if chip_area else 0.0
        print(
            f"  {core}-core: chipyard total={chip_total:.3f}, poly total={poly_total:.3f}, "
            f"poly total faster by={total_faster:.2f}%"
        )
        print(
            f"           chipyard area={chip_area:.3f}, poly area={poly_area:.3f}, "
            f"poly area faster by={area_faster:.2f}%"
        )

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
