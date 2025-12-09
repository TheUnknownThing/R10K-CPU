from dataclasses import dataclass
from typing import List, Optional

from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator

from r10k_cpu.downstreams.register_ready import RegisterReady
from tests.utils import run_quietly


NUM_REGS = 8
MAX_WRITES = 2


@dataclass
class Step:
    cycle: int
    clear: Optional[List[int]] = None
    set_ready: Optional[List[int]] = None
    flush: bool = False
    probe: int = 0


STEPS = [
    Step(cycle=1, probe=0),
    Step(cycle=2, clear=[3], probe=3),
    Step(cycle=3, set_ready=[3], probe=3),
    Step(cycle=4, clear=[1, 6], probe=6),
    Step(cycle=5, set_ready=[1, 6], probe=1),
    Step(cycle=6, clear=[2], probe=2),
    Step(cycle=7, clear=[4], flush=True, probe=4),
]


class Driver(Module):
    def __init__(self):
        super().__init__(ports={})
        self.ready = RegisterReady(num_registers=NUM_REGS)
        self.cycle = RegArray(UInt(32), 1, initializer=[0])

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        clear_en = [Bits(1)(0) for _ in range(MAX_WRITES)]
        clear_idx = [Bits(self.ready.index_bits)(0) for _ in range(MAX_WRITES)]
        set_en = [Bits(1)(0) for _ in range(MAX_WRITES)]
        set_idx = [Bits(self.ready.index_bits)(0) for _ in range(MAX_WRITES)]
        flush_flag = Bits(1)(0)
        probe_idx = Bits(self.ready.index_bits)(0)

        for step in STEPS:
            if step.clear:
                assert (
                    len(step.clear) <= MAX_WRITES
                ), "Too many clear operations for allocated write ports"
            if step.set_ready:
                assert (
                    len(step.set_ready) <= MAX_WRITES
                ), "Too many set operations for allocated write ports"

            cond = cycle_val == UInt(32)(step.cycle)
            probe_idx = cond.select(Bits(self.ready.index_bits)(step.probe), probe_idx)
            flush_flag = cond.select(Bits(1)(1), flush_flag) if step.flush else flush_flag

            for port, reg_idx in enumerate(step.clear or []):
                clear_en[port] = cond.select(Bits(1)(1), clear_en[port])
                clear_idx[port] = cond.select(
                    Bits(self.ready.index_bits)(reg_idx), clear_idx[port]
                )

            for port, reg_idx in enumerate(step.set_ready or []):
                set_en[port] = cond.select(Bits(1)(1), set_en[port])
                set_idx[port] = cond.select(
                    Bits(self.ready.index_bits)(reg_idx), set_idx[port]
                )

        for en, idx in zip(clear_en, clear_idx):
            self.ready.mark_not_ready(idx, enable=en)

        for en, idx in zip(set_en, set_idx):
            self.ready.mark_ready(idx, enable=en)

        self.ready.build(flush_recover=flush_flag)

        ready_bit = self.ready.read(probe_idx)
        ready_state = self.ready.state()

        log(
            "cycle: {}, flush: {}, probe: {}, ready: {}, state: {}",
            cycle_val,
            flush_flag,
            probe_idx,
            ready_bit,
            ready_state,
        )


def _simulate_expected_state():
    step_map = {step.cycle: step for step in STEPS}
    max_cycle = max(STEPS, key=lambda s: s.cycle).cycle + 1
    state = (1 << NUM_REGS) - 1
    expectations = {}

    for cycle in range(0, max_cycle + 1):
        step = step_map.get(cycle)
        probe_idx = step.probe if step is not None else 0
        ready_bit = (state >> probe_idx) & 1
        expectations[cycle] = {"state": state, "ready": ready_bit, "probe": probe_idx}

        if step is not None:
            next_state = state
            for idx in step.clear or []:
                next_state &= ~(1 << idx)
            for idx in step.set_ready or []:
                next_state |= 1 << idx
            if step.flush:
                next_state = (1 << NUM_REGS) - 1
            state = next_state

    return expectations


def _parse_logs(raw: str):
    logs = {}
    for line in raw.strip().splitlines():
        if "cycle:" not in line:
            continue

        # Remove any prefix before "cycle:"
        line = line[line.find("cycle:") :]
        parts = line.replace(",", "").split()
        logs[int(parts[1])] = {
            "flush": int(parts[3]),
            "probe": int(parts[5]),
            "ready": int(parts[7]),
            "state": int(parts[9]),
        }
    return logs


def test_register_ready():
    sys = SysBuilder("test_register_ready")
    with sys:
        driver = Driver()
        driver.build()

    sim, _ = elaborate(sys, verilog=True, verbose=False, sim_threshold=32)
    raw, _, stderr = run_quietly(run_simulator, sim)
    print(f"DEBUG raw:\n{raw}")
    print(f"DEBUG stderr:\n{stderr}")
    assert raw is not None, stderr

    expected = _simulate_expected_state()
    logs = _parse_logs(raw)

    for cycle, exp in expected.items():
        log_entry = logs.get(cycle)
        assert log_entry is not None, f"Missing log for cycle {cycle}"
        assert log_entry["state"] == exp["state"], f"Cycle {cycle}: state mismatch"
        assert (
            log_entry["ready"] == exp["ready"]
        ), f"Cycle {cycle}: ready bit mismatch (probe {exp['probe']})"

    for cycle, log_entry in logs.items():
        if log_entry["flush"] == 1:
            next_entry = logs.get(cycle + 1)
            assert next_entry is not None, f"Missing post-flush state for cycle {cycle}"
            assert (
                next_entry["state"] == (1 << NUM_REGS) - 1
            ), f"Cycle {cycle + 1}: flush should set all bits ready"
