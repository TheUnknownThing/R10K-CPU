from dataclasses import dataclass
from typing import Optional, Tuple
from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator
from tests.utils import run_quietly
from dataclass.circular_queue import CircularQueue
import re


@dataclass
class Step:
    cycle: int
    push: Optional[int] = None
    pop: bool = False
    modify: Optional[Tuple[int, int]] = None  # (index, value)
    search: Optional[int] = None


STEPS = [
    Step(1, push=10),
    Step(2, push=20),
    Step(3, push=30),
    Step(4, pop=True),
    Step(5, modify=(1, 99)),
    Step(6, pop=True),
    Step(7, pop=True),
    Step(8, push=40),
    # New steps for full/empty/wrap/search testing
    Step(9, push=50),
    Step(10, push=60),
    Step(11, push=70),
    Step(12, push=80),
    Step(13, push=90),
    Step(14, push=100),  # Wraps here
    Step(15, push=110),
    Step(16, push=120),
    Step(17, push=130),  # Full
    Step(18, search=40),  # Head
    Step(19, search=130),  # Tail
    Step(20, search=999),  # Not found
    Step(21, pop=True),  # Pop 40
    Step(22, search=40),  # Should not find
    # Emptying
    Step(23, pop=True),
    Step(24, pop=True),
    Step(25, pop=True),
    Step(26, pop=True),
    Step(27, pop=True),
    Step(28, pop=True),
    Step(29, pop=True),
    Step(30, pop=True),
    Step(31, pop=True),  # Should be empty now
    Step(32),  # Check empty
]

record = Record(a=UInt(10), b=UInt(10))


class Driver(Module):
    queue: CircularQueue
    size: int
    cycle: Array

    def __init__(self, size: int):
        super().__init__(ports={})
        self.queue = CircularQueue(record, size)
        self.size = size
        self.cycle = RegArray(UInt(32), 1, initializer=[0])

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        # Test Logic
        push_enable = Bits(1)(0)
        push_data = UInt(10)(0)
        pop_enable = Bits(1)(0)
        search_target = UInt(10)(0)

        for step in STEPS:
            cond = cycle_val == UInt(32)(step.cycle)

            if step.push is not None:
                push_enable = cond.select(Bits(1)(1), push_enable)
                push_data = cond.select(UInt(10)(step.push), push_data)

            if step.pop:
                pop_enable = cond.select(Bits(1)(1), pop_enable)

            if step.modify is not None:
                idx, val = step.modify
                with Condition(cond):
                    self.queue[UInt(self.queue.addr_bits)(idx)] = record.bundle(a=UInt(10)(val), b=UInt(10)(0))

            if step.search is not None:
                search_target = cond.select(UInt(10)(step.search), search_target)

        pop_data = self.queue.operate(
            push_enable=push_enable, push_data=record.bundle(a=push_data, b=UInt(10)(0)), pop_enable=pop_enable
        )
        selection = self.queue.choose(lambda x: x.a == search_target)

        log_strings = (
            "cycle: {}, head: {}, tail: {}, count: {}, is_full: {}, is_empty:{}, front: {}, pop_data: {}, "
            "sel_valid: {}, sel_idx: {}, sel_dist: {}, sel_data: {}, "
            "content: "
        )
        for _ in range(self.size):
            log_strings += "{}, "
        contents = [self.queue[i].a for i in range(self.size)]
        log(
            log_strings,
            cycle_val,
            self.queue._head[0],
            self.queue._tail[0],
            self.queue.count(),
            self.queue.is_full(),
            self.queue.is_empty(),
            self.queue.front().a,
            pop_data.a,
            selection.valid,
            selection.index,
            selection.distance,
            selection.data.a,
            *contents,
        )


def check(raw: str):
    print(raw)
    # Parse the output and verify
    lines = raw.strip().split("\n")

    # Helper to parse a line
    def parse_line(line):
        # Example: cycle: 1, head: 0, tail: 0, count: 0, is_full: 0, is_empty:1, front: 0, pop_data: 0, sel_valid: 0, sel_idx: 0, sel_dist: 0, sel_data: 0, content: 0, 0, ...
        m = re.search(
            r"cycle: (\d+), head: (\d+), tail: (\d+), count: (\d+), is_full: (\d+), is_empty:(\d+), front: (\d+), pop_data: (\d+), sel_valid: (\d+), sel_idx: (\d+), sel_dist: (\d+), sel_data: (\d+)",
            line,
        )
        if m:
            return {
                "cycle": int(m.group(1)),
                "head": int(m.group(2)),
                "tail": int(m.group(3)),
                "count": int(m.group(4)),
                "is_full": int(m.group(5)),
                "is_empty": int(m.group(6)),
                "front": int(m.group(7)),
                "pop_data": int(m.group(8)),
                "sel_valid": int(m.group(9)),
                "sel_idx": int(m.group(10)),
                "sel_dist": int(m.group(11)),
                "sel_data": int(m.group(12)),
            }
        return None

    history = {}
    for line in lines:
        data = parse_line(line)
        if data:
            history[data["cycle"]] = data

    # Python Golden Model Simulation
    queue_storage = [0] * 10
    head = 0
    tail = 0
    count = 0

    step_map = {s.cycle: s for s in STEPS}
    max_cycle = max(s.cycle for s in STEPS) + 1

    for c in range(1, max_cycle + 1):
        log_entry = history.get(c)
        if not log_entry:
            # If simulation stopped early or we don't have log for this cycle
            break

        print(f"Checking cycle {c}...")

        # 1. Verify current state (Result of previous cycles)
        assert log_entry["count"] == count, f"Cycle {c}: Expected count {count}, got {log_entry['count']}"
        assert log_entry["head"] == head, f"Cycle {c}: Expected head {head}, got {log_entry['head']}"
        assert log_entry["tail"] == tail, f"Cycle {c}: Expected tail {tail}, got {log_entry['tail']}"
        assert log_entry["is_full"] == int(
            count == 10
        ), f"Cycle {c}: Expected is_full {int(count == 10)}, got {log_entry['is_full']}"
        assert log_entry["is_empty"] == int(
            count == 0
        ), f"Cycle {c}: Expected is_empty {int(count == 0)}, got {log_entry['is_empty']}"

        if count > 0:
            expected_front = queue_storage[head]
            assert (
                log_entry["front"] == expected_front
            ), f"Cycle {c}: Expected front {expected_front}, got {log_entry['front']}"

        # 2. Apply operations for this cycle to update state for NEXT cycle
        step = step_map.get(c)

        # Default values if no step
        push_val = None
        pop_en = False
        modify_op = None

        if step:
            push_val = step.push
            pop_en = step.pop
            modify_op = step.modify

            # Check Search
            if step.search is not None:
                target = step.search
                found = False
                found_idx = 0
                found_dist = 0

                curr = head
                for dist in range(count):
                    if queue_storage[curr] == target:
                        found = True
                        found_idx = curr
                        found_dist = dist
                        break
                    curr = (curr + 1) % 10

                assert log_entry["sel_valid"] == int(
                    found
                ), f"Cycle {c}: Expected sel_valid {int(found)}, got {log_entry['sel_valid']}"
                if found:
                    assert (
                        log_entry["sel_idx"] == found_idx
                    ), f"Cycle {c}: Expected sel_idx {found_idx}, got {log_entry['sel_idx']}"
                    assert (
                        log_entry["sel_dist"] == found_dist
                    ), f"Cycle {c}: Expected sel_dist {found_dist}, got {log_entry['sel_dist']}"
                    assert (
                        log_entry["sel_data"] == target
                    ), f"Cycle {c}: Expected sel_data {target}, got {log_entry['sel_data']}"
                else:
                    assert log_entry["sel_valid"] == 0

        # Check pop_data (combinational output of operate)
        # operate returns storage[head]
        expected_pop_data = queue_storage[head]
        assert (
            log_entry["pop_data"] == expected_pop_data
        ), f"Cycle {c}: Expected pop_data {expected_pop_data}, got {log_entry['pop_data']}"

        # Apply Modify (RegArray write happens at end of cycle)
        if modify_op:
            idx, val = modify_op
            queue_storage[idx] = val

        # Apply Push (RegArray write happens at end of cycle)
        if push_val is not None:
            queue_storage[tail] = push_val
            tail = (tail + 1) % 10

        # Apply Pop (Head update happens at end of cycle)
        if pop_en:
            head = (head + 1) % 10

        # Update Count
        if push_val is not None and not pop_en:
            count += 1
        elif pop_en and push_val is None:
            count -= 1
        # If both push and pop, count remains same

    print("All checks passed!")


def test_circular_queue():
    sys = SysBuilder("test_circular_queue")
    with sys:
        driver = Driver(10)
        driver.build()

    max_cycle = max(s.cycle for s in STEPS)
    sim, ver = elaborate(sys, verilog=True, verbose=False, sim_threshold=max_cycle + 5)

    raw, std_out, std_err = run_quietly(run_simulator, sim)
    assert raw is not None, std_err
    check(raw)
