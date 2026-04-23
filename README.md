# PolyChip

PolyChip is a scalable framework for heterogeneous multiple chiplet architecture, built on RISC-V architecture and optimized for different scenario designs.

## Project Overview

The PolyChip framework provides a comprehensive hardware design, simulation verification, and software development toolchain, supporting the full development process from RTL-level chiplet design to multi-die system-level verification. The framework adopts a modular, interconnect-centric design that supports flexible configuration and expansion of compute, IO, and memory chiplets, making it ideal for building specialized high-performance computing systems.

## Quick Start

### Installation in Nix
We use Nix Flake as our main build system. If you have not installed nix, install it following the [guide](https://nix.dev/manual/nix/2.28/installation/installing-binary.html), and enable flake following the [wiki](https://nixos.wiki/wiki/Flakes#Enable_flakes). Or you can try the [installer](https://github.com/DeterminateSystems/nix-installer) provided by Determinate Systems, which enables flake by default.


**1. Clone Repository**

```bash
git clone https://github.com/DangoSys/buckyball.git
```

**2. Initialize Environment**
```bash
cd buckyball
./scripts/nix/build-all.sh
```

After the first time installation, you can enter the environment anytime by running:

```bash
nix develop
```

**3. Verify Installation**

Run Verilator simulation test to verify installation:
```bash
bbdev verilator --run '--jobs 16 --binary ctest_vecunit_matmul_ones_singlecore-baremetal --config sims.verilator.BuckyballToyVerilatorConfig --batch'
```
