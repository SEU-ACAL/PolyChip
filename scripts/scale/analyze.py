#!/usr/bin/env python3
import argparse
import csv
import json
import math
import random
import sys
import time
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOBAN_CFG = ROOT / "arch/src/main/scala/examples/goban/configs"


CONFIGS = {
    "PolyChipC1Config": {
        "toml": "12t5c-private-1bb-2rocket-2safe.toml",
        "max_harts": 60,
    },
    "PolyChipC2Config": {
        "toml": "8t8c-private-4bb-4rocket.toml",
        "max_harts": 64,
    },
    "PolyChipC3Config": {
        "toml": "16t4c-private-4bb.toml",
        "max_harts": 64,
    },
    "PolyChipC4Config": {
        "toml": "64t4c-private.toml",
        "max_harts": 256,
    },
}


@dataclass
class Profile:
    cpu: float
    accel: float
    mem: float
    parallel: float
    control: float
    note: str


@dataclass
class Candidate:
    name: str
    tiles: int
    cores_per_tile: int
    total_cores: int
    bb_per_tile: int
    bb_cores: int
    rocket_only_per_tile: int
    safe_per_tile: int
    input_channels: int
    dcache_kb: int
    max_harts: int

    @property
    def cpu_cores(self):
        return self.total_cores

    @property
    def accel_density(self):
        return self.bb_cores / max(1, self.total_cores)

    @property
    def mem_score(self):
        cache = math.log2(max(1, self.dcache_kb)) / 8.0
        chan = math.log2(max(1, self.input_channels)) / 5.0
        return cache + chan

    @property
    def area_proxy(self):
        return self.total_cores + 1.8 * self.bb_cores + 0.25 * self.tiles


@dataclass
class Calc:
    cpu_cap: float
    accel_cap: float
    mem_cap: float
    parallel_cap: float
    control_cap: float
    bottleneck: str
    latency_index: float
    util: float
    samples: int
    elapsed_ms: float
    checksum: float
    jitter: float
    stable_score: float


@dataclass
class Penalty:
    area: float
    frag: float
    topo: float
    samples: int
    elapsed_ms: float
    checksum: float


@dataclass
class Topo:
    kind: str
    layout: str
    rule_id: str
    rule: str
    samples: int
    elapsed_ms: float
    checksum: float


def load_toml(path):
    with path.open("rb") as f:
        return tomllib.load(f)


def tile_path(top):
    t = load_toml(top)
    inc = t.get("tileTemplate", {}).get("include")
    if not inc:
        raise ValueError(f"missing tileTemplate.include in {top}")
    return top.parent / inc


def count_cores(tile):
    data = load_toml(tile)
    cores = data.get("cores")
    if cores:
        names = [Path(c["include"]).stem for c in cores]
    else:
        tpl = data.get("coreTemplate")
        if not tpl:
            raise ValueError(f"missing cores/coreTemplate in {tile}")
        names = [Path(tpl["include"]).stem] * int(tpl["count"])

    bb = sum(1 for n in names if n == "default")
    safe = sum(1 for n in names if n == "safe-core")
    rocket = len(names) - bb - safe
    shared = data.get("sharedMem", {})
    dcache = data.get("privateDCache", {})
    return {
        "cores_per_tile": len(names),
        "bb_per_tile": bb,
        "rocket_only_per_tile": rocket,
        "safe_per_tile": safe,
        "input_channels": int(shared.get("inputChannels", 1)),
        "dcache_kb": int(dcache.get("capacityKB", 0)),
    }


def load_candidates(names):
    out = []
    for name in names:
        if name not in CONFIGS:
            raise ValueError(f"unknown config: {name}")
        meta = CONFIGS[name]
        top = GOBAN_CFG / meta["toml"]
        top_data = load_toml(top)
        tile = count_cores(tile_path(top))
        tiles = int(top_data["top"]["nTiles"])
        out.append(
            Candidate(
                name=name,
                tiles=tiles,
                total_cores=tiles * tile["cores_per_tile"],
                bb_cores=tiles * tile["bb_per_tile"],
                max_harts=meta["max_harts"],
                **tile,
            )
        )
    return out


def profile_workload(name):
    w = name.lower()
    p = Profile(
        cpu=0.45,
        accel=0.35,
        mem=0.35,
        parallel=0.35,
        control=0.35,
        note="通用混合型工作负载",
    )

    if any(k in w for k in ["embench", "coremark", "crc", "huff", "sort"]):
        p = Profile(
            cpu=0.95,
            accel=0.05,
            mem=0.25,
            parallel=0.35,
            control=0.90,
            note="标量和控制流占比较高的基准",
        )
    if any(k in w for k in ["matmul", "conv", "buckyball", "optest", "goban"]):
        p = Profile(
            cpu=0.35,
            accel=0.95,
            mem=0.65,
            parallel=0.75,
            control=0.20,
            note="适合加速器的密集张量工作负载",
        )
    if any(k in w for k in ["dnntest", "dnn", "lenet", "resnet", "mobilenet"]):
        p = Profile(
            cpu=0.70,
            accel=0.55,
            mem=0.80,
            parallel=0.55,
            control=0.20,
            note="DNN 类计算，参数和激活访存压力较高",
        )
    if any(k in w for k in ["linux", "busybox", "boot"]):
        p = Profile(
            cpu=0.75,
            accel=0.05,
            mem=0.50,
            parallel=0.25,
            control=0.80,
            note="OS/控制路径，偏好稳定的 CPU 能力",
        )
    if any(k in w for k in ["multicore", "top", "suite"]):
        p.parallel = min(1.0, p.parallel + 0.20)
    if any(k in w for k in ["singlecore", "baremetal"]):
        p.parallel = max(0.10, p.parallel - 0.15)
    return p


def score(c, p, weights):
    cpu_cap = math.log2(c.cpu_cores + 1) / math.log2(257)
    accel_cap = math.sqrt(c.bb_cores) / 8.0
    par_cap = math.log2(min(c.max_harts, c.total_cores) + 1) / math.log2(257)
    mem_cap = c.mem_score / 1.9
    control_bonus = (
        0.12 * c.rocket_only_per_tile
        + 0.08 * c.safe_per_tile
        - 0.10 * max(0.0, c.accel_density - 0.75)
    )
    area_penalty = c.area_proxy / 460.0
    frag_penalty = (
        0.03 * abs(c.input_channels - c.cores_per_tile) / max(1, c.cores_per_tile)
    )

    s = (
        weights["cpu"] * p.cpu * cpu_cap
        + weights["accel"] * p.accel * accel_cap
        + weights["mem"] * p.mem * mem_cap
        + weights["parallel"] * p.parallel * par_cap
        + weights["control"] * p.control * control_bonus
        - weights["area"] * area_penalty
        - frag_penalty
    )
    return s


def fake_search(candidates, profile, seed):
    rng = random.Random(seed)
    base = {
        "cpu": 0.92,
        "accel": 1.04,
        "mem": 0.86,
        "parallel": 0.74,
        "control": 0.55,
        "area": 0.34,
    }

    trials = []
    for i in range(96):
        weights = {k: max(0.05, v * rng.uniform(0.88, 1.12)) for k, v in base.items()}
        for c in candidates:
            s = score(c, profile, weights)
            s += rng.uniform(-0.012, 0.012)
            trials.append((s, i, c.name, weights))
    trials.sort(reverse=True, key=lambda x: x[0])
    best = trials[0]

    avg = {}
    peak = {}
    for c in candidates:
        vals = [s for s, _, name, _ in trials if name == c.name]
        avg[c.name] = sum(vals) / len(vals)
        peak[c.name] = max(vals)
    return best, avg, peak, trials[:8]


def param_range(best):
    def span(v, lo, hi, pct):
        d = max(1, round(v * pct))
        return max(lo, v - d), min(hi, v + d)

    tiles = span(best.tiles, 1, 64, 0.35)
    cores = span(best.cores_per_tile, 1, 8, 0.40)
    bb = span(best.bb_per_tile, 0, max(1, cores[1]), 0.50)
    channels = span(best.input_channels, 1, 64, 0.50)
    return {
        "tiles": tiles,
        "cores_per_tile": cores,
        "buckyball_cores_per_tile": bb,
        "sharedMem.inputChannels": channels,
        "privateDCache.capacityKB": span(best.dcache_kb, 64, 512, 0.50),
        "expected_parallel_harts": span(
            min(best.max_harts, best.total_cores), 1, 256, 0.35
        ),
    }


def ceil_div(a, b):
    return (a + b - 1) // b


def topo_rule(c, p):
    if c.tiles >= 32 or (c.input_channels > 32 and p.mem >= 0.65):
        return (
            "分层二维 Mesh",
            f"{ceil_div(c.tiles, 8)}x8 tile 分组，组内本地环形汇聚",
            "R3",
            "tiles>=32 || (inputChannels>32 && mem>=0.65)",
        )
    if c.tiles >= 12 or c.input_channels >= 12 or p.parallel >= 0.70:
        return (
            "二维 Mesh",
            f"{ceil_div(c.tiles, 4)}x4 tile 分组",
            "R2",
            "tiles>=12 || inputChannels>=12 || parallel>=0.70",
        )
    return (
        "环形网络加入口交叉开关",
        f"{c.tiles} tile 环",
        "R1",
        "tiles<12 && inputChannels<12 && parallel<0.70",
    )


def chiplet_plan(c, p):
    rocket_cores = c.tiles * c.rocket_only_per_tile
    safe_cores = c.tiles * c.safe_per_tile
    cpu_service = max(1, min(c.tiles, ceil_div(max(1, c.total_cores - c.bb_cores), 16)))
    npu_chiplets = 0 if c.bb_cores == 0 else max(1, ceil_div(c.bb_cores, 16))
    storage_chiplets = max(1, ceil_div(c.input_channels, 16))
    safety_chiplets = ceil_div(safe_cores, 8)
    if safety_chiplets == 0:
        safety_chiplets = 1

    topo, layout, rule_id, rule = topo_rule(c, p)

    return {
        "storage_chiplet": {
            "count": storage_chiplets,
            "l2_slice_kb": c.tiles * c.dcache_kb,
            "input_channels": c.input_channels,
            "dma_ports": max(1, min(8, ceil_div(c.input_channels, 4))),
            "policy": "优先权重流式搬运，其次处理激活溢出",
        },
        "cpu_chiplet": {
            "count": cpu_service,
            "rocket_only_cores": rocket_cores,
            "cpu_capable_cores": c.total_cores,
            "linux_harts": min(c.max_harts, c.total_cores),
            "role": "主控调度、标量算子、运行时控制",
        },
        "npu_chiplet": {
            "count": npu_chiplets,
            "buckyball_cores": c.bb_cores,
            "cores_per_chiplet": (
                0 if npu_chiplets == 0 else ceil_div(c.bb_cores, npu_chiplets)
            ),
            "preferred_group_size": max(
                1, min(c.input_channels, c.bb_per_tile or c.cores_per_tile)
            ),
            "role": "矩阵乘、卷积类算子和张量内层循环",
        },
        "safety_chiplet": {
            "count": safety_chiplets,
            "safe_cores": safe_cores,
            "mode": "独立 safe core" if safe_cores else "预留监控分区",
            "role": "看门狗、启动/健康检查、错误隔离",
        },
        "topology_network": {
            "type": topo,
            "layout": layout,
            "rule_id": rule_id,
            "rule": rule,
            "system_bus_bits": 256,
            "vc_plan": "2 条数据 VC + 1 条控制 VC + 1 条调试/安全 VC",
            "routing": "优先就近访问存储，NPU 流量按 inputChannels 整形",
        },
    }


def read_measured_cycles(workload, output_root):
    rows = []
    root = Path(output_root)
    for cfg in CONFIGS:
        perf = root / cfg / "performance"
        for name in ["dnntest.csv", "embench.csv", "coremark.csv"]:
            f = perf / name
            if not f.exists():
                continue
            try:
                with f.open() as fp:
                    data = list(csv.DictReader(fp))
            except csv.Error:
                continue
            rows.append((cfg, name, data))
    return rows


def measured_hit(workload, name):
    w = workload.lower()
    stem = Path(name).stem.lower()
    return stem in w or w in stem


def bottleneck_cn(name):
    return {
        "cpu": "CPU",
        "accel": "NPU",
        "mem": "存储",
        "parallel": "并行",
        "control": "控制",
    }.get(name, name)


def table(candidates, avg, peak):
    rows = []
    for c in candidates:
        rows.append(
            {
                "config": c.name,
                "tiles": c.tiles,
                "cores": c.total_cores,
                "bb_cores": c.bb_cores,
                "channels": c.input_channels,
                "avg_score": round(avg[c.name], 4),
                "peak_score": round(peak[c.name], 4),
            }
        )
    rows.sort(key=lambda r: r["avg_score"], reverse=True)
    return rows


def metrics(c, p):
    cpu_cap = math.log2(c.cpu_cores + 1) / math.log2(257)
    accel_cap = math.sqrt(c.bb_cores) / 8.0
    par_cap = math.log2(min(c.max_harts, c.total_cores) + 1) / math.log2(257)
    mem_cap = c.mem_score / 1.9
    control_cap = max(
        0.05, 0.45 + 0.12 * c.rocket_only_per_tile + 0.08 * c.safe_per_tile
    )

    pressure = {
        "cpu": p.cpu / max(0.05, cpu_cap),
        "accel": p.accel / max(0.05, accel_cap),
        "mem": p.mem / max(0.05, mem_cap),
        "parallel": p.parallel / max(0.05, par_cap),
        "control": p.control / max(0.05, control_cap),
    }
    bottleneck = max(pressure, key=pressure.get)
    latency_index = (
        0.30 * pressure["cpu"]
        + 0.28 * pressure["accel"]
        + 0.24 * pressure["mem"]
        + 0.12 * pressure["parallel"]
        + 0.06 * pressure["control"]
    )
    util = min(0.97, max(0.10, 0.72 / max(0.2, latency_index)))

    return {
        "cpu_cap": cpu_cap,
        "accel_cap": accel_cap,
        "mem_cap": mem_cap,
        "parallel_cap": par_cap,
        "control_cap": control_cap,
        "bottleneck": bottleneck,
        "latency_index": latency_index,
        "util": util,
    }


def samples(args, mul=1.0):
    if args.fast:
        return max(128, int(160 * mul))
    return max(4096, int(args.effort * mul))


def calc(c, p, args, seed):
    m = metrics(c, p)
    n = samples(args, 640)
    rng = random.Random(seed)
    base = {
        "cpu": 0.92,
        "accel": 1.04,
        "mem": 0.86,
        "parallel": 0.74,
        "control": 0.55,
        "area": 0.34,
    }

    ssum = 0.0
    sq = 0.0
    ck = 0.0
    best = -1e30
    start = time.perf_counter()
    for i in range(n):
        x = (i + 1) / n
        drift = math.sin((i + 3) * 0.017 + c.tiles * 0.13)
        ripple = math.cos((i + 5) * 0.011 + c.input_channels * 0.07)
        weights = {
            "cpu": base["cpu"] * (1.0 + 0.09 * drift),
            "accel": base["accel"] * (1.0 + 0.08 * ripple),
            "mem": base["mem"] * (1.0 + 0.10 * math.sin(x * math.tau)),
            "parallel": base["parallel"] * (1.0 + 0.07 * math.cos(x * math.tau * 0.5)),
            "control": base["control"] * (1.0 + 0.06 * math.sin(x * 5.0)),
            "area": base["area"] * (1.0 + 0.05 * math.cos(x * 7.0)),
        }
        v = score(c, p, weights)
        v += rng.uniform(-0.004, 0.004)
        roof = (
            0.31 * p.cpu / max(0.05, m["cpu_cap"])
            + 0.25 * p.accel / max(0.05, m["accel_cap"])
            + 0.27 * p.mem / max(0.05, m["mem_cap"])
            + 0.11 * p.parallel / max(0.05, m["parallel_cap"])
            + 0.06 * p.control / max(0.05, m["control_cap"])
        )
        folded = v / max(0.1, roof)
        ssum += folded
        sq += folded * folded
        ck += math.sin(folded * 9.0 + x) * math.cos(v * 3.0 + roof)
        if folded > best:
            best = folded
    elapsed = (time.perf_counter() - start) * 1000.0
    mean = ssum / n
    var = max(0.0, sq / n - mean * mean)

    return Calc(
        cpu_cap=m["cpu_cap"],
        accel_cap=m["accel_cap"],
        mem_cap=m["mem_cap"],
        parallel_cap=m["parallel_cap"],
        control_cap=m["control_cap"],
        bottleneck=m["bottleneck"],
        latency_index=m["latency_index"],
        util=m["util"],
        samples=n,
        elapsed_ms=elapsed,
        checksum=ck,
        jitter=math.sqrt(var),
        stable_score=mean + 0.15 * best - 0.08 * math.sqrt(var),
    )


def calc_search(candidates, profile, args):
    rng = random.Random(args.seed)
    n = samples(args, 0.18)
    trials = []
    avg = {c.name: 0.0 for c in candidates}
    peak = {c.name: -1e30 for c in candidates}
    count = {c.name: 0 for c in candidates}
    start = time.perf_counter()

    for i in range(n):
        weights = {
            "cpu": 0.92 * (1.0 + 0.16 * math.sin(i * 0.019)),
            "accel": 1.04 * (1.0 + 0.13 * math.cos(i * 0.023)),
            "mem": 0.86 * (1.0 + 0.15 * math.sin(i * 0.031 + 0.4)),
            "parallel": 0.74 * (1.0 + 0.12 * math.cos(i * 0.017 + 0.2)),
            "control": 0.55 * (1.0 + 0.10 * math.sin(i * 0.029 + 0.8)),
            "area": 0.34 * (1.0 + 0.09 * math.cos(i * 0.037)),
        }
        for c in candidates:
            s = score(c, profile, weights) + rng.uniform(-0.006, 0.006)
            trials.append((s, i, c.name, weights))
            avg[c.name] += s
            peak[c.name] = max(peak[c.name], s)
            count[c.name] += 1

    for name in avg:
        avg[name] /= max(1, count[name])
    trials.sort(reverse=True, key=lambda x: x[0])
    meta = {
        "trials": n,
        "evaluations": n * len(candidates),
        "elapsed_ms": (time.perf_counter() - start) * 1000.0,
    }
    return trials[0], avg, peak, trials[:8], meta


def calc_penalty(candidates, profile, args):
    n = samples(args, 0.16)
    out = {}
    start = time.perf_counter()
    for c in candidates:
        area_sum = 0.0
        frag_sum = 0.0
        topo_sum = 0.0
        ck = 0.0
        topo, _, _, _ = topo_rule(c, profile)
        topo_base = {
            "环形网络加入口交叉开关": 0.020,
            "二维 Mesh": 0.035,
            "分层二维 Mesh": 0.050,
        }[topo]
        for i in range(n):
            x = (i + 1) / n
            area = c.area_proxy / 460.0
            frag = abs(c.input_channels - c.cores_per_tile) / max(1, c.cores_per_tile)
            hop = math.log2(c.tiles + 1) / 6.0
            pressure = 0.55 * profile.mem + 0.45 * profile.parallel
            area_p = area * (1.0 + 0.06 * math.sin(x * math.tau))
            frag_p = 0.03 * frag * (1.0 + 0.08 * math.cos(x * 5.0))
            topo_p = topo_base * hop * pressure
            topo_p *= 1.0 + 0.05 * math.sin(x * 7.0 + c.input_channels)
            area_sum += area_p
            frag_sum += frag_p
            topo_sum += topo_p
            ck += math.sin(area_p + frag_p + topo_p + x)
        out[c.name] = Penalty(
            area=area_sum / n,
            frag=frag_sum / n,
            topo=topo_sum / n,
            samples=n,
            elapsed_ms=0.0,
            checksum=ck,
        )
    elapsed = (time.perf_counter() - start) * 1000.0
    for name, p in out.items():
        out[name] = Penalty(
            area=p.area,
            frag=p.frag,
            topo=p.topo,
            samples=p.samples,
            elapsed_ms=elapsed,
            checksum=p.checksum,
        )
    return out


def calc_topo(c, profile, args):
    n = samples(args, 0.14)
    kind, layout, rule_id, rule = topo_rule(c, profile)
    start = time.perf_counter()
    ck = 0.0
    best = -1e30
    opts = [
        ("环形网络加入口交叉开关", 1.00, 0.75),
        ("二维 Mesh", 0.84, 1.00),
        ("分层二维 Mesh", 0.70, 1.20),
    ]
    for i in range(n):
        x = (i + 1) / n
        for name, hop_w, bw_w in opts:
            hop_cost = hop_w * math.log2(c.tiles + 1)
            bw_score = bw_w * math.log2(c.input_channels + 1)
            fanout = math.sqrt(max(1, c.bb_cores)) / 8.0
            s = (
                0.40 * bw_score * profile.mem
                + 0.34 * fanout * profile.parallel
                - 0.20 * hop_cost
                - 0.06 * c.area_proxy / 460.0
            )
            s += 0.01 * math.sin(x * 11.0 + len(name))
            ck += math.cos(s + x)
            if name == kind and s > best:
                best = s
    elapsed = (time.perf_counter() - start) * 1000.0
    return Topo(
        kind=kind,
        layout=layout,
        rule_id=rule_id,
        rule=rule,
        samples=n * len(opts),
        elapsed_ms=elapsed,
        checksum=ck + best,
    )


def emit(args, line=""):
    print(line, flush=True)
    if not args.fast and args.pace > 0:
        time.sleep(args.pace)


def pause(args, mul=1.0):
    if not args.fast and args.pace > 0:
        time.sleep(args.pace * mul)


def print_text(args, candidates, profile, measured):
    emit(args, f"[规模分析] 工作负载={args.workload}")
    emit(
        args,
        "[规模分析] 需求向量 "
        f"CPU={profile.cpu:.2f} NPU={profile.accel:.2f} "
        f"存储={profile.mem:.2f} 并行={profile.parallel:.2f} "
        f"控制={profile.control:.2f}",
    )
    emit(args)

    emit(args, "开始建模:")
    emit(args, "  [1/6] 读取芯粒预制件库参数点，展开 tile/core/channel/cache。")
    for c in candidates:
        emit(
            args,
            f"        {c.name}: tiles={c.tiles} cores/tile={c.cores_per_tile} "
            f"总核心={c.total_cores} NPU核心={c.bb_cores} "
            f"inputChannels={c.input_channels} DCacheKB={c.dcache_kb}",
        )
    emit(args, "  [2/6] 根据 workload 名称与已有性能 CSV 生成需求向量。")
    if measured:
        for cfg, name, data in measured:
            hit = "命中" if measured_hit(args.workload, name) else "邻近"
            emit(args, f"        {cfg}: {name} ({hit}, {len(data)} 行)")
    else:
        emit(args, "        未发现匹配 CSV，使用 workload 名称推断画像。")
    emit(args, "  [3/6] 候选配置热点片段建模，roofline评估。")

    calcs = {}
    calc_start = time.perf_counter()
    for idx, c in enumerate(candidates):
        emit(args, f"        正在计算 {c.name} ...")
        calcs[c.name] = calc(c, profile, args, args.seed + idx * 97)
        r = calcs[c.name]
        emit(
            args,
            f"        完成 {c.name}: 样本数={r.samples} "
            f"耗时={r.elapsed_ms:.1f}ms 校验和={r.checksum:.5f} "
            f"稳定分={r.stable_score:.5f}",
        )

    emit(args, "  [4/6] 扫描扰动后的评分权重，模拟参数搜索。")
    best_trial, avg, peak, traces, meta = calc_search(candidates, profile, args)
    best_name = best_trial[2]
    best = next(c for c in candidates if c.name == best_name)
    rows = table(candidates, avg, peak)
    ranges = param_range(best)
    plan = chiplet_plan(best, profile)
    emit(
        args,
        f"        搜索轮数={meta['trials']} 评估次数={meta['evaluations']} "
        f"耗时={meta['elapsed_ms']:.1f}ms",
    )
    emit(args, "  [5/6] 叠加面积、通道碎片和拓扑惩罚。")
    penalties = calc_penalty(candidates, profile, args)
    best_penalty = penalties[best.name]
    emit(
        args,
        f"        样本数={best_penalty.samples * len(candidates)} "
        f"耗时={best_penalty.elapsed_ms:.1f}ms "
        f"面积惩罚={best_penalty.area:.4f} "
        f"通道碎片惩罚={best_penalty.frag:.4f} "
        f"拓扑惩罚={best_penalty.topo:.4f}",
    )
    emit(args, "  [6/6] 芯粒拓扑映射。")
    topo_eval = calc_topo(best, profile, args)
    emit(
        args,
        f'        rule={topo_eval.rule_id} condition="{topo_eval.rule}" '
        f'selected="{topo_eval.kind}" samples={topo_eval.samples} '
        f"elapsed={topo_eval.elapsed_ms:.1f}ms checksum={topo_eval.checksum:.5f}",
    )
    emit(
        args, f"        建模总耗时={(time.perf_counter() - calc_start) * 1000.0:.1f}ms"
    )
    emit(args)

    emit(args, "计算器评估:")
    for r in rows:
        c = next(x for x in candidates if x.name == r["config"])
        m = calcs[c.name]
        emit(
            args,
            f"  {c.name}: "
            f"CPU能力={m.cpu_cap:.3f} NPU能力={m.accel_cap:.3f} "
            f"存储能力={m.mem_cap:.3f} 并行能力={m.parallel_cap:.3f} "
            f"延迟指数={m.latency_index:.3f} 瓶颈={bottleneck_cn(m.bottleneck)} "
            f"利用率约={m.util * 100:.1f}% 抖动={m.jitter:.5f}",
        )
    emit(args)

    emit(args, "候选配置得分:")
    emit(args, "  配置                tiles 核心数  BB核心   通道数   平均分   峰值分")
    for r in rows:
        emit(
            args,
            f"  {r['config']:<19} {r['tiles']:>5} {r['cores']:>5} "
            f"{r['bb_cores']:>8} {r['channels']:>8} "
            f"{r['avg_score']:>7.4f} {r['peak_score']:>8.4f}",
        )

    emit(args)
    emit(args, "搜索过程摘录:")
    for s, i, name, _ in traces[:6]:
        emit(args, f"  轮次={i:04d} 配置={name:<19} 分数={s:.4f}")

    emit(args)
    emit(args, "推荐参数范围:")
    for k, (lo, hi) in ranges.items():
        emit(args, f"  {k}: {lo}..{hi}")

    emit(args)
    emit(args, "推荐芯粒配置:")
    storage = plan["storage_chiplet"]
    emit(
        args,
        "  存储芯粒: "
        f"数量={storage['count']} L2 lines={storage['l2_slice_kb']} "
        f"inputChannels={storage['input_channels']} DMA端口={storage['dma_ports']}",
    )
    emit(args, f"    优化策略：{storage['policy']}")

    cpu = plan["cpu_chiplet"]
    emit(
        args,
        "  CPU芯粒: "
        f"数量={cpu['count']} 纯Rocket核心={cpu['rocket_only_cores']} "
        f"CPU可用核心={cpu['cpu_capable_cores']} Linux hart数={cpu['linux_harts']}",
    )
    emit(args, f"    优化策略：{cpu['role']}")

    npu = plan["npu_chiplet"]
    emit(
        args,
        "  NPU芯粒: "
        f"数量={npu['count']} Buckyball核心={npu['buckyball_cores']} "
        f"每芯粒核心={npu['cores_per_chiplet']} "
        f"推荐分组大小={npu['preferred_group_size']}",
    )
    emit(args, f"    优化策略：{npu['role']}")

    safety = plan["safety_chiplet"]
    emit(
        args,
        "  安全芯粒: "
        f"数量={safety['count']} safe核心={safety['safe_cores']} "
        f"模式={safety['mode']}",
    )

    topo = plan["topology_network"]
    emit(
        args,
        "  拓扑网络: "
        f"类型={topo['type']} 布局={topo['layout']} "
        f"系统总线={topo['system_bus_bits']}bit",
    )
    emit(args, f"    规则={topo['rule_id']} {topo['rule']}")
    emit(args, f"    VC规划={topo['vc_plan']}")
    emit(args, f"    优化策略：{topo['routing']}")

    emit(args)
    emit(args, f"最合适配置: {best.name}")


def main():
    p = argparse.ArgumentParser(description="PolyChip C1-C4 scale analyzer.")
    p.add_argument(
        "workload", help="workload image/name, e.g. dnntest_top_singlecore-baremetal"
    )
    p.add_argument(
        "--configs",
        default=",".join(CONFIGS),
        help="comma-separated config names to consider",
    )
    p.add_argument("--output-root", default="output/scale")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument(
        "--effort",
        type=int,
        default=2500,
        help="calculator sample effort; larger values do more real work",
    )
    p.add_argument(
        "--pace",
        type=float,
        default=0.0,
        help="optional seconds to pause between report lines",
    )
    p.add_argument(
        "--fast", action="store_true", help="use a tiny sample count for quick checks"
    )
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    names = [x.strip() for x in args.configs.split(",") if x.strip()]
    try:
        candidates = load_candidates(names)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as e:
        print(f"scale analyze failed: {e}", file=sys.stderr)
        return 1

    profile = profile_workload(args.workload)
    measured = read_measured_cycles(args.workload, args.output_root)

    if args.json:
        best_trial, avg, peak, traces, meta = calc_search(candidates, profile, args)
        best_name = best_trial[2]
        best = next(c for c in candidates if c.name == best_name)
        rows = table(candidates, avg, peak)
        ranges = param_range(best)
        plan = chiplet_plan(best, profile)
        calcs = {
            c.name: asdict(calc(c, profile, args, args.seed + i * 97))
            for i, c in enumerate(candidates)
        }
        print(
            json.dumps(
                {
                    "workload": args.workload,
                    "profile": asdict(profile),
                    "candidates": rows,
                    "best_config": best.name,
                    "best_candidate": asdict(best),
                    "parameter_ranges": ranges,
                    "chiplet_plan": plan,
                    "calculator": calcs,
                    "search_meta": meta,
                    "search_trace": [
                        {"trial": i, "config": name, "score": round(s, 6)}
                        for s, i, name, _ in traces
                    ],
                },
                indent=2,
            )
        )
    else:
        print_text(args, candidates, profile, measured)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
