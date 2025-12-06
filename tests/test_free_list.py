from dataclasses import dataclass
from typing import Any, Optional
from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator
from tests.utils import run_quietly
from r10k_cpu.downstreams.free_list import FreeList
import re

@dataclass
class Step:
    cycle: int
    pop: bool = False # Allocate
    push: Optional[int] = None # Free (push back)

# Test with 4 registers: 0, 1, 2, 3
# Register 0 is reserved, so FreeList manages 1, 2, 3.
# Initial state: [1, 2, 3], Head=0, Tail=0, Count=3
STEPS = [
    Step(1, pop=True),          # Alloc 1. State: [?, 2, 3], H=1, T=0, C=2
    Step(2, pop=True),          # Alloc 2. State: [?, ?, 3], H=2, T=0, C=1
    Step(3, pop=True),          # Alloc 3. State: [?, ?, ?], H=0, T=0, C=0 (Empty)
    Step(5, push=1),            # Free 1.  State: [1, ?, ?], H=0, T=1, C=1
    Step(6, push=2),            # Free 2.  State: [1, 2, ?], H=0, T=2, C=2
    Step(7, pop=True),          # Alloc 1. State: [?, 2, ?], H=1, T=2, C=1
    Step(8, push=3),            # Free 3.  State: [?, 2, 3], H=1, T=0, C=2
    Step(9, pop=True),          # Alloc 2. State: [?, ?, 3], H=2, T=0, C=1
    Step(10),                   # Idle
]

class Driver(Module):
    free_list: FreeList
    size: int
    cycle: Array

    def __init__(self, size: int):
        super().__init__(ports={})
        self.free_list = FreeList(size)
        self.size = size
        self.cycle = RegArray(UInt(32), 1, initializer=[0])

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        # Test Logic
        pop_enable = Bits(1)(0)
        push_enable = Bits(1)(0)
        push_data = Bits(self.free_list.queue._dtype.bits)(0)

        for step in STEPS:
            cond = cycle_val == UInt(32)(step.cycle)

            if step.pop:
                pop_enable = cond.select(Bits(1)(1), pop_enable)
            
            if step.push is not None:
                push_enable = cond.select(Bits(1)(1), push_enable)
                push_data = cond.select(Bits(self.free_list.queue._dtype.bits)(step.push), push_data)

        self.free_list.build(pop_enable, push_enable, push_data)
        
        # Outputs to check
        alloc_reg = self.free_list.free_reg()
        valid = self.free_list.valid()

        # Logging
        log_strings = (
            "cycle: {}, head: {}, tail: {}, count: {}, "
            "pop_en: {}, push_en: {}, push_data: {}, "
            "alloc_reg: {}, valid: {}, "
            "contents: "
        )
        
        args = [
            cycle_val,
            self.free_list.queue._head[0],
            self.free_list.queue._tail[0],
            self.free_list.queue.count(),
            pop_enable,
            push_enable,
            push_data,
            alloc_reg,
            valid,
        ]
        
        for i in range(self.size - 1):
            log_strings += "{}, "
            args.append(self.free_list.queue[i])

        log(log_strings, *args)

def check(raw: str):
    print(raw)
    lines = raw.strip().split("\n")
    
    def parse_line(line):
        # cycle: 1, head: 0, tail: 0, count: 4, pop_en: 1, push_en: 0, push_data: 0, alloc_reg: 0, valid: 1, contents: 0, 1, 2, 3, 
        m = re.search(r"cycle: (\d+), head: (\d+), tail: (\d+), count: (\d+), pop_en: (\d+), push_en: (\d+), push_data: (\d+), alloc_reg: (\d+), valid: (\d+), contents: (.*)", line)
        if m:
            base: dict[str, Any] = {
                "cycle": int(m.group(1)),
                "head": int(m.group(2)),
                "tail": int(m.group(3)),
                "count": int(m.group(4)),
                "pop_en": int(m.group(5)),
                "push_en": int(m.group(6)),
                "push_data": int(m.group(7)),
                "alloc_reg": int(m.group(8)),
                "valid": int(m.group(9)),
            }
            # Parse contents
            contents_str = m.group(10)
            # 0, 1, 2, 3, 
            items = [int(x.strip()) for x in contents_str.split(",") if x.strip()]
            base["contents"] = items
            return base
        return None

    history = {}
    for line in lines:
        data = parse_line(line)
        if data:
            history[data["cycle"]] = data

    # Python Golden Model
    size = 3
    # Initial state: [1, 2, 3]
    queue_storage = [i + 1 for i in range(size)]
    head = 0
    tail = 0 # In CircularQueue implementation, if count=size, tail == head usually.
    # Wait, let's check CircularQueue implementation details or infer from behavior.
    # If capacity is 4, and it's full.
    # If head=0. Tail usually points to next write location.
    # If full, tail == head? Or is there a separate count?
    # The CircularQueue implementation uses `count` register.
    # Tail is usually (head + count) % size.
    # So if head=0, count=4, tail=0.
    
    count = size
    
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
        
        expected_valid = 1 if count > 0 else 0
        assert log_entry["valid"] == expected_valid, f"Cycle {c}: Expected valid {expected_valid}, got {log_entry['valid']}"
        
        if count > 0:
            expected_alloc = queue_storage[head]
            assert log_entry["alloc_reg"] == expected_alloc, f"Cycle {c}: Expected alloc_reg {expected_alloc}, got {log_entry['alloc_reg']}"

        # Verify contents
        for i in range(size):
            expected_val = queue_storage[i]
            got_val = log_entry["contents"][i]
            assert got_val == expected_val, f"Cycle {c}, Index {i}: Expected val {expected_val}, got {got_val}"

        # 2. Apply operations for NEXT cycle
        step = step_map.get(c)
        
        pop_en = False
        push_en = False
        push_val = 0
        
        if step:
            pop_en = step.pop
            if step.push is not None:
                push_en = True
                push_val = step.push
            
        # Apply Push (Free)
        if push_en:
            queue_storage[tail] = push_val
            tail = (tail + 1) % size
            
        # Apply Pop (Allocate)
        if pop_en:
            head = (head + 1) % size
            
        # Update Count
        if push_en and not pop_en:
            count += 1
        elif pop_en and not push_en:
            count -= 1
            
    print("All checks passed!")

def test_free_list():
    sys = SysBuilder("test_free_list")
    with sys:
        driver = Driver(4)
        driver.build()

    max_cycle = max(s.cycle for s in STEPS)
    sim, ver = elaborate(sys, verilog=True, verbose=False, sim_threshold=max_cycle + 5)

    raw, std_out, std_err = run_quietly(run_simulator, sim)
    assert raw is not None, std_err
    check(raw)
