#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import tomllib
from pathlib import Path


SYSTEMS = ("chipyard", "poly")
RESET = "\033[0m"
BOLD_CYAN = "\033[1;36m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
FORBIDDEN_KEYS = {
    "runtime_cores",
    "runtime_config",
    "requested_vsrc_dir",
    "runtime_vsrc_dir",
}


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze configured Poly/Chipyard summary.json files."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--time", action="store_true", help="plot total_min bars")
    mode.add_argument("--valid", action="store_true", help="check subtask logs")
    return parser.parse_args()


def required(data: dict, key: str, where: str):
    if key not in data:
        fail(f"{where} missing required key: {key}")
    value = data[key]
    if isinstance(value, (dict, list)):
        fail(f"{where} key {key} must be scalar")
    return value


def parse_system(value, where: str) -> str:
    system = str(value).strip().lower()
    if system not in SYSTEMS:
        fail(f"{where} has invalid system {value!r}; expected {SYSTEMS}")
    return system


def parse_cores(value, where: str) -> int:
    if isinstance(value, bool):
        fail(f"{where} cores must be an integer")
    try:
        cores = int(value)
    except (TypeError, ValueError):
        fail(f"{where} cores must be an integer")
    if cores <= 0:
        fail(f"{where} cores must be positive")
    return cores


def parse_total_min(value, where: str) -> float:
    if isinstance(value, bool):
        fail(f"{where} total_min must be numeric")
    try:
        total_min = float(value)
    except (TypeError, ValueError):
        fail(f"{where} total_min must be numeric")
    if not math.isfinite(total_min) or total_min <= 0:
        fail(f"{where} total_min must be finite and positive")
    return total_min


def load_config(path: Path) -> dict:
    if not path.is_file():
        fail(f"missing config: {path}")
    if path.suffix != ".toml":
        fail(f"config must be TOML: {path}")
    with path.open("rb") as f:
        config = tomllib.load(f)

    inputs = config.get("inputs")
    if not isinstance(inputs, list):
        fail("config must contain 10 [[inputs]] tables")
    if len(inputs) != 10:
        fail(f"expected exactly 10 [[inputs]], got {len(inputs)}")
    for index, item in enumerate(inputs, start=1):
        where = f"config [[inputs]] #{index}"
        if not isinstance(item, dict):
            fail(f"{where} must be a table")
        parse_system(required(item, "system", where), where)
        parse_cores(required(item, "cores", where), where)
        path_value = required(item, "path", where)
        if not isinstance(path_value, str):
            fail(f"{where} path must be a string")
        summary_path = Path(path_value)
        if not summary_path.is_absolute():
            fail(f"{where} path must be absolute: {summary_path}")
        if summary_path.name != "summary.json":
            fail(f"{where} path must point to summary.json: {summary_path}")
    return config


def load_summary(path: Path) -> dict:
    if not path.is_file():
        fail(f"missing summary: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        fail(f"{path} must be a JSON array containing exactly one object")
    row = data[0]
    forbidden = sorted(FORBIDDEN_KEYS.intersection(row))
    if forbidden:
        fail(f"{path} contains forbidden runtime fields: {', '.join(forbidden)}")
    return row


def load_entries(inputs: list[dict]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    seen: set[Path] = set()
    for index, item in enumerate(inputs, start=1):
        where = f"config [[inputs]] #{index}"
        system = parse_system(required(item, "system", where), where)
        cores = parse_cores(required(item, "cores", where), where)
        path = Path(required(item, "path", where))
        if path in seen:
            fail(f"duplicate summary path: {path}")
        seen.add(path)

        row = load_summary(path)
        row_system = parse_system(required(row, "family", str(path)), str(path))
        row_cores = parse_cores(required(row, "cores", str(path)), str(path))
        if row_system != system:
            fail(f"{path} family {row_system!r} does not match config {system!r}")
        if row_cores != cores:
            fail(f"{path} cores {row_cores} does not match config {cores}")

        parse_total_min(required(row, "total_min", str(path)), str(path))
        entries.append(
            {
                "system": system,
                "cores": cores,
                "path": path,
                "row": row,
            }
        )
    return entries


def collect_time(entries: list[dict[str, object]]) -> dict[int, dict[str, float]]:
    by_core: dict[int, dict[str, float]] = {}
    for entry in entries:
        system = str(entry["system"])
        cores = int(entry["cores"])
        path = Path(entry["path"])
        row = entry["row"]
        if not isinstance(row, dict):
            fail(f"{path} row must be a dict")

        values = by_core.setdefault(cores, {})
        if system in values:
            fail(f"duplicate {system} summary for {cores} cores")
        values[system] = parse_total_min(
            required(row, "total_min", str(path)), str(path)
        )

    if len(by_core) != 5:
        fail(f"expected 5 core-count groups, got {len(by_core)}")
    for cores, values in sorted(by_core.items()):
        missing = [system for system in SYSTEMS if system not in values]
        if missing:
            fail(f"{cores} cores missing: {', '.join(missing)}")
    return by_core


def speedup_percent(chipyard: float, poly: float) -> float:
    return (poly - chipyard) / chipyard * 100.0


def plot(by_core: dict[int, dict[str, float]], config: dict, config_path: Path) -> Path:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        fail("matplotlib is required")

    cores = sorted(by_core)
    labels = [str(core) for core in cores] + ["avg"]
    chipyard = [by_core[core]["chipyard"] for core in cores]
    poly = [by_core[core]["poly"] for core in cores]
    chipyard.append(sum(chipyard) / len(chipyard))
    poly.append(sum(poly) / len(poly))
    speedups = [speedup_percent(c, p) for c, p in zip(chipyard, poly, strict=True)]

    output = Path(config.get("output", "poly-total-time.png"))
    if not output.is_absolute():
        output = config_path.parent / output
    output.parent.mkdir(parents=True, exist_ok=True)

    xs = list(range(len(labels)))
    width = 0.36
    fig, ax = plt.subplots(figsize=(11, 5.6))
    chipyard_bars = ax.bar(
        [x - width / 2 for x in xs],
        chipyard,
        width,
        label="Chipyard",
        color="#4c78a8",
    )
    poly_bars = ax.bar(
        [x + width / 2 for x in xs],
        poly,
        width,
        label="Poly",
        color="#f58518",
    )

    ax.set_title(str(config.get("title", "Poly vs Chipyard Total Time")))
    ax.set_xlabel("Cores")
    ax.set_ylabel("Total time (min)")
    ax.set_xticks(xs, labels)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    ax.legend()

    for bar, pct in zip(poly_bars, speedups, strict=True):
        color = "#188038" if pct <= 0.0 else "#b3261e"
        ax.annotate(
            f"{pct:+.1f}%",
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
            color=color,
            bbox={
                "boxstyle": "round,pad=0.25",
                "facecolor": "white",
                "edgecolor": color,
                "linewidth": 1.1,
                "alpha": 0.95,
            },
        )
    for bars in (chipyard_bars, poly_bars):
        for bar in bars:
            ax.annotate(
                f"{bar.get_height():.1f}",
                xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, -12),
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=8,
                color="white",
            )

    ax.set_ylim(0, max(chipyard + poly) * 1.16)
    fig.tight_layout()
    fig.savefig(output, dpi=int(config.get("dpi", 160)))
    return output


def summary_root(path: Path, row: dict) -> Path:
    test = str(required(row, "test", str(path)))
    if path.parent.name != test:
        return path.parent
    return path.parent.parent


def subtask_logs(entry: dict[str, object]) -> list[tuple[str, Path, bool]]:
    path = Path(entry["path"])
    row = entry["row"]
    if not isinstance(row, dict):
        fail(f"{path} row must be a dict")
    test = str(required(row, "test", str(path)))
    root = summary_root(path, row)
    test_dir = root / test

    return [
        ("summary_csv", path.with_suffix(".csv"), False),
        ("workload", root / "logs/workload_build.log", True),
        ("verilog", test_dir / "bebop_verilator_verilog.log", True),
        ("build", test_dir / "bebop_verilator_build.log", True),
        ("simulation", test_dir / "bebop_verilator_sim.log", True),
        ("yosys", test_dir / "yosys.log", True),
    ]


def validate(entries: list[dict[str, object]]) -> int:
    failed = False
    for entry in sorted(entries, key=lambda e: (int(e["cores"]), str(e["system"]))):
        row = entry["row"]
        path = Path(entry["path"])
        if not isinstance(row, dict):
            fail(f"{path} row must be a dict")
        test = str(required(row, "test", str(path)))
        print(f"{BOLD_CYAN}{test} ({entry['system']}, {entry['cores']} cores){RESET}")
        print(f"  summary: {path}")
        for name, log, requires_completion in subtask_logs(entry):
            if not log.is_file():
                status = "MISSING"
                status_color = YELLOW
                ok = False
            elif log.stat().st_size == 0:
                status = "FAIL"
                status_color = RED
                ok = False
            elif requires_completion:
                text = log.read_text(encoding="utf-8", errors="replace")
                if (
                    "Task completed on http://127.0.0.1" not in text
                    and "Task completed on http://localhost" not in text
                ):
                    status = "FAIL"
                    status_color = RED
                    ok = False
                else:
                    status = "PASS"
                    status_color = GREEN
                    ok = True
            else:
                status = "PASS"
                status_color = GREEN
                ok = True
            failed = failed or not ok
            print(f"  {name:<10} {status_color}{status:<7}{RESET} {log}")
        print()
    return 1 if failed else 0


def main() -> int:
    args = parse_args()
    config_path = Path(__file__).resolve().parent / "analysis.toml"
    config = load_config(config_path)
    entries = load_entries(config["inputs"])
    if args.time:
        output = plot(collect_time(entries), config, config_path)
        print(output)
        return 0
    if args.valid:
        return validate(entries)
    fail("missing analysis mode")


if __name__ == "__main__":
    raise SystemExit(main())
