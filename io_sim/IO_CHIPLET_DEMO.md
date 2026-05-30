# IO Chiplet Demo (Ruby/Garnet) — Build & Run Guide

This demo uses Ruby’s `Garnet_standalone` protocol because it is designed for **network injection + network statistics**:
- CPU-side nodes inject packets into the network.
- A Directory node acts as a **sink** (it receives and drops packets), so the network drains cleanly and stats are stable.

## Repo layout

- `io_sim/gem5/`: gem5 fork as a submodule
- `io_sim/io_sim_config.json`: single config file for build + run
- `io_sim/build_io_sim`: build script
- `io_sim/run_io_sim`: run script (reads the same config)

## 1) Build

```bash
./io_sim/build_io_sim
```

Notes:
- System/toolchain dependencies of gem5 are assumed to be ready.
- Python dependencies of gem5 are automatically installed before building.

## 2) Run

Run uses the parameters under `run.io_chiplet_params` in `io_sim_config.json`:

```bash
./io_sim/run_io_sim
```

The demo prints:
- A header with **all parameter values** (one per line, with units)
- A final **summary block** with key network metrics

Notes:
- A `stats.txt` file is still written under the directory configured by `run.outdir`.
- Default traffic is **many-to-one** at a fixed high load (`injectionrate=0.5`) and fixed run length (`sim_cycles=50000`).

All demo parameters have fixed discrete choices:

| Parameter (config path) | Description | Default | Choices |
|---|---|---:|---|
| `run.io_chiplet_params.num_ports` | Number of injection endpoints | 4 | 2 / 4 / 8 |
| `run.io_chiplet_params.router_latency` | Router internal pipeline latency (cycles) | 1 | 1 / 2 / 3 / 4 |
| `run.io_chiplet_params.link_latency` | Link + abstract PHY latency (cycles) | 2 | 1 / 2 / 4 / 8 |
| `run.io_chiplet_params.flit_width_bits` | Flit width (bits) | 128 | 64 / 128 / 256 |
| `run.io_chiplet_params.vcs_per_vnet` | Virtual channels per virtual network | 4 | 1 / 2 / 4 / 8 |
| `run.io_chiplet_params.buffer_depth` | Data VC buffer depth (flits) | 4 | 1 / 2 / 4 / 8 / 16 |

Port semantics:
- `run.io_chiplet_params.num_ports` = number of **injection** endpoints (compute/peripheral endpoints)
- plus **one** fixed sink endpoint (Directory): total endpoints = `num_ports + 1`

## Metrics to track (printed to stdout)

The demo prints these metrics at the end of the run:

- `packets_received_total` (packets)
- `pkts_per_cycle_total` (packets/cycle, all ports)
- `pkts_per_cycle_per_port` (packets/(port*cycle))
- `avg_packet_latency` (cycles)
- `avg_packet_network_latency` (cycles)
- `avg_packet_queueing_latency` (cycles)
- `avg_link_utilization` (flits/cycle, aggregated over links)
- `avg_vc_load_total` (flits/cycle, aggregated over VCs)
- `avg_vc_load_mean` (flits/cycle per-VC, aggregated over links)
- `avg_vc_load_max` (flits/cycle for the busiest VC)

If you need the complete stats, open `stats.txt` under the directory set by `run.outdir`.
