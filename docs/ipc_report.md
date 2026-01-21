# R10K-CPU IPC Report

This document is a reader-facing performance report for the repository’s R10K-like out-of-order RV32I CPU.
It explains **what was measured**, **how IPC was computed**, and **what the results suggest** about the current microarchitecture.

## CPU overview
- ISA: RV32I+M user programs in `asms/` (program result observed via `x10`)
- Frontend: **single-issue** decode/rename (at most 1 instruction enters the OoO backend per cycle)
- Backend (R10K-like): in-order retirement via Active List; OoO scheduling through ALUQ and LSQ
- Main structures (current build):
  - Active List (ROB): 32 entries
  - ALU Queue: 32 entries
  - LSQ: 32 entries (+ 1-entry committed store buffer)
  - Physical integer registers: 64
- Branch prediction: default `build_cpu()` uses `BinaryPredictor(4, WeaklyNo)` (see `main.py`).
- For a detailed microarchitecture walkthrough, see `docs/architectural_report.md`.

## What we measured

- **Cycles**: taken from the simulator’s `Cycle @...` prefix on the final (terminator) commit log line.
- **Retired instructions**: a 64-bit `retire_count` maintained in the `Commit` module.
- **IPC**: $\text{IPC} = \frac{\text{retired instructions}}{\text{cycles}}$
- **CPI** (also reported): $\text{CPI} = \frac{\text{cycles}}{\text{retired instructions}} = \frac{1}{\text{IPC}}$
- `retire_count` increments once whenever the Active List head **retires** (in-order), i.e. at most one increment per cycle.
- Wrong-path (flushed) instructions are never retired, and therefore never counted.
- The terminator instruction is retired and included in the final `retire_count` printed.
- The reported IPC is **end-to-end** (start of simulation to program termination), not a steady-state kernel IPC.

## Benchmark suite
The suite consists of all subdirectories under `asms/` that contain both:
- `asms/<test>/<test>.hex` (program image)
- `asms/<test>/<test>.out` (golden `x10` result)

At a high level the suite covers:
- ALU and short loops (`arithmetic`, `logic_ops`, `sum`, `sum100`)
- Memory + control mixes (`bubble_sort`, `quick_sort`, `qsort`, `primes`)
- Longer dependency/control chains and recursion (`magic`, `hanoi`, `queens`)
- Regular compute loops (`matrix_mul`, `vector_add`, `vector_mul`, `multiarray`)

### Summary views

**Bottom IPC (least throughput)**
- `arithmetic`, `empty`, `logic_ops`: IPC 0.2857 (CPI 3.500)
- `math_comprehensive`: IPC 0.2921 (CPI 3.423)
- `sum100`: IPC 0.4181 (CPI 2.392)

**Top IPC (best throughput in this suite)**
- `multiarray`: IPC 0.7807 (CPI 1.281)
- `fibonacci`: IPC 0.7668 (CPI 1.304)
- `store_byte_half`: IPC 0.7143 (CPI 1.400)
- `sum`: IPC 0.6389 (CPI 1.565)
- `vector_add`: IPC 0.6347 (CPI 1.575)

### Per-benchmark table (IPC + CPI)
| Test | Cycles | Retired | IPC | CPI | x10 | Notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| arithmetic | 14 | 4 | 0.285714 | 3.500 | 40 |  |
| bubble_sort | 586 | 293 | 0.500000 | 2.000 | 11 |  |
| empty | 14 | 4 | 0.285714 | 3.500 | 516 |  |
| fibonacci | 283 | 217 | 0.766784 | 1.304 | 8 |  |
| hanoi | 159500 | 98465 | 0.617335 | 1.620 | 20 |  |
| logic_ops | 14 | 4 | 0.285714 | 3.500 | 31 |  |
| magic | 402549 | 241950 | 0.601045 | 1.664 | 106 |  |
| math_comprehensive | 6959 | 2033 | 0.292140 | 3.423 | 158617 |  |
| matrix_mul | 32320 | 17762 | 0.549567 | 1.820 | 18816 |  |
| multiarray | 228 | 178 | 0.780702 | 1.281 | 115 |  |
| primes | 21184 | 11419 | 0.539039 | 1.855 | 168 |  |
| qsort | 1718860 | 974876 | 0.567164 | 1.763 | 105 |  |
| queens | 492405 | 278224 | 0.565031 | 1.770 | 171 |  |
| quick_sort | 80556 | 39000 | 0.484135 | 2.066 | 5050 |  |
| store_byte_half | 63 | 45 | 0.714286 | 1.400 | 54389 |  |
| sum | 36 | 23 | 0.638889 | 1.565 | 55 |  |
| sum100 | 2454 | 1026 | 0.418093 | 2.392 | 5050 |  |
| test_div | 140 | 62 | 0.442857 | 2.258 | 2147483647 |  |
| test_mul | 166 | 91 | 0.548193 | 1.824 | 2147539734 |  |
| test_mulh | 164 | 89 | 0.542683 | 1.843 | 2147231736 |  |
| test_rem | 163 | 71 | 0.435583 | 2.296 | 1 |  |
| vector_add | 3017 | 1915 | 0.634736 | 1.575 | 10000 |  |
| vector_mul | 3018 | 1816 | 0.601723 | 1.662 | 9900 |  |

## Why IPC varies so much in this suite

- **Single-issue frontend ceiling**: because only one instruction can be decoded/renamed per cycle, the best-case steady-state IPC is bounded near 1.0, and any bubbles (frontend stall, flush recovery, cache/memory latency) quickly pull IPC down.
- **End-to-end measurement amplifies fixed costs**: very short programs (4 retired instructions total) are dominated by constant overhead (pipeline fill, bookkeeping, terminator), so they report low IPC even if the “core” instructions execute efficiently.
- **Memory ordering and LSQ constraints**: loads are prevented from passing older stores in the LSQ selection scan. Store execution occurs via a committed store buffer. These policies are correct-by-construction but can reduce overlap for memory-heavy codes.
- **Control flow / speculation recovery**: branch prediction quality and flush penalties affect long control-heavy workloads (e.g., `queens`, `qsort`). IPC in the ~0.56–0.60 range indicates the backend is often busy but still experiences frequent serialization points.