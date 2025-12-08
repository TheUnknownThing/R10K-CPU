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
    snapshot: bool = False
    recover: bool = False

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
    steps: list[Step]

    def __init__(self, size: int, steps: list[Step]):
        super().__init__(ports={})
        self.free_list = FreeList(size)
        self.size = size
        self.cycle = RegArray(UInt(32), 1, initializer=[0])
        self.steps = steps

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        # Test Logic
        pop_enable = Bits(1)(0)
        push_enable = Bits(1)(0)
        push_data = Bits(self.free_list.queue._dtype.bits)(0)
        make_snapshot = Bits(1)(0)
        flush_recover = Bits(1)(0)

        for step in self.steps:
            cond = cycle_val == UInt(32)(step.cycle)

            if step.pop:
                pop_enable = cond.select(Bits(1)(1), pop_enable)
            
            if step.push is not None:
                push_enable = cond.select(Bits(1)(1), push_enable)
                push_data = cond.select(Bits(self.free_list.queue._dtype.bits)(step.push), push_data)
            
            if step.snapshot:
                make_snapshot = cond.select(Bits(1)(1), make_snapshot)
            
            if step.recover:
                flush_recover = cond.select(Bits(1)(1), flush_recover)

        self.free_list.build(pop_enable, push_enable, push_data, make_snapshot, flush_recover)
        
        # Outputs to check
        alloc_reg = self.free_list.free_reg()
        valid = self.free_list.valid()

        # Logging
        log_strings = (
            "cycle: {}, head: {}, tail: {}, count: {}, "
            "pop_en: {}, push_en: {}, push_data: {}, "
            "snapshot: {}, recover: {}, "
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
            make_snapshot,
            flush_recover,
            alloc_reg,
            valid,
        ]
        
        for i in range(self.size * 2):
            log_strings += "{}, "
            args.append(self.free_list.queue[i])

        log(log_strings, *args)

def parse_history(raw: str):
    print(raw)
    lines = raw.strip().split("\n")
    
    def parse_line(line):
        # cycle: 1, head: 0, tail: 0, count: 4, pop_en: 1, push_en: 0, push_data: 0, snapshot: 0, recover: 0, alloc_reg: 0, valid: 1, contents: 0, 1, 2, 3, ...
        m = re.search(r"cycle: (\d+), head: (\d+), tail: (\d+), count: (\d+), pop_en: (\d+), push_en: (\d+), push_data: (\d+), snapshot: (\d+), recover: (\d+), alloc_reg: (\d+), valid: (\d+), contents: (.*)", line)
        if m:
            base: dict[str, Any] = {
                "cycle": int(m.group(1)),
                "head": int(m.group(2)),
                "tail": int(m.group(3)),
                "count": int(m.group(4)),
                "pop_en": int(m.group(5)),
                "push_en": int(m.group(6)),
                "push_data": int(m.group(7)),
                "snapshot": int(m.group(8)),
                "recover": int(m.group(9)),
                "alloc_reg": int(m.group(10)),
                "valid": int(m.group(11)),
            }
            # Parse contents
            contents_str = m.group(12)
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
    return history

def check(raw: str):
    history = parse_history(raw)

    # Python Golden Model
    # FreeList(4) creates a queue of size 8 (double buffering).
    # Initialized with [1, 2, 3] (3 items).
    size = 8
    queue_storage = [0] * size
    queue_storage[0] = 1
    queue_storage[1] = 2
    queue_storage[2] = 3
    
    head = 0
    tail = 3
    count = 3
    
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
        driver = Driver(4, STEPS)
        driver.build()

    max_cycle = max(s.cycle for s in STEPS)
    sim, ver = elaborate(sys, verilog=True, verbose=False, sim_threshold=max_cycle + 5)

    raw, std_out, std_err = run_quietly(run_simulator, sim)
    assert raw is not None, std_err
    check(raw)

def test_free_list_snapshot():
    steps = [
        Step(1, pop=True),          # Alloc 1.
        Step(2, snapshot=True),     # Snapshot.
        Step(3, pop=True),          # Alloc 2.
        Step(4, push=1),            # Free 1.
        Step(5, recover=True),      # Recover.
        Step(6),                    # Idle.
    ]
    
    sys = SysBuilder("test_free_list_snapshot")
    with sys:
        driver = Driver(4, steps)
        driver.build()

    max_cycle = 10
    sim, ver = elaborate(sys, verilog=True, verbose=False, sim_threshold=max_cycle)
    raw, std_out, std_err = run_quietly(run_simulator, sim)
    assert raw is not None, std_err
    
    history = parse_history(raw)
    
    state_c2 = history[2]
    state_c6 = history[6]
    
    print(f"Cycle 2: {state_c2}")
    print(f"Cycle 6: {state_c6}")

    # Head should be restored
    assert state_c6["head"] == state_c2["head"], f"Head mismatch: {state_c6['head']} != {state_c2['head']}"
    
    # Tail should NOT be restored (it advanced due to push in cycle 4)
    # Initial tail=3. Push 1 item -> tail=4.
    assert state_c6["tail"] == 4, f"Tail mismatch: {state_c6['tail']} != 4"
    assert state_c6["tail"] != state_c2["tail"], "Tail should have advanced"
    
    # Count should be recalculated based on restored head and current tail
    # Head=1, Tail=4 -> Count=3
    assert state_c6["count"] == 3, f"Count mismatch: {state_c6['count']} != 3"
