#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

cfg="${1:?usage: ./scripts/scale/run.sh PolyChipC1Config}"
scale_config="${SCALE_CONFIG:-scripts/scale/config/config.yaml}"

case "$cfg" in
  PolyChipC1Config|PolyChipC2Config|PolyChipC3Config|PolyChipC4Config) ;;
  *)
    echo "unknown scale config: $cfg" >&2
    exit 1
    ;;
esac

full_cfg="examples.poly.${cfg}"
test -f "$scale_config"

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
build="$(dirname "$(dirname "$bitstream")")"
log="${out}/sim"

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

mkdir -p "$log"
log="$(realpath "$log")"

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

echo "[scale run] simulation log=${log}"
echo "[scale run] performance result=${log}"
