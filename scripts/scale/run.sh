#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

cfg="${1:?usage: ./scripts/scale/run.sh PolyChipC1Config [workload] [bitstream]}"
scale_config="${SCALE_CONFIG:-scripts/scale/config/config.yaml}"

case "$cfg" in
  PolyChipC1Config|PolyChipC2Config|PolyChipC3Config|PolyChipC4Config)
    full_cfg="examples.poly.${cfg}"
    ;;
  *)
    echo "unknown scale config: $cfg" >&2
    exit 1
    ;;
esac

if [[ ! -f "$scale_config" ]]; then
  echo "missing scale config: ${scale_config}" >&2
  exit 1
fi

yaml_get_top() {
  local key="$1"
  awk -v key="${key}:" '$1 == key { print $2; exit }' "$scale_config"
}

yaml_get_section() {
  local section="$1"
  local key="$2"
  awk -v section="${section}:" -v key="${key}:" '
    $1 == section { in_section = 1; next }
    in_section && /^[^[:space:]]/ { in_section = 0 }
    in_section && $1 == key { print $2; exit }
  ' "$scale_config"
}

output_root="$(yaml_get_top output_root)"
image="${2:-$(yaml_get_section workload image)}"
bitstream="${3:-$(yaml_get_section bitstreams "$cfg")}"
fpga_location="$(yaml_get_section fpga location)"
multi_fpga="$(yaml_get_section fpga multi_fpga)"

if [[ "$image" != *_singlecore-baremetal ]]; then
  image="${image}_singlecore-baremetal"
fi
workload="${image%_singlecore-baremetal}"

if [[ -z "$output_root" ]]; then
  echo "missing output_root in ${scale_config}" >&2
  exit 1
fi
if [[ -z "$image" ]]; then
  echo "missing workload.image in ${scale_config}" >&2
  exit 1
fi
if [[ -z "$bitstream" ]]; then
  echo "missing bitstreams.${cfg} in ${scale_config}" >&2
  exit 1
fi
case "$multi_fpga" in
  true|false) ;;
  *)
    echo "invalid fpga.multi_fpga in ${scale_config}: ${multi_fpga}" >&2
    exit 1
    ;;
esac
if [[ "$multi_fpga" == false && -z "$fpga_location" ]]; then
  echo "missing fpga.location in ${scale_config} when fpga.multi_fpga is false" >&2
  exit 1
fi

out="${output_root}/${cfg}"
run="${out}/${workload}"
build="$(dirname "$(dirname "$bitstream")")"
log="${run}/sim"
fpga="${out}/fpga"
func="${run}/functional"
perf="${run}/performance"

if [[ ! -f "$bitstream" ]]; then
  echo "missing bitstream: ${bitstream}" >&2
  echo "configured in: ${scale_config}" >&2
  exit 1
fi
bitstream="$(realpath "$bitstream")"
build="$(realpath "$build")"

image_hex="$(find bb-tests/output -type f -name "${image}.hex" -print -quit)"
if [[ -z "$image_hex" ]]; then
  echo "missing workload hex: ${image}.hex" >&2
  echo "searched under: bb-tests/output" >&2
  echo "build/convert it explicitly before running scale simulation" >&2
  exit 1
fi

if ! command -v bbdev >/dev/null 2>&1; then
  echo "missing command: bbdev" >&2
  echo "enter nix develop first, or run: nix develop -c ./scripts/scale/run.sh ${cfg}" >&2
  exit 1
fi

mkdir -p "$run" "$log" "$fpga" "$func" "$perf"
run="$(realpath "$run")"
log="$(realpath "$log")"
fpga="$(realpath "$fpga")"
func="$(realpath "$func")"
perf="$(realpath "$perf")"

rm -f \
  "${log}/uart.log" \
  "${log}/uart_hart_0.log" \
  "${func}/uart.log" \
  "${func}/uart_hart_0.log" \
  "${func}/status.txt" \
  "${perf}/embench.csv" \
  "${perf}/coremark.csv" \
  "${perf}/dnntest.csv" \
  "${perf}/summary.txt"

echo "[scale run] config=${full_cfg}"
echo "[scale run] scale_config=${scale_config}"
echo "[scale run] image=${image}"
echo "[scale run] image_hex=${image_hex}"
echo "[scale run] bitstream=${bitstream}"
echo "[scale run] build=${build}"
echo "[scale run] log=${log}"
echo "[scale run] multi_fpga=${multi_fpga}"
if [[ -n "$fpga_location" ]]; then
  echo "[scale run] fpga_location=${fpga_location}"
fi

args="--config ${full_cfg} --image ${image} --bitstream ${bitstream} --build-dir ${build} --log-dir ${log}"
if [[ "$multi_fpga" == true ]]; then
  args="${args} --multi-fpga"
else
  args="${args} --fpga-location ${fpga_location}"
fi

bbdev bebop-p2e --runworkload "$args"

cat > "${run}/run.env" <<EOF
config=${full_cfg}
scale_config=${scale_config}
image=${image}
image_hex=${image_hex}
bitstream=${bitstream}
build=${build}
log=${log}
fpga=${fpga}
multi_fpga=${multi_fpga}
fpga_location=${fpga_location}
EOF

ln -sfn "$bitstream" "${fpga}/bitstream.bit"
ln -sfn "$build" "${fpga}/build"
ln -sfn "$(realpath "$image_hex")" "${run}/workload.hex"

for f in main.tcl sim_exit.flag vdbg.log tb_bebop.log tb_SimCtl.log tb_rbsrv.log; do
  if [[ -f "${build}/${f}" ]]; then
    cp "${build}/${f}" "${fpga}/${f}"
  fi
done
if [[ -f "${build}/vvacDir/runtimeDir/rtcfg" ]]; then
  cp "${build}/vvacDir/runtimeDir/rtcfg" "${fpga}/rtcfg"
fi
if [[ -f "${log}/console.sock.path" ]]; then
  cp "${log}/console.sock.path" "${run}/console.sock.path"
fi

if [[ ! -f "${log}/uart.log" ]]; then
  echo "missing simulation uart log: ${log}/uart.log" >&2
  exit 1
fi

cp "${log}/uart.log" "${func}/uart.log"
if [[ -f "${log}/uart_hart_0.log" ]]; then
  cp "${log}/uart_hart_0.log" "${func}/uart_hart_0.log"
fi

if grep -qE "FAIL|failures=[1-9][0-9]*|Incorrect operation|ERROR" "${func}/uart.log"; then
  status=FAIL
else
  status=PASS
fi
cat > "${func}/status.txt" <<EOF
status=${status}
uart_log=${func}/uart.log
EOF

if grep -q '^embench ' "${log}/uart.log"; then
  awk '
    BEGIN { print "benchmark,cycles,result,status" }
    /^embench / {
      name = $2
      cycles = ""
      result = ""
      status = $NF
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^cycles=/) {
          cycles = $i
          sub(/^cycles=/, "", cycles)
        }
        if ($i ~ /^result=/) {
          result = $i
          sub(/^result=/, "", result)
        }
      }
      print name "," cycles "," result "," status
    }
  ' "${log}/uart.log" > "${perf}/embench.csv"
  grep '^Embench top total cycles=' "${log}/uart.log" > "${perf}/summary.txt"
elif grep -qE '^Total ticks|^Iterations|^Correct operation validated' "${log}/uart.log"; then
  awk -F: '
    BEGIN { print "metric,value" }
    /^Total ticks/ { gsub(/^[ \t]+/, "", $2); print "total_ticks," $2 }
    /^Iterations/ { gsub(/^[ \t]+/, "", $2); print "iterations," $2 }
    /^Correct operation validated/ { print "validated,1" }
  ' "${log}/uart.log" > "${perf}/coremark.csv"
  cp "${log}/uart.log" "${perf}/summary.txt"
elif grep -q '^DNNTest .* cycles=' "${log}/uart.log"; then
  awk '
    BEGIN { print "model,cycles,class,status" }
    /^DNNTest .* cycles=/ {
      model = $2
      cycles = ""
      cls = ""
      status = $NF
      for (i = 1; i <= NF; i++) {
        if ($i ~ /^cycles=/) {
          cycles = $i
          sub(/^cycles=/, "", cycles)
        }
        if ($i ~ /^class=/) {
          cls = $i
          sub(/^class=/, "", cls)
        }
      }
      if (model == "total") {
        failures = status
        sub(/^failures=/, "", failures)
        status = failures == "0" ? "PASS" : "FAIL"
      }
      print model "," cycles "," cls "," status
    }
  ' "${log}/uart.log" > "${perf}/dnntest.csv"
  grep '^DNNTest total cycles=' "${log}/uart.log" > "${perf}/summary.txt"
else
  echo "missing known performance markers in ${log}/uart.log" >&2
  exit 1
fi

echo "[scale run] simulation log=${log}"
echo "[scale run] fpga runtime=${fpga}"
echo "[scale run] functional result=${func}"
echo "[scale run] performance result=${perf}"
