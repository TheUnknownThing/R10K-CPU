#!/usr/bin/env python3
"""IPC sweep across asm testbenches.

This script:
- Builds the simulator once (via main.build_cpu + assassyn build_simulator)
- Runs each program under asms/<name>/<name>.hex
- Parses the final terminator commit line for cycle count, x10, and retire_count
- Writes results to out/ipc_results.csv

Note: per repo convention, run `ass` in your shell first to set up the
assassyn toolchain/PYTHONPATH before invoking this script.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
from dataclasses import dataclass
from typing import Iterable

from assassyn.utils import build_simulator, run_simulator

from main import build_cpu
from r10k_cpu.utils import prepare_byte_files
from tests.utils import run_quietly


TERMINATOR_LINE_RE = re.compile(
    r"Cycle\s+@(?P<cycle>[0-9]+(?:\.[0-9]+)?):\s+\[Commit\]\s+PC=0x(?P<pc>[0-9A-Fa-f]{8}),\s+x10=(?P<x10>0x[0-9A-Fa-f]+),\s+retire_count=(?P<retire>[0-9]+)"
)


@dataclass(frozen=True)
class ResultRow:
    test: str
    status: str
    cycles: int | None
    retired: int | None
    ipc: float | None
    x10: int | None
    expected_x10: int | None
    notes: str


def iter_asm_tests(asms_dir: str) -> Iterable[str]:
    for entry in sorted(os.listdir(asms_dir)):
        if entry.startswith("."):
            continue
        hex_path = os.path.join(asms_dir, entry, f"{entry}.hex")
        out_path = os.path.join(asms_dir, entry, f"{entry}.out")
        if os.path.isfile(hex_path) and os.path.isfile(out_path):
            yield entry


def parse_terminator_line(raw: str) -> tuple[int, int, int]:
    """Return (cycles, x10, retired) from simulator output."""
    for line in reversed(raw.splitlines()):
        m = TERMINATOR_LINE_RE.search(line)
        if m:
            cycle_f = float(m.group("cycle"))
            cycles = int(round(cycle_f))
            x10 = int(m.group("x10"), 16)
            retired = int(m.group("retire"))
            return cycles, x10, retired
    raise ValueError("Terminator line not found (possibly hit sim_threshold)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asms-dir", default="asms")
    parser.add_argument("--work-dir", default="tmp")
    parser.add_argument("--out-csv", default="out/ipc_results.csv")
    parser.add_argument("--sim-threshold", type=int, default=3_000_000)
    args = parser.parse_args()

    os.makedirs(args.work_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.out_csv) or ".", exist_ok=True)

    work_hex_paths = [
        os.path.join(args.work_dir, fname)
        for fname in ["exe.hex", "exe_b0.hex", "exe_b1.hex", "exe_b2.hex", "exe_b3.hex"]
    ]

    _, simulator_path, _ = build_cpu(sram_files=work_hex_paths, sim_threshold=args.sim_threshold)
    simulator_binary, stdout, stderr = run_quietly(build_simulator, simulator_path)
    if not simulator_binary:
        raise RuntimeError(
            f"Build simulator failed with stdout:\n{stdout}\n\nstderr:\n{stderr}\n"
        )

    rows: list[ResultRow] = []

    for test in iter_asm_tests(args.asms_dir):
        hex_path = os.path.join(args.asms_dir, test, f"{test}.hex")
        out_path = os.path.join(args.asms_dir, test, f"{test}.out")

        with open(out_path, "r", encoding="utf-8") as f:
            expected_x10 = int(f.readline().strip())

        shutil.copyfile(hex_path, work_hex_paths[0])
        prepare_byte_files(work_hex_paths[0])

        raw, stdout, stderr = run_quietly(run_simulator, binary_path=simulator_binary)
        if not isinstance(raw, str):
            rows.append(
                ResultRow(
                    test=test,
                    status="error",
                    cycles=None,
                    retired=None,
                    ipc=None,
                    x10=None,
                    expected_x10=expected_x10,
                    notes=f"run_simulator failed: {stderr.strip() or stdout.strip()}",
                )
            )
            continue

        try:
            cycles, x10, retired = parse_terminator_line(raw)
            ipc = (retired / cycles) if cycles > 0 else None
            status = "pass" if x10 == expected_x10 else "fail"
            notes = ""
        except Exception as e:  # noqa: BLE001
            cycles, x10, retired, ipc = None, None, None, None
            status = "timeout"
            notes = str(e)

        rows.append(
            ResultRow(
                test=test,
                status=status,
                cycles=cycles,
                retired=retired,
                ipc=ipc,
                x10=x10,
                expected_x10=expected_x10,
                notes=notes,
            )
        )

    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["test", "status", "cycles", "retired", "ipc", "x10", "expected_x10", "notes"])
        for r in rows:
            w.writerow(
                [
                    r.test,
                    r.status,
                    r.cycles,
                    r.retired,
                    f"{r.ipc:.6f}" if r.ipc is not None else None,
                    r.x10,
                    r.expected_x10,
                    r.notes,
                ]
            )

    # Also print a short summary to stdout.
    passed = sum(1 for r in rows if r.status == "pass")
    failed = sum(1 for r in rows if r.status == "fail")
    timed = sum(1 for r in rows if r.status == "timeout")
    errored = sum(1 for r in rows if r.status == "error")
    print(f"Wrote {args.out_csv}")
    print(f"Summary: pass={passed} fail={failed} timeout={timed} error={errored}")

    return 0 if (failed == 0 and errored == 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
