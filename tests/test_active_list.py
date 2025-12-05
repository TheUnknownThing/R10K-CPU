from dataclasses import dataclass
from typing import Any, Optional, Dict, Tuple
from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator
from tests.utils import run_quietly
from r10k_cpu.downstreams.active_list import ActiveList, InstructionPushEntry
import re


@dataclass
class Step:
    cycle: int
    push: Optional[Dict[str, int]] = None
    retire: bool = False
    set_ready: Optional[int] = None  # index to set ready


STEPS = [
    Step(
        1,
        push={
            "pc": 0x1000,
            "dest_logical": 1,
            "dest_new_physical": 10,
            "dest_old_physical": 1,
            "is_branch": 0,
            "predict_branch": 0,
        },
    ),
    Step(
        2,
        push={
            "pc": 0x1004,
            "dest_logical": 2,
            "dest_new_physical": 11,
            "dest_old_physical": 2,
            "is_branch": 0,
            "predict_branch": 0,
        },
    ),
    Step(
        3,
        push={
            "pc": 0x1008,
            "dest_logical": 3,
            "dest_new_physical": 12,
            "dest_old_physical": 3,
            "is_branch": 1,
            "predict_branch": 1,
        },
    ),
    Step(4, set_ready=0),  # Set first instruction ready. Index 0 (head)
    Step(5, retire=True),  # Retire first instruction
    Step(6, set_ready=1),  # Set second instruction ready. Index 1 (now head)
    Step(7, retire=True),  # Retire second instruction
    Step(
        8,
        push={
            "pc": 0x100C,
            "dest_logical": 4,
            "dest_new_physical": 13,
            "dest_old_physical": 4,
            "is_branch": 0,
            "predict_branch": 0,
        },
    ),
    Step(9, set_ready=2),  # Set third instruction ready. Index 2.
    Step(10, retire=True),  # Retire third instruction
    Step(11, set_ready=3),  # Set fourth instruction ready. Index 3.
    Step(12, retire=True),  # Retire fourth instruction
    Step(13),  # Idle
]


class Driver(Module):
    active_list: ActiveList
    depth: int
    cycle: Array

    def __init__(self, depth: int):
        super().__init__(ports={})
        self.active_list = ActiveList(depth)
        self.depth = depth
        self.cycle = RegArray(UInt(32), 1, initializer=[0])

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        # Test Logic
        push_valid = Bits(1)(0)
        push_pc = Bits(32)(0)
        push_dest_logical = Bits(5)(0)
        push_dest_new_physical = Bits(6)(0)
        push_dest_old_physical = Bits(6)(0)
        push_is_branch = Bits(1)(0)
        push_is_alu = Bits(1)(1)
        push_predict_branch = Bits(1)(0)

        pop_enable = Bits(1)(0)

        # set_ready logic
        set_ready_en = Bits(1)(0)
        set_ready_idx = Bits(self.active_list.queue.addr_bits)(0)

        for step in STEPS:
            cond = cycle_val == UInt(32)(step.cycle)

            if step.push is not None:
                push_valid = cond.select(Bits(1)(1), push_valid)
                push_pc = cond.select(Bits(32)(step.push["pc"]), push_pc)
                push_dest_logical = cond.select(Bits(5)(step.push["dest_logical"]), push_dest_logical)
                push_dest_new_physical = cond.select(Bits(6)(step.push["dest_new_physical"]), push_dest_new_physical)
                push_dest_old_physical = cond.select(Bits(6)(step.push["dest_old_physical"]), push_dest_old_physical)
                push_is_branch = cond.select(Bits(1)(step.push["is_branch"]), push_is_branch)
                push_is_alu = cond.select(Bits(1)(step.push.get("is_alu", 1)), push_is_alu)
                push_predict_branch = cond.select(Bits(1)(step.push["predict_branch"]), push_predict_branch)

            if step.retire:
                pop_enable = cond.select(Bits(1)(1), pop_enable)

            if step.set_ready is not None:
                set_ready_en = cond.select(Bits(1)(1), set_ready_en)
                set_ready_idx = cond.select(Bits(self.active_list.queue.addr_bits)(step.set_ready), set_ready_idx)

        push_inst = InstructionPushEntry(
            valid=push_valid,
            pc=push_pc,
            dest_logical=push_dest_logical,
            dest_new_physical=push_dest_new_physical,
            dest_old_physical=push_dest_old_physical,
            is_branch=push_is_branch,
            is_alu=push_is_alu,
            predict_branch=push_predict_branch,
        )

        self.active_list.build(push_inst, pop_enable)

        with Condition(set_ready_en):
            self.active_list.set_ready(set_ready_idx)

        # Logging
        log_strings = (
            "cycle: {}, head: {}, tail: {}, count: {}, "
            "push_valid: {}, pop_enable: {}, set_ready_en: {}, set_ready_idx: {}, "
            "front_pc: {}, front_ready: {}, "
            "contents: "
        )

        args = [
            cycle_val,
            self.active_list.queue._head[0],
            self.active_list.queue._tail[0],
            self.active_list.queue.count(),
            push_valid,
            pop_enable,
            set_ready_en,
            set_ready_idx,
            self.active_list.queue.front().pc,
            self.active_list.queue.front().ready,
        ]

        for i in range(self.depth):
            log_strings += "({}, {}), "
            entry = self.active_list.queue[i]
            args.append(entry.pc)
            args.append(entry.ready)

        log(log_strings, *args)


def check(raw: str):
    print(raw)
    lines = raw.strip().split("\n")

    def parse_line(line):
        # cycle: 1, head: 0, tail: 0, count: 0, push_valid: 0, pop_enable: 0, set_ready_en: 0, set_ready_idx: 0, front_pc: 0, front_ready: 0, contents: (0, 0), (0, 0), ...
        m = re.search(
            r"cycle: (\d+), head: (\d+), tail: (\d+), count: (\d+), push_valid: (\d+), pop_enable: (\d+), set_ready_en: (\d+), set_ready_idx: (\d+), front_pc: (\d+), front_ready: (\d+)",
            line,
        )
        if m:
            base: Dict[str, Any] = {
                "cycle": int(m.group(1)),
                "head": int(m.group(2)),
                "tail": int(m.group(3)),
                "count": int(m.group(4)),
                "push_valid": int(m.group(5)),
                "pop_enable": int(m.group(6)),
                "set_ready_en": int(m.group(7)),
                "set_ready_idx": int(m.group(8)),
                "front_pc": int(m.group(9)),
                "front_ready": int(m.group(10)),
            }
            # Parse contents
            contents_str = line.split("contents: ")[1]
            # (pc, ready), (pc, ready), ...
            # Use regex to find all pairs
            pairs = re.findall(r"\((\d+), (\d+)\)", contents_str)
            base["contents"] = [{"pc": int(p[0]), "ready": int(p[1])} for p in pairs]
            return base
        return None

    history = {}
    for line in lines:
        data = parse_line(line)
        if data:
            history[data["cycle"]] = data

    # Python Golden Model
    depth = 16
    queue_storage = [{"pc": 0, "ready": 0} for _ in range(depth)]
    head = 0
    tail = 0
    count = 0

    step_map = {s.cycle: s for s in STEPS}
    max_cycle = max(s.cycle for s in STEPS) + 1

    for c in range(1, max_cycle + 1):
        log_entry = history.get(c)
        if not log_entry:
            break

        print(f"Checking cycle {c}...")

        # 1. Verify current state
        assert log_entry["count"] == count, f"Cycle {c}: Expected count {count}, got {log_entry['count']}"
        assert log_entry["head"] == head, f"Cycle {c}: Expected head {head}, got {log_entry['head']}"
        assert log_entry["tail"] == tail, f"Cycle {c}: Expected tail {tail}, got {log_entry['tail']}"

        if count > 0:
            expected_front_pc = queue_storage[head]["pc"]
            expected_front_ready = queue_storage[head]["ready"]
            assert (
                log_entry["front_pc"] == expected_front_pc
            ), f"Cycle {c}: Expected front_pc {expected_front_pc}, got {log_entry['front_pc']}"
            assert (
                log_entry["front_ready"] == expected_front_ready
            ), f"Cycle {c}: Expected front_ready {expected_front_ready}, got {log_entry['front_ready']}"

        # Verify contents
        for i in range(depth):
            expected_pc = queue_storage[i]["pc"]
            expected_ready = queue_storage[i]["ready"]
            got_pc = log_entry["contents"][i]["pc"]
            got_ready = log_entry["contents"][i]["ready"]
            assert got_pc == expected_pc, f"Cycle {c}, Index {i}: Expected pc {expected_pc}, got {got_pc}"
            assert (
                got_ready == expected_ready
            ), f"Cycle {c}, Index {i}: Expected ready {expected_ready}, got {got_ready}"

        # 2. Apply operations for NEXT cycle
        step = step_map.get(c)

        push_data = None
        retire = False
        set_ready_idx = None

        if step:
            push_data = step.push
            retire = step.retire
            set_ready_idx = step.set_ready

        # Apply Set Ready (happens at end of cycle effectively for next cycle view, but in hardware it's a write)
        if set_ready_idx is not None:
            queue_storage[set_ready_idx]["ready"] = 1

        # Apply Push
        if push_data:
            queue_storage[tail]["pc"] = push_data["pc"]
            queue_storage[tail]["ready"] = 0  # Reset ready on new push
            tail = (tail + 1) % depth

        # Apply Retire (Pop)
        if retire:
            head = (head + 1) % depth

        # Update Count
        if push_data and not retire:
            count += 1
        elif retire and not push_data:
            count -= 1

    print("All checks passed!")


def test_active_list():
    sys = SysBuilder("test_active_list")
    with sys:
        driver = Driver(16)
        driver.build()

    max_cycle = max(s.cycle for s in STEPS)
    sim, ver = elaborate(sys, verilog=True, verbose=False, sim_threshold=max_cycle + 5)

    raw, std_out, std_err = run_quietly(run_simulator, sim)
    assert raw is not None, std_err
    check(raw)
