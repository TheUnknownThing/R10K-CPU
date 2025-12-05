from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple
import re

from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator

from tests.utils import run_quietly
from r10k_cpu.downstreams.active_list import ActiveList, InstructionPushEntry
from r10k_cpu.modules.commit import Commit


@dataclass
class Step:
    cycle: int
    push: Optional[Dict[str, int]] = None
    set_ready: Optional[int] = None
    set_actual_branch: Optional[Tuple[int, int]] = None


DEPTH = 8
STEPS = [
    Step(1, push={"pc": 0x100, "dest_logical": 1, "dest_new": 40, "dest_old": 1, "is_branch": 0, "is_alu": 1, "predict_branch": 0}),
    Step(2, push={"pc": 0x104, "dest_logical": 2, "dest_new": 41, "dest_old": 2, "is_branch": 0, "is_alu": 0, "predict_branch": 0}),
    Step(3, push={"pc": 0x108, "dest_logical": 3, "dest_new": 42, "dest_old": 3, "is_branch": 1, "is_alu": 1, "predict_branch": 0}),
    Step(4, set_ready=0),
    Step(5, set_ready=1),
    Step(6, set_ready=2, set_actual_branch=(2, 1)),
    Step(7, push={"pc": 0x10C, "dest_logical": 4, "dest_new": 43, "dest_old": 4, "is_branch": 0, "is_alu": 1, "predict_branch": 0}),
    Step(8, set_ready=3),
]


class Driver(Module):
    def __init__(self, depth: int):
        super().__init__(ports={})
        self.active_list = ActiveList(depth)
        self.commit = Commit()
        self.depth = depth
        self.cycle = RegArray(UInt(32), 1, initializer=[0])
        self.map_table_0 = RegArray(Bits(6), 32, initializer=[i for i in range(32)])
        self.map_table_1 = RegArray(Bits(6), 32, initializer=[i for i in range(32)])
        self.map_table_active = RegArray(Bits(1), 1, initializer=[0])

    def _set_actual_branch(self, index: Value, value: Value):
        bundle = self.active_list.queue[index]
        updated = self.active_list.queue._dtype.bundle(
            pc=bundle.pc,
            dest_logical=bundle.dest_logical,
            dest_new_physical=bundle.dest_new_physical,
            dest_old_physical=bundle.dest_old_physical,
            ready=bundle.ready,
            is_branch=bundle.is_branch,
            is_alu=bundle.is_alu,
            predict_branch=bundle.predict_branch,
            actual_branch=value,
        )
        self.active_list.queue[index] = updated

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        push_valid = Bits(1)(0)
        push_pc = Bits(32)(0)
        push_dest_logical = Bits(5)(0)
        push_dest_new = Bits(6)(0)
        push_dest_old = Bits(6)(0)
        push_is_branch = Bits(1)(0)
        push_is_alu = Bits(1)(0)
        push_predict = Bits(1)(0)

        set_ready_en = Bits(1)(0)
        set_ready_idx = Bits(self.active_list.queue.addr_bits)(0)
        set_actual_en = Bits(1)(0)
        set_actual_idx = Bits(self.active_list.queue.addr_bits)(0)
        set_actual_val = Bits(1)(0)

        for step in STEPS:
            cond = cycle_val == UInt(32)(step.cycle)
            if step.push is not None:
                push_valid = cond.select(Bits(1)(1), push_valid)
                push_pc = cond.select(Bits(32)(step.push["pc"]), push_pc)
                push_dest_logical = cond.select(Bits(5)(step.push["dest_logical"]), push_dest_logical)
                push_dest_new = cond.select(Bits(6)(step.push["dest_new"]), push_dest_new)
                push_dest_old = cond.select(Bits(6)(step.push["dest_old"]), push_dest_old)
                push_is_branch = cond.select(Bits(1)(step.push["is_branch"]), push_is_branch)
                push_is_alu = cond.select(Bits(1)(step.push["is_alu"]), push_is_alu)
                push_predict = cond.select(Bits(1)(step.push["predict_branch"]), push_predict)

            if step.set_ready is not None:
                set_ready_en = cond.select(Bits(1)(1), set_ready_en)
                set_ready_idx = cond.select(Bits(self.active_list.queue.addr_bits)(step.set_ready), set_ready_idx)

            if step.set_actual_branch is not None:
                idx, value = step.set_actual_branch
                set_actual_en = cond.select(Bits(1)(1), set_actual_en)
                set_actual_idx = cond.select(Bits(self.active_list.queue.addr_bits)(idx), set_actual_idx)
                set_actual_val = cond.select(Bits(1)(value), set_actual_val)

        push_entry = InstructionPushEntry(
            valid=push_valid,
            pc=push_pc,
            dest_logical=push_dest_logical,
            dest_new_physical=push_dest_new,
            dest_old_physical=push_dest_old,
            is_branch=push_is_branch,
            is_alu=push_is_alu,
            predict_branch=push_predict,
        )

        with Condition(set_actual_en):
            self._set_actual_branch(set_actual_idx, set_actual_val)

        with Condition(set_ready_en):
            self.active_list.set_ready(set_ready_idx)

        pop_instruction, old_physical, is_alu = self.commit.build(
            active_list_queue=self.active_list.queue,
            map_table_active=self.map_table_active,
            map_table_0=self.map_table_0,
            map_table_1=self.map_table_1,
        )

        self.active_list.build(push_entry, pop_instruction)

        log_str = (
            "cycle: {}, head: {}, tail: {}, count: {}, push_valid: {}, pop_instruction: {}, "
            "old_physical: {}, is_alu: {}, map_active: {}, "
            "mt0_r1: {}, mt0_r2: {}, mt0_r3: {}, mt0_r4: {}, "
            "mt1_r1: {}, mt1_r2: {}, mt1_r3: {}, mt1_r4: {}"
        )

        args = [
            cycle_val,
            self.active_list.queue._head[0],
            self.active_list.queue._tail[0],
            self.active_list.queue.count(),
            push_valid,
            pop_instruction,
            old_physical,
            is_alu,
            self.map_table_active[0],
        ]

        for i in range(1, 5):
            args.append(self.map_table_0[i])
        for i in range(1, 5):
            args.append(self.map_table_1[i])

        log(log_str, *args)


def parse_line(line: str) -> Optional[Dict[str, Any]]:
    pattern = (
    r"cycle: (\d+), head: (\d+), tail: (\d+), count: (\d+), push_valid: (\d+), pop_instruction: (\d+), "
    r"old_physical: (\d+), is_alu: (\d+), map_active: (\d+), "
        r"mt0_r1: (\d+), mt0_r2: (\d+), mt0_r3: (\d+), mt0_r4: (\d+), "
        r"mt1_r1: (\d+), mt1_r2: (\d+), mt1_r3: (\d+), mt1_r4: (\d+)"
    )
    match = re.search(pattern, line)
    if not match:
        return None

    values = list(map(int, match.groups()))
    return {
        "cycle": values[0],
        "head": values[1],
        "tail": values[2],
        "count": values[3],
        "push_valid": values[4],
        "pop_instruction": values[5],
        "old_physical": values[6],
        "is_alu": values[7],
    "map_active": values[8],
    "mt0": values[9:13],
    "mt1": values[13:17],
    }


def check(raw: str):
    lines = raw.strip().split("\n")
    history: Dict[int, Dict[str, Any]] = {}
    for line in lines:
        parsed = parse_line(line)
        if parsed:
            history[parsed["cycle"]] = parsed

    queue_storage: List[Dict[str, int]] = [
        {
            "dest_logical": 0,
            "dest_new": 0,
            "dest_old": 0,
            "is_branch": 0,
            "is_alu": 0,
            "predict_branch": 0,
            "actual_branch": 0,
            "ready": 0,
        }
        for _ in range(DEPTH)
    ]
    head = 0
    tail = 0
    count = 0

    map_table_0 = [i for i in range(32)]
    map_table_1 = [i for i in range(32)]
    map_active = 0

    step_map = {step.cycle: step for step in STEPS}
    max_cycle = max(step.cycle for step in STEPS) + 2

    for cycle in range(1, max_cycle + 1):
        log_entry = history.get(cycle)
        if not log_entry:
            continue

        step = step_map.get(cycle)

        if step and step.set_actual_branch is not None:
            idx, value = step.set_actual_branch
            queue_storage[idx]["actual_branch"] = value

        if step and step.set_ready is not None:
            queue_storage[step.set_ready]["ready"] = 1

        pop_expected = 1 if count > 0 and queue_storage[head]["ready"] == 1 else 0

        assert log_entry["head"] == head, f"Cycle {cycle}: head mismatch"
        assert log_entry["tail"] == tail, f"Cycle {cycle}: tail mismatch"
        assert log_entry["count"] == count, f"Cycle {cycle}: count mismatch"
        assert log_entry["pop_instruction"] == pop_expected, f"Cycle {cycle}: pop signal mismatch"

        count_delta = 0

        if pop_expected:
            entry = queue_storage[head]
            assert log_entry["old_physical"] == entry["dest_old"], f"Cycle {cycle}: old physical mismatch"
            assert log_entry["is_alu"] == entry["is_alu"], f"Cycle {cycle}: is_alu mismatch"

            target_table = map_table_0 if map_active == 0 else map_table_1
            target_table[entry["dest_logical"]] = entry["dest_new"]

            mispredict = entry["is_branch"] == 1 and entry["predict_branch"] != entry["actual_branch"]
            if mispredict:
                map_active = 1 - map_active

            head = (head + 1) % DEPTH
            count_delta -= 1
        else:
            if count > 0:
                assert (
                    log_entry["old_physical"] == queue_storage[head]["dest_old"]
                ), f"Cycle {cycle}: old physical should reflect front entry"

        if step and step.push is not None:
            entry = {
                "dest_logical": step.push["dest_logical"],
                "dest_new": step.push["dest_new"],
                "dest_old": step.push["dest_old"],
                "is_branch": step.push["is_branch"],
                "is_alu": step.push["is_alu"],
                "predict_branch": step.push["predict_branch"],
                "actual_branch": 0,
                "ready": 0,
            }
            queue_storage[tail] = entry
            tail = (tail + 1) % DEPTH
            count_delta += 1

        count += count_delta

        expected_mt0 = [map_table_0[i] for i in range(1, 5)]
        expected_mt1 = [map_table_1[i] for i in range(1, 5)]
        assert log_entry["mt0"] == expected_mt0, f"Cycle {cycle}: map_table_0 mismatch"
        assert log_entry["mt1"] == expected_mt1, f"Cycle {cycle}: map_table_1 mismatch"
        assert log_entry["map_active"] == map_active, f"Cycle {cycle}: map_active mismatch"

    assert count == 0, "All instructions should retire by end of scenario"


def test_commit_stage_behavior():
    sys = SysBuilder("commit_stage_test")
    with sys:
        driver = Driver(DEPTH)
        driver.build()

    max_cycle = max(step.cycle for step in STEPS)
    sim, _ = elaborate(sys, verilog=True, verbose=False, sim_threshold=max_cycle + 5)

    raw, std_out, std_err = run_quietly(run_simulator, sim)
    assert raw is not None, std_err
    check(raw)
