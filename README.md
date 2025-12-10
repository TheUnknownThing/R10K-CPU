# R10K-CPU

An RV32I CPU (with MIPS R10K like OoO) implemented with the assassyn [https://github.com/synthesys-lab/assassyn](https://github.com/synthesys-lab/assassyn).

It is a course project of Computer Systems (2025 Fall) at Shanghai Jiao Tong University. This project is developed by [Zhaoyuan Wan](https://github.com/caidj0) and [Hanning Wang](https://github.com/TheUnknownThing).

## Overview

RV32I, single-issue frontend with R10K-style out-of-order core: rename/Active List, ALU queue, LSQ, physical regfile (64 regs).

See `docs/architectural_report.md` for a full microarchitecture walkthrough.

## Requirements

- Python 3.11+ and the [Assassyn toolchain](https://github.com/synthesys-lab/assassyn)
- `pytest` for running the regression and unit tests

## Quick Start

1. Install assassyn per its README.

2. Run a demo simulation (uses `asms/empty/empty.hex` by default):
   ```bash
   python main.py
   ```
   The run prints architectural registers on each commit; the final line shows the program result.

3. Run the full test suite:
   ```bash
   pytest
   ```

## Project Structure

```text
.
├── main.py                     # top-level system builder
├── r10k_cpu
│   ├── modules                 # fetcher, decoder, scheduler, ALU, LSU, writeback, commit
│   ├── downstreams             # Active List, ALUQ, LSQ, MapTable, FreeList, Predictor, etc.
│   ├── instruction.py          # RV32I decode and operand selection
│   ├── common.py               # shared record/enum definitions
│   └── utils.py                # helpers
├── dataclass                   # circular queue + multiport storage utilities
├── asms                        # sample programs with .hex images and expected outputs
├── docs
│   └── architectural_report.md # detailed architecture report
└── tests                       # unit and integration tests
```
