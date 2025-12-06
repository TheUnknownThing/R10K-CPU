from dataclasses import dataclass
from typing import Optional, Dict

from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator

from r10k_cpu.downstreams.map_table import MapTable, MapTableWriteEntry
from tests.utils import run_quietly


@dataclass
class Step:
    cycle: int
    rename: Optional[Dict[str, int]] = None
    commit: Optional[Dict[str, int]] = None
    flush: bool = False
    read_idx: int = 0


STEPS = [
    Step(cycle=1, rename={"logical": 1, "physical": 40}, read_idx=1),
    Step(cycle=2, rename={"logical": 2, "physical": 41}, read_idx=2),
    Step(cycle=3, commit={"logical": 1, "physical": 40}, read_idx=1),
    Step(
        cycle=4,
        rename={"logical": 1, "physical": 50},
        commit={"logical": 2, "physical": 41},
        read_idx=1,
    ),
    Step(
        cycle=5,
        rename={"logical": 4, "physical": 55},  # Should be ignored because of flush
        flush=True,
        read_idx=1,
    ),
    Step(
        cycle=6,
        rename={"logical": 3, "physical": 60},
        commit={"logical": 1, "physical": 50},
        read_idx=3,
    ),
    Step(cycle=7, read_idx=1),
]


class Driver(Module):
    def __init__(self):
        super().__init__(ports={})
        self.map_table = MapTable(num_logical=32, physical_bits=6)
        self.cycle = RegArray(UInt(32), 1, initializer=[0])

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        rename_en = Bits(1)(0)
        rename_idx = Bits(self.map_table.logical_bits)(0)
        rename_phy = Bits(self.map_table.physical_bits)(0)

        commit_en = Bits(1)(0)
        commit_idx = Bits(self.map_table.logical_bits)(0)
        commit_phy = Bits(self.map_table.physical_bits)(0)

        flush_flag = Bits(1)(0)
        read_idx = Bits(self.map_table.logical_bits)(0)

        for step in STEPS:
            cond = cycle_val == UInt(32)(step.cycle)
            if step.rename is not None:
                rename_en = cond.select(Bits(1)(1), rename_en)
                rename_idx = cond.select(
                    Bits(self.map_table.logical_bits)(step.rename["logical"]),
                    rename_idx,
                )
                rename_phy = cond.select(
                    Bits(self.map_table.physical_bits)(step.rename["physical"]),
                    rename_phy,
                )
            if step.commit is not None:
                commit_en = cond.select(Bits(1)(1), commit_en)
                commit_idx = cond.select(
                    Bits(self.map_table.logical_bits)(step.commit["logical"]),
                    commit_idx,
                )
                commit_phy = cond.select(
                    Bits(self.map_table.physical_bits)(step.commit["physical"]),
                    commit_phy,
                )
            if step.flush:
                flush_flag = cond.select(Bits(1)(1), flush_flag)
            read_idx = cond.select(
                Bits(self.map_table.logical_bits)(step.read_idx),
                read_idx,
            )

        rename_port = MapTableWriteEntry(
            enable=rename_en,
            logical_idx=rename_idx,
            physical_value=rename_phy,
        )
        commit_port = MapTableWriteEntry(
            enable=commit_en,
            logical_idx=commit_idx,
            physical_value=commit_phy,
        )

        self.map_table.build(
            rename_write=rename_port,
            commit_write=commit_port,
            flush_to_commit=flush_flag,
        )

        spec_read = self.map_table.read_spec(read_idx)
        commit_read = self.map_table.read_commit(read_idx)

        log(
            "cycle: {}, rename_en: {}, commit_en: {}, flush: {}, read_idx: {}, spec_read: {}, commit_read: {}, spec_state: {}, commit_state: {}",
            cycle_val,
            rename_en,
            commit_en,
            flush_flag,
            read_idx,
            spec_read,
            commit_read,
            self.map_table.spec_state(),
            self.map_table.commit_state(),
        )


def _pack_state(values):
    packed = 0
    for idx, val in enumerate(values):
        packed |= (val & 0x3F) << (idx * 6)
    return packed


def check(raw: str):
    lines = [line for line in raw.strip().split("\n") if line.strip()]
    history = {}

    for line in lines:
        if "cycle:" not in line:
            continue
        # Remove the prefix up to "cycle:"
        line = line[line.find("cycle:") :]
        parts = line.replace(",", "").split()
        data = {
            "cycle": int(parts[1]),
            "rename_en": int(parts[3]),
            "commit_en": int(parts[5]),
            "flush": int(parts[7]),
            "read_idx": int(parts[9]),
            "spec_read": int(parts[11]),
            "commit_read": int(parts[13]),
            "spec_state": int(parts[15]),
            "commit_state": int(parts[17]),
        }
        history[data["cycle"]] = data

    spec_state = [i for i in range(32)]
    commit_state = [i for i in range(32)]

    step_map = {step.cycle: step for step in STEPS}
    max_cycle = max(STEPS, key=lambda s: s.cycle).cycle

    for cycle in range(1, max_cycle + 1):
        log_entry = history.get(cycle)
        assert log_entry is not None, f"Missing log for cycle {cycle}"

        read_idx = log_entry["read_idx"]
        assert log_entry["spec_read"] == spec_state[read_idx], (
            f"Cycle {cycle}: expected spec read {spec_state[read_idx]}, got {log_entry['spec_read']}"
        )
        assert log_entry["commit_read"] == commit_state[read_idx], (
            f"Cycle {cycle}: expected commit read {commit_state[read_idx]}, got {log_entry['commit_read']}"
        )
        assert log_entry["spec_state"] == _pack_state(spec_state), f"Cycle {cycle}: spec state mismatch"
        assert log_entry["commit_state"] == _pack_state(commit_state), f"Cycle {cycle}: commit state mismatch"

        step = step_map.get(cycle)
        if step is None:
            continue

        if step.commit is not None:
            commit_state[step.commit["logical"]] = step.commit["physical"]
        if step.flush:
            spec_state = commit_state.copy()
        elif step.rename is not None:
            spec_state[step.rename["logical"]] = step.rename["physical"]


def test_map_table():
    sys = SysBuilder("test_map_table")
    with sys:
        driver = Driver()
        driver.build()

    sim, _ = elaborate(sys, verilog=True, verbose=False, sim_threshold=32)
    raw, _, stderr = run_quietly(run_simulator, sim)
    print(f"DEBUG: raw output:\n{raw}")
    print(f"DEBUG: stderr output:\n{stderr}")
    assert raw is not None, stderr
    check(raw)
