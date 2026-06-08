#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
JOBS = 16
TOP = "DigitalTop"
CHIPYARD_WORKLOAD = "ctest_chipyard_batch_matmul"
POLY_WORKLOAD = "ctest_goban_batch_matmul"

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one fixed Poly/Chipyard core-count demo."
    )
    parser.add_argument(
        "test", choices=sorted(DEMOS), help="Demo name, for example poly-2-test."
    )
    parser.add_argument(
        "--skip-area", action="store_true", help="Skip Yosys area synthesis."
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


def binary_name(family: str, cores: int) -> str:
    workload = POLY_WORKLOAD if family == "poly" else CHIPYARD_WORKLOAD
    return f"{workload}_{cores}core-baremetal"


def latest_sim_log(binary: str, since: float) -> Path:
    root = REPO / "arch/log"
    if not root.exists():
        raise RuntimeError(f"missing simulation log root: {root}")
    dirs = [
        p
        for p in root.iterdir()
        if p.is_dir() and p.name.endswith(f"-{binary}") and p.stat().st_mtime >= since
    ]
    if not dirs:
        raise RuntimeError(f"no simulation log found for {binary}")
    return max(dirs, key=lambda p: p.stat().st_mtime)


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
    if cycles is None:
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
    if active_harts != cores:
        raise RuntimeError(
            f"active harts mismatch in {stdout_log}: expected {cores}, got {active_harts}"
        )
    return (
        int(cycles.group(1)),
        active_harts,
        int(tasks.group(1)),
        int(tasks_per_hart.group(1)),
    )


def write_summary(out: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "test",
        "family",
        "cores",
        "config",
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
    binary = binary_name(family, cores)
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
    if not args.skip_area:
        yosys_args = (
            f"--config {config} --top {TOP} --output-dir {yosys_build} "
            f"--log-dir {yosys_log_dir}"
        )
        yosys_seconds = bbdev("yosys", "--run", yosys_args, cfg_out / "yosys.log")
        area_report = copy_report(
            yosys_log_dir, "area_report.txt", cfg_out / "area_report.txt"
        )
        copy_report(
            yosys_log_dir, "hierarchy_report.txt", cfg_out / "hierarchy_report.txt"
        )

    sim_build = out / "build/bebop-verilator"
    sim_log = cfg_out / "sim_log"
    verilator_common_args = f"--config {config} --output-dir {sim_build}"
    verilator_build_args = f"--jobs {JOBS} --config {config} --vsrc-dir {sim_build}"
    sim_args = (
        f"--binary {binary} --batch --no-wave --config {config} "
        f"--vsrc-dir {sim_build} --log-dir {sim_log}"
    )
    since = time.time()
    verilog_seconds = bbdev(
        "bebop-verilator",
        "--verilog",
        verilator_common_args,
        cfg_out / "bebop_verilator_verilog.log",
    )
    build_seconds = bbdev(
        "bebop-verilator",
        "--build",
        verilator_build_args,
        cfg_out / "bebop_verilator_build.log",
    )
    simulation_seconds = bbdev(
        "bebop-verilator", "--sim", sim_args, cfg_out / "bebop_verilator_sim.log"
    )
    if not (sim_log / "uart").exists():
        fallback_sim_log = latest_sim_log(binary, since)
        shutil.copytree(fallback_sim_log, sim_log, dirs_exist_ok=True)
    task_cycles, active_harts, task_count, tasks_per_hart = parse_sim_metrics(
        sim_log, cores
    )
    sim_log_rel = out_path(sim_log)
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
            "workload": binary,
            "workload_min": workload_seconds / 60.0,
            "area_time": yosys_seconds / 60.0,
            "codegen_time": codegen_seconds / 60.0,
            "simulation_time": simulation_seconds / 60.0,
            "total_min": total_seconds / 60.0,
            "area_report": area_report,
            "yosys_log_dir": out_path(yosys_log_dir) if not args.skip_area else "",
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
