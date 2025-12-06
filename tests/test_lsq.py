from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import re

from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator

from tests.utils import run_quietly
from r10k_cpu.downstreams.lsq import LSQ, LSQPushEntry


@dataclass
class Step:
    cycle: int
    push: Optional[Dict[str, int]] = None
    pop: bool = False


DEPTH = 4
STEPS = [
    Step(1, push={"address": 0x1000, "data": 0xAAAA_BBBB, "is_load": 1, "is_store": 0, "op_type": 0}),
    Step(2, push={"address": 0x1004, "data": 0xCCCC_DDDD, "is_load": 0, "is_store": 1, "op_type": 1}),
    Step(3, pop=True),
    Step(4, push={"address": 0x2000, "data": 0x1111_2222, "is_load": 1, "is_store": 0, "op_type": 2}, pop=True),
    Step(5, push={"address": 0x2004, "data": 0x3333_4444, "is_load": 0, "is_store": 1, "op_type": 3}),
    Step(6, pop=True),
    Step(7, push={"address": 0x3000, "data": 0x5555_6666, "is_load": 1, "is_store": 0, "op_type": 4}),
    Step(8, pop=True),
    Step(9, pop=True),
]


class Driver(Module):
    queue: LSQ
    depth: int
    cycle: Array

    def __init__(self, depth: int):
        super().__init__(ports={})
        self.queue = LSQ(depth)
        self.depth = depth
        self.cycle = RegArray(UInt(32), 1, initializer=[0])

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        push_en = Bits(1)(0)
        pop_en = Bits(1)(0)
        push_addr = Bits(32)(0)
        push_data = Bits(32)(0)
        push_is_load = Bits(1)(0)
        push_is_store = Bits(1)(0)
        push_op = Bits(3)(0)
        push_rd = Bits(6)(0)
        push_rs1 = Bits(6)(0)
        push_rs2 = Bits(6)(0)
        push_rs1_needed = Bits(1)(1)
        push_rs2_needed = Bits(1)(1)
        active_idx = Bits(5)(0)

        for idx, step in enumerate(STEPS):
            cond = cycle_val == UInt(32)(step.cycle)
            if step.push is not None:
                push_en = cond.select(Bits(1)(1), push_en)
                push_addr = cond.select(Bits(32)(step.push["address"]), push_addr)
                push_data = cond.select(Bits(32)(step.push["data"]), push_data)
                push_is_load = cond.select(Bits(1)(step.push["is_load"]), push_is_load)
                push_is_store = cond.select(Bits(1)(step.push["is_store"]), push_is_store)
                push_op = cond.select(Bits(3)(step.push["op_type"]), push_op)
                push_rd = cond.select(Bits(6)((idx + 1) % 64), push_rd)
                push_rs1 = cond.select(Bits(6)((idx + 2) % 64), push_rs1)
                push_rs2 = cond.select(Bits(6)((idx + 3) % 64), push_rs2)
                push_rs1_needed = cond.select(Bits(1)(1), push_rs1_needed)
                push_rs2_needed = cond.select(Bits(1)(1), push_rs2_needed)
                active_idx = cond.select(Bits(5)(idx), active_idx)

            if step.pop:
                pop_en = cond.select(Bits(1)(1), pop_en)

        push_entry = LSQPushEntry(
            address=push_addr,
            data=push_data,
            is_load=push_is_load,
            is_store=push_is_store,
            op_type=push_op,
            rd_physical=push_rd,
            rs1_physical=push_rs1,
            rs2_physical=push_rs2,
            rs1_needed=push_rs1_needed,
            rs2_needed=push_rs2_needed,
        )

        self.queue.build(push_en, push_entry, pop_en, active_idx)

        front_entry = self.queue.queue._dtype.view(self.queue.queue.front())

        log_str = (
            "cycle: {}, head: {}, tail: {}, count: {}, push_en: {}, pop_en: {}, "
            "front_valid: {}, front_queue_idx: {}, front_addr: {}, contents: "
        )

        args = [
            cycle_val,
            self.queue.queue._head[0],
            self.queue.queue._tail[0],
            self.queue.queue.count(),
            push_en,
            pop_en,
            front_entry.valid,
            front_entry.lsq_queue_idx,
            front_entry.address,
        ]

        for i in range(self.depth):
            entry = self.queue.queue._dtype.view(self.queue.queue[i])
            log_str += f"E{i}:{{}},{{}},{{}},{{}},{{}},{{}},{{}}; "
            args.extend(
                [
                    entry.valid,
                    entry.active_list_idx,
                    entry.lsq_queue_idx,
                    entry.address,
                    entry.data,
                    entry.is_load,
                    entry.is_store,
                ]
            )

        log(log_str, *args)


def parse_line(line: str) -> Optional[Dict[str, Any]]:
    base_match = re.search(
        r"cycle: (\d+), head: (\d+), tail: (\d+), count: (\d+), push_en: (\d+), pop_en: (\d+), "
        r"front_valid: (\d+), front_queue_idx: (\d+), front_addr: (\d+), contents: (.*)",
        line,
    )
    if not base_match:
        return None

    entry_block = base_match.group(10)
    entries: Dict[int, Dict[str, int]] = {}
    for match in re.finditer(r"E(\d+):([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+);", entry_block):
        idx = int(match.group(1))
        entries[idx] = {
            "valid": int(match.group(2)),
            "active_idx": int(match.group(3)),
            "queue_idx": int(match.group(4)),
            "address": int(match.group(5)),
            "data": int(match.group(6)),
            "is_load": int(match.group(7)),
            "is_store": int(match.group(8)),
        }

    return {
        "cycle": int(base_match.group(1)),
        "head": int(base_match.group(2)),
        "tail": int(base_match.group(3)),
        "count": int(base_match.group(4)),
        "push_en": int(base_match.group(5)),
        "pop_en": int(base_match.group(6)),
        "front_valid": int(base_match.group(7)),
        "front_queue_idx": int(base_match.group(8)),
        "front_addr": int(base_match.group(9)),
        "entries": entries,
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
            "valid": 0,
            "active_idx": 0,
            "queue_idx": 0,
            "address": 0,
            "data": 0,
            "is_load": 0,
            "is_store": 0,
        }
        for _ in range(DEPTH)
    ]
    head = 0
    tail = 0
    count = 0

    step_map = {step.cycle: step for step in STEPS}
    max_cycle = max(step.cycle for step in STEPS) + 2

    for cycle in range(1, max_cycle + 1):
        log_entry = history.get(cycle)
        if not log_entry:
            continue

        assert log_entry["head"] == head, f"Cycle {cycle}: head mismatch"
        assert log_entry["tail"] == tail, f"Cycle {cycle}: tail mismatch"
        assert log_entry["count"] == count, f"Cycle {cycle}: count mismatch"

        if count > 0:
            expected_front = queue_storage[head]
            assert log_entry["front_valid"] == expected_front["valid"], "Front valid mismatch"
            assert log_entry["front_addr"] == expected_front["address"], "Front addr mismatch"
            assert log_entry["front_queue_idx"] == expected_front["queue_idx"], "Front idx mismatch"

        for i in range(DEPTH):
            logged = log_entry["entries"].get(i)
            stored = queue_storage[i]
            assert logged is not None, f"Missing entry log for slot {i}"
            for field, value in stored.items():
                assert logged[field if field != "queue_idx" else "queue_idx"] == value, (
                    f"Cycle {cycle}: slot {i}, field {field} mismatch"
                )

        step = step_map.get(cycle)
        push = step.push if step else None
        pop = step.pop if step else False

        if push:
            entry = {
                "valid": 1,
                "active_idx": STEPS.index(step),
                "queue_idx": (tail + 1) % 32,
                "address": push["address"],
                "data": push["data"],
                "is_load": push["is_load"],
                "is_store": push["is_store"],
            }
            queue_storage[tail] = entry
            tail = (tail + 1) % DEPTH

        if pop and count > 0:
            head = (head + 1) % DEPTH

        if push and not pop:
            count += 1
        elif pop and not push and count > 0:
            count -= 1

    assert count == 0, "Queue should be empty after scenario"


def test_lsq_behavior():
    sys = SysBuilder("lsq_test")
    with sys:
        driver = Driver(DEPTH)
        driver.build()

    max_cycle = max(step.cycle for step in STEPS)
    sim, _ = elaborate(sys, verilog=True, verbose=False, sim_threshold=max_cycle + 5)

    raw, std_out, std_err = run_quietly(run_simulator, sim)
    assert raw is not None, std_err
    check(raw)
