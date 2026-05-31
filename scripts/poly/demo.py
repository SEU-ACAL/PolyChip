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
BINARY = "ctest_batch_matmul_singlecore-baremetal"

DEMOS = {
    "chipyard-2-test": ("chipyard", 2, "examples.poly.Chipyard2CoreVerilatorConfig"),
    "chipyard-4-test": ("chipyard", 4, "examples.poly.Chipyard4CoreVerilatorConfig"),
    "chipyard-8-test": ("chipyard", 8, "examples.poly.Chipyard8CoreVerilatorConfig"),
    "chipyard-16-test": ("chipyard", 16, "examples.poly.Chipyard16CoreVerilatorConfig"),
    "chipyard-32-test": ("chipyard", 32, "examples.poly.Chipyard32CoreVerilatorConfig"),
    "poly-2-test": ("poly", 2, "examples.poly.Poly2CoreVerilatorConfig"),
    "poly-4-test": ("poly", 4, "examples.poly.Poly4CoreVerilatorConfig"),
    "poly-8-test": ("poly", 8, "examples.poly.Poly8CoreVerilatorConfig"),
    "poly-16-test": ("poly", 16, "examples.poly.Poly16CoreVerilatorConfig"),
    "poly-32-test": ("poly", 32, "examples.poly.Poly32CoreVerilatorConfig"),
}


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


def parse_cycles(stdout_log: Path) -> int:
    text = stdout_log.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"BATCH_MATMUL_CYCLES=(\d+)", text)
    if m is None:
        raise RuntimeError(f"missing BATCH_MATMUL_CYCLES in {stdout_log}")
    if "batch matmul PASSED" not in text:
        raise RuntimeError(f"missing pass marker in {stdout_log}")
    return int(m.group(1))


def write_summary(out: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "test",
        "family",
        "cores",
        "config",
        "workload",
        "area_report",
        "yosys_log_dir",
        "task_cycles",
        "verilator_run_seconds",
        "yosys_seconds",
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
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = (REPO / "output/poly" / args.test / stamp).resolve()
    out.mkdir(parents=True, exist_ok=True)

    bbdev("workload", "--build", "", out / "logs/workload_build.log")

    rows: list[dict[str, object]] = []
    cfg_out = out / args.test
    cfg_out.mkdir(parents=True, exist_ok=True)

    yosys_build = out / "build/yosys"
    yosys_log_dir = cfg_out / "yosys_artifacts"
    yosys_args = (
        f"--config {config} --top {TOP} --output-dir {yosys_build} "
        f"--log-dir {yosys_log_dir}"
    )
    yosys_seconds = bbdev("yosys", "--run", yosys_args, cfg_out / "yosys.log")
    area_report = copy_report(
        yosys_log_dir, "area_report.txt", cfg_out / "area_report.txt"
    )
    copy_report(yosys_log_dir, "hierarchy_report.txt", cfg_out / "hierarchy_report.txt")

    sim_build = out / "build/verilator"
    sim_args = (
        f"--jobs {JOBS} --binary {BINARY} --config {config} "
        f"--output-dir {sim_build} --batch"
    )
    since = time.time()
    verilator_seconds = bbdev(
        "verilator", "--run", sim_args, cfg_out / "verilator_run.log"
    )
    sim_log = latest_sim_log(BINARY, since)
    shutil.copytree(sim_log, cfg_out / "sim_log", dirs_exist_ok=True)
    task_cycles = parse_cycles(cfg_out / "sim_log/stdout.log")
    sim_log_rel = out_path(cfg_out / "sim_log")

    rows.append(
        {
            "test": args.test,
            "family": family,
            "cores": cores,
            "config": config,
            "workload": BINARY,
            "area_report": area_report,
            "yosys_log_dir": out_path(yosys_log_dir),
            "task_cycles": task_cycles,
            "verilator_run_seconds": verilator_seconds,
            "yosys_seconds": yosys_seconds,
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
