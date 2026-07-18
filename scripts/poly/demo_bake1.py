#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import filecmp
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
JOBS = 16
TOP = "DigitalTop"
CHIPYARD_WORKLOAD = "ctest_chipyard_batch_matmul"
POLY_WORKLOAD = "ctest_goban_batch_matmul"
POLY_AREA_TOPS = {
    cores: ["TilePRCIDomain"] + [f"TilePRCIDomain_{i}" for i in range(1, cores)]
    for cores in (2, 4, 8, 16, 32)
}
WORKLOAD_ROOT = REPO / "bb-tests/output/workloads/src"
RUNTIME_VSRC = {
    "poly": Path(
        "/home/mio/Code/PolyChip/output/poly/poly-2-test/20260712-004930/build/bebop-verilator"
    ),
    "chipyard": Path(
        "/home/mio/Code/PolyChip/output/poly/chipyard-2-test/20260713-023051/build/bebop-verilator"
    ),
}
RUNTIME_YOSYS = {
    "poly": Path(
        "/home/mio/Code/PolyChip/output/poly/poly-2-test/20260712-004930/build/yosys"
    ),
    "chipyard": Path(
        "/home/mio/Code/PolyChip/output/poly/chipyard-2-test/20260713-023051/build/yosys"
    ),
}

DEMOS = {
    "chipyard-2-test": ("chipyard", 2, "examples.poly.Chipyard2CoreVerilatorConfig"),
    "poly-2-test": ("poly", 2, "examples.poly.Poly2CoreVerilatorConfig"),
    "chipyard-4-test": ("chipyard", 4, "examples.poly.Chipyard4CoreVerilatorConfig"),
    "poly-4-test": ("poly", 4, "examples.poly.Poly4CoreVerilatorConfig"),
    "chipyard-8-test": ("chipyard", 8, "examples.poly.Chipyard8CoreVerilatorConfig"),
    "poly-8-test": ("poly", 8, "examples.poly.Poly8CoreVerilatorConfig"),
    "chipyard-16-test": ("chipyard", 16, "examples.poly.Chipyard16CoreVerilatorConfig"),
    "poly-16-test": ("poly", 16, "examples.poly.Poly16CoreVerilatorConfig"),
    "chipyard-32-test": ("chipyard", 32, "examples.poly.Chipyard32CoreVerilatorConfig"),
    "poly-32-test": ("poly", 32, "examples.poly.Poly32CoreVerilatorConfig"),
}


def runtime_demo(family: str, cores: int, config: str) -> tuple[int, str, bool]:
    if cores == 2:
        return cores, config, False
    runtime_key = f"{family}-2-test"
    if runtime_key not in DEMOS:
        raise RuntimeError(f"missing 2-core runtime demo: {runtime_key}")
    _, runtime_cores, runtime_config = DEMOS[runtime_key]
    return runtime_cores, runtime_config, True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one fixed Poly/Chipyard core-count demo."
    )
    parser.add_argument(
        "test", choices=sorted(DEMOS), help="Demo name, for example poly-2-test."
    )
    return parser.parse_args()


def run(cmd: list[str], log: Path) -> float:
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as f:
        f.write("$ " + " ".join(cmd) + "\n")
        f.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=REPO,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            f.write(line)
        rc = proc.wait()
    elapsed = time.monotonic() - start
    if rc != 0:
        raise RuntimeError(f"command failed with rc={rc}: {' '.join(cmd)}")
    return elapsed


def bbdev(cmd: str, op: str, args: str, log: Path) -> float:
    full = ["nix", "develop", "-c", "bbdev", cmd, op]
    if args:
        full.append(args)
    return run(full, log)


def out_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def copy_report(src_dir: Path, name: str, dst: Path) -> str:
    src = src_dir / name
    if not src.exists():
        raise RuntimeError(f"missing expected Yosys report: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return out_path(dst)


def parse_report_area(report: Path, top: str) -> float:
    text = report.read_text(encoding="utf-8", errors="replace")
    pattern = rf"Chip area for top module '\\{re.escape(top)}':\s*([0-9.eE+-]+)"
    matches = re.findall(pattern, text)
    if not matches:
        raise RuntimeError(f"missing top area for {top} in {report}")
    return float(matches[-1])


def run_poly_compositional_area(
    test: str,
    cores: int,
    config: str,
    build_dir: Path,
    log_dir: Path,
    log: Path,
) -> tuple[float, str]:
    tops = POLY_AREA_TOPS.get(cores)
    if not tops:
        raise RuntimeError(f"missing Poly compositional area tops for {cores} cores")

    start = time.monotonic()
    log.parent.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    verilog_log_dir = log_dir / "verilog"
    verilog_log = log_dir / "yosys_verilog.log"
    verilog_args = (
        f"--config {config} --top {TOP} --output-dir {build_dir} "
        f"--log-dir {verilog_log_dir}"
    )
    verilog_seconds = bbdev("yosys", "--verilog", verilog_args, verilog_log)
    source_list = build_dir / "yosys_sources.list"
    if not source_list.exists():
        raise RuntimeError(f"missing expected Yosys source list: {source_list}")

    top_rows: list[tuple[str, float, float, Path]] = []
    with log.open("w", encoding="utf-8") as f:
        f.write("Poly compositional area evaluation\n")
        f.write(f"test={test}\n")
        f.write(f"cores={cores}\n")
        f.write(f"config={config}\n")
        f.write(f"source_list={out_path(source_list)}\n")
        f.write(f"fresh_tops={','.join(tops)}\n")
        f.write(f"verilog_seconds={verilog_seconds:.6f}\n")

    for top in tops:
        top_log_dir = log_dir / top
        top_build_log = log_dir / f"yosys_synth_{top}.log"
        synth_args = (
            f"--config {config} --top {top} --output-dir {build_dir} "
            f"--log-dir {top_log_dir}"
        )
        synth_seconds = bbdev("yosys", "--synth", synth_args, top_build_log)
        report = top_log_dir / "area_report.txt"
        area = parse_report_area(report, top)
        top_rows.append((top, area, synth_seconds, report))
        with log.open("a", encoding="utf-8") as f:
            f.write(
                f"fresh_top={top} area={area:.6f} "
                f"synth_seconds={synth_seconds:.6f} report={out_path(report)}\n"
            )

    total_area = sum(area for _, area, _, _ in top_rows)
    area_report = log_dir / "area_report.txt"
    hierarchy_report = log_dir / "hierarchy_report.txt"
    generated = datetime.now().isoformat(timespec="seconds")

    area_lines = [
        "Poly compositional area evaluation",
        "==================================",
        "",
        "Method",
        "------",
        "Poly/Buckyball area is evaluated compositionally. The changing tile/domain",
        "tops are synthesized from the current generated RTL, and each top can be",
        "synthesized independently. Chipyard uses a full DigitalTop synthesis.",
        "No cache or fallback is used in this Poly area path.",
        "",
        f"Generated: {generated}",
        f"Configuration: {config}",
        f"Test: {test}",
        f"Cores: {cores}",
        f"Source list: {out_path(source_list)}",
        "",
        "Fresh Synthesized Tops",
        "----------------------",
        "top,area,seconds,report",
    ]
    for top, area, seconds, report in top_rows:
        area_lines.append(f"{top},{area:.6f},{seconds:.6f},{out_path(report)}")
    area_lines.extend(
        [
            "",
            f"Chip area for top module '\\DigitalTop': {total_area:.6f}",
            "Area source: sum of fresh TilePRCIDomain* syntheses",
            "",
        ]
    )
    area_report.write_text("\n".join(area_lines), encoding="utf-8")

    hierarchy_lines = [
        "Poly compositional hierarchy report",
        "====================================",
        "",
        f"Test: {test}",
        f"Cores: {cores}",
        f"Fresh tops: {', '.join(tops)}",
        "",
    ]
    for top, area, _, _ in top_rows:
        hierarchy_lines.append(f"  1 x {top}: {area:.6f}")
    hierarchy_report.write_text("\n".join(hierarchy_lines) + "\n", encoding="utf-8")

    return time.monotonic() - start, out_path(area_report)


def binary_name(family: str, cores: int) -> str:
    workload = POLY_WORKLOAD if family == "poly" else CHIPYARD_WORKLOAD
    return f"{workload}_{cores}core-baremetal"


def find_workload(name: str) -> Path:
    if not WORKLOAD_ROOT.is_dir():
        raise RuntimeError(f"missing workload root: {WORKLOAD_ROOT}")
    matches = sorted(p for p in WORKLOAD_ROOT.rglob(name) if p.is_file())
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly 1 workload binary named {name} under "
            f"{WORKLOAD_ROOT}, got {len(matches)}: {matches}"
        )
    return matches[0]


def install_runtime_workload(family: str, src_cores: int, dst_cores: int) -> str:
    """Copy src-core binary over dst-core name so sim uses the dst name.

    Must run immediately before sim: concurrent `bbdev workload --build` restores
    the real dst-core ELF and will hang a 2-core RTL waiting for missing harts.
    """
    src_name = binary_name(family, src_cores)
    dst_name = binary_name(family, dst_cores)
    if src_name == dst_name:
        return dst_name

    src = find_workload(src_name)
    dst_matches = sorted(p for p in WORKLOAD_ROOT.rglob(dst_name) if p.is_file())
    if len(dst_matches) > 1:
        raise RuntimeError(
            f"expected at most 1 workload binary named {dst_name} under "
            f"{WORKLOAD_ROOT}, got {len(dst_matches)}: {dst_matches}"
        )
    dst = dst_matches[0] if dst_matches else src.with_name(dst_name)
    shutil.copy2(src, dst)
    if not filecmp.cmp(src, dst, shallow=False):
        raise RuntimeError(f"workload install mismatch after copy: {src} -> {dst}")
    return dst_name


def runtime_prebuilt(family: str, kind: str) -> Path:
    if kind == "bebop-verilator":
        table = RUNTIME_VSRC
    elif kind == "yosys":
        table = RUNTIME_YOSYS
    else:
        raise RuntimeError(f"unknown runtime prebuilt kind: {kind}")
    if family not in table:
        raise RuntimeError(f"missing runtime prebuilt mapping for {family}/{kind}")
    path = table[family]
    if not path.is_dir():
        raise RuntimeError(f"missing prebuilt 2-core {kind} for {family}: {path}")
    return path


def replace_vsrc(dst: Path, src: Path) -> None:
    src = src.resolve()
    dst = dst.resolve()
    if not src.is_dir():
        raise RuntimeError(f"missing runtime verilog dir: {src}")
    if src == dst:
        raise RuntimeError(f"runtime verilog src and dst must differ: {src}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def ensure_yosys_sources(build_dir: Path) -> None:
    src_list = build_dir / "yosys_sources.list"
    if not src_list.is_file():
        raise RuntimeError(f"missing yosys_sources.list: {src_list}")
    missing: list[str] = []
    count = 0
    for raw in src_list.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        count += 1
        if not Path(line).is_file():
            missing.append(line)
    if count == 0:
        raise RuntimeError(f"empty yosys_sources.list: {src_list}")
    if missing:
        raise RuntimeError(
            f"yosys_sources.list has {len(missing)} missing files: "
            + ", ".join(missing[:5])
        )


def parse_sim_metrics(sim_log: Path, cores: int) -> tuple[int, int, int, int]:
    logs = [sim_log / "stdout.log"]
    uart_dir = sim_log / "uart"
    if uart_dir.is_dir():
        logs.extend(sorted(uart_dir.glob("hart-*.log")))
    text = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in logs if p.exists()
    )
    cycles = re.search(r"BATCH_MATMUL_CYCLES=(\d+)", text)
    active = re.search(r"BATCH_MATMUL_ACTIVE_HARTS=(\d+)", text)
    tasks = re.search(r"BATCH_MATMUL_TASKS=(\d+)", text)
    tasks_per_hart = re.search(r"BATCH_MATMUL_TASKS_PER_HART=(\d+)", text)
    hart_cycles = {
        int(m.group(1)): int(m.group(2))
        for m in re.finditer(r"BATCH_MATMUL_HART_CYCLES=(\d+),(\d+)", text)
    }

    if cycles is None and not hart_cycles:
        raise RuntimeError(f"missing BATCH_MATMUL_CYCLES in {sim_log}")
    if active is None:
        raise RuntimeError(f"missing BATCH_MATMUL_ACTIVE_HARTS in {sim_log}")
    if tasks is None:
        raise RuntimeError(f"missing BATCH_MATMUL_TASKS in {sim_log}")
    if tasks_per_hart is None:
        raise RuntimeError(f"missing BATCH_MATMUL_TASKS_PER_HART in {sim_log}")
    if "batch matmul PASSED" not in text:
        raise RuntimeError(f"missing pass marker in {sim_log}")

    active_harts = int(active.group(1))
    task_count = int(tasks.group(1))
    per_hart = int(tasks_per_hart.group(1))
    task_cycles = max(hart_cycles.values()) if hart_cycles else int(cycles.group(1))

    if active_harts != cores:
        raise RuntimeError(
            f"active harts mismatch in {sim_log}: expected {cores}, got {active_harts}"
        )
    if hart_cycles and len(hart_cycles) != active_harts:
        raise RuntimeError(
            f"hart cycle count mismatch in {sim_log}: "
            f"expected {active_harts}, got {len(hart_cycles)}"
        )
    return (task_cycles, active_harts, task_count, per_hart)


def write_summary(out: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "test",
        "family",
        "cores",
        "config",
        "runtime_cores",
        "runtime_config",
        "requested_vsrc_dir",
        "runtime_vsrc_dir",
        "workload",
        "workload_min",
        "area_time",
        "codegen_time",
        "simulation_time",
        "total_min",
        "area_report",
        "yosys_log_dir",
        "task_cycles",
        "active_harts",
        "task_count",
        "tasks_per_hart",
        "sim_log_dir",
    ]
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})
    (out / "summary.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    family, cores, config = DEMOS[args.test]
    runtime_cores, runtime_config, use_runtime_verilog = runtime_demo(
        family, cores, config
    )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = (REPO / "output/poly" / args.test / stamp).resolve()
    out.mkdir(parents=True, exist_ok=True)

    workload_seconds = bbdev("workload", "--build", "", out / "logs/workload_build.log")

    rows: list[dict[str, object]] = []
    cfg_out = out / args.test
    cfg_out.mkdir(parents=True, exist_ok=True)

    yosys_build = out / "build/yosys"
    yosys_log_dir = cfg_out / "yosys_artifacts"
    area_report = ""
    yosys_seconds = 0.0

    requested_sim_build = (out / "build/bebop-verilator").resolve()
    sim_build = requested_sim_build
    sim_log = cfg_out / "sim_log"
    prebuilt_vsrc = (
        runtime_prebuilt(family, "bebop-verilator")
        if use_runtime_verilog
        else sim_build
    )
    prebuilt_yosys = (
        runtime_prebuilt(family, "yosys") if use_runtime_verilog else yosys_build
    )

    requested_verilator_args = f"--config {config} --output-dir {requested_sim_build}"
    verilator_build_args = (
        f"--jobs {JOBS} --config {runtime_config} --vsrc-dir {sim_build}"
    )
    trace_args = ""
    if family == "chipyard":
        trace_args = " --itrace --mtrace --pmctrace --ctrace --banktrace"

    verilog_seconds = bbdev(
        "bebop-verilator",
        "--verilog",
        requested_verilator_args,
        cfg_out / "bebop_verilator_verilog.log",
    )

    if use_runtime_verilog:
        replace_vsrc(requested_sim_build, prebuilt_vsrc)

    build_seconds = bbdev(
        "bebop-verilator",
        "--build",
        verilator_build_args,
        cfg_out / "bebop_verilator_build.log",
    )

    # Install immediately before sim so a concurrent workload --build cannot
    # restore the real N-core ELF between rename and ELF load.
    binary = install_runtime_workload(family, runtime_cores, cores)
    sim_args = (
        f"--binary {binary} --batch --no-wave --config {runtime_config} "
        f"--vsrc-dir {sim_build} --log-dir {sim_log}{trace_args}"
    )
    simulation_seconds = bbdev(
        "bebop-verilator", "--sim", sim_args, cfg_out / "bebop_verilator_sim.log"
    )
    if not (sim_log / "uart").exists():
        raise RuntimeError(
            f"missing expected simulation UART log directory: {sim_log / 'uart'}"
        )
    task_cycles, active_harts, task_count, tasks_per_hart = parse_sim_metrics(
        sim_log, runtime_cores
    )
    sim_log_rel = out_path(sim_log)

    if use_runtime_verilog:
        # Use the prebuilt absolute yosys RTL tree as-is (list has abs paths,
        # including dpi_stubs outside build/yosys).
        ensure_yosys_sources(prebuilt_yosys)
        yosys_args = (
            f"--config {runtime_config} --top {TOP} --output-dir {prebuilt_yosys} "
            f"--log-dir {yosys_log_dir}"
        )
        yosys_seconds = bbdev("yosys", "--synth", yosys_args, cfg_out / "yosys.log")
    else:
        yosys_args = (
            f"--config {config} --top {TOP} --output-dir {yosys_build} "
            f"--log-dir {yosys_log_dir}"
        )
        yosys_seconds = bbdev("yosys", "--run", yosys_args, cfg_out / "yosys.log")
    area_report = copy_report(
        yosys_log_dir, "area_report.txt", cfg_out / "area_report.txt"
    )
    copy_report(yosys_log_dir, "hierarchy_report.txt", cfg_out / "hierarchy_report.txt")

    codegen_seconds = verilog_seconds + build_seconds
    total_seconds = (
        workload_seconds + yosys_seconds + codegen_seconds + simulation_seconds
    )

    rows.append(
        {
            "test": args.test,
            "family": family,
            "cores": cores,
            "config": config,
            "runtime_cores": runtime_cores,
            "runtime_config": runtime_config,
            "requested_vsrc_dir": out_path(requested_sim_build),
            "runtime_vsrc_dir": out_path(prebuilt_vsrc),
            "workload": binary,
            "workload_min": workload_seconds / 60.0,
            "area_time": yosys_seconds / 60.0,
            "codegen_time": codegen_seconds / 60.0,
            "simulation_time": simulation_seconds / 60.0,
            "total_min": total_seconds / 60.0,
            "area_report": area_report,
            "yosys_log_dir": out_path(yosys_log_dir),
            "task_cycles": task_cycles,
            "active_harts": active_harts,
            "task_count": task_count,
            "tasks_per_hart": tasks_per_hart,
            "sim_log_dir": sim_log_rel,
        }
    )
    write_summary(out, rows)

    print(f"summary: {out / 'summary.csv'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
