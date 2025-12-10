from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import re

from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator

from tests.utils import run_quietly
from r10k_cpu.downstreams.lsq import LSQ, LSQPushEntry
from r10k_cpu.common import LSQEntryType


@dataclass
class Step:
    cycle: int
    push: Optional[Dict[str, int]] = None
    pop: bool = False
    reg_ready: Optional[List[int]] = None
    issue_idx: Optional[int] = None
    check_idx: Optional[int] = None
    flush: bool = False


DEPTH = 4
STEPS = [
    Step(1, push={"is_load": 1, "is_store": 0, "op_type": 0, "imm": 0x100}),
    Step(2, push={"is_load": 0, "is_store": 1, "op_type": 1, "imm": 0x200}),
    Step(3, pop=True),
    Step(4, push={"is_load": 1, "is_store": 0, "op_type": 2, "imm": 0x300}, pop=True),
    Step(5, push={"is_load": 0, "is_store": 1, "op_type": 3, "imm": 0x400}),
    Step(6, pop=True),
    Step(7, push={"is_load": 1, "is_store": 0, "op_type": 4, "imm": 0x500}),
    Step(8, pop=True),
    Step(9, pop=True),
    # New steps for issue logic
    # Queue is empty here. Head=1, Tail=1.
    # Push Load A at idx 1. rs1=10, rs2=11 (from loop logic: idx=9 -> rd=10, rs1=11, rs2=12)
    # Actually let's check the loop logic in Driver.
    # push_rd = (idx + 1) % 64
    # push_rs1 = (idx + 2) % 64
    # push_rs2 = (idx + 3) % 64
    # Step index 9: rd=10, rs1=11, rs2=12. Load.
    Step(10, push={"is_load": 1, "is_store": 0, "op_type": 0, "imm": 0}), 
    # Step index 10: rd=11, rs1=12, rs2=13. Store.
    Step(11, push={"is_load": 0, "is_store": 1, "op_type": 0, "imm": 0}),
    
    # Load A (idx 1) needs rs1=11.
    # Store B (idx 2) needs rs1=12, rs2=13.
    
    Step(12, reg_ready=[11]), # Make Load A ready. Expect select A (idx 1).
    Step(13, reg_ready=[11], issue_idx=1), # Issue A.
    Step(14, reg_ready=[11]), # A issued. B not ready. Expect select None.
    Step(15, reg_ready=[11, 12, 13]), # Make B ready. Expect select B (idx 2).

    # New tests for is_store_before
    # Current state: Head=1, Tail=3. Queue: [?, Load(1), Store(2), ?].
    # Valid indices: 1, 2.
    
    # Case 1: Check Head (1). Range empty. Expect 0.
    Step(16, check_idx=1),
    
    # Case 2: Check Store (2). Range [1, 2) -> {1}. 1 is Load. Expect 0.
    Step(17, check_idx=2),
    
    # Case 3: Check Next (3). Range [1, 3) -> {1, 2}. 2 is Store. Expect 1.
    Step(18, check_idx=3),
    
    # Add more items to wrap.
    # Push Load at 3. Tail -> 0.
    Step(19, push={"is_load": 1, "is_store": 0, "op_type": 0, "imm": 0}),
    # Push Store at 0. Tail -> 1.
    Step(20, push={"is_load": 0, "is_store": 1, "op_type": 0, "imm": 0}),
    
    # State: Head=1, Tail=1 (Full? or Empty? Count=4).
    # Queue: 0:Store, 1:Load, 2:Store, 3:Load.
    # Order: 1, 2, 3, 0.
    
    # Case 4: Check index 3. Range [1, 3) -> {1, 2}. 2 is Store. Expect 1.
    Step(21, check_idx=3),
    
    # Case 5: Check index 0. Range [1, 0) (wrap) -> {1, 2, 3}. 2 is Store. Expect 1.
    Step(22, check_idx=0),
    
    # Case 6: Check index 1 (Head). Range [1, 1) -> Empty. Expect 0.
    Step(23, check_idx=1),
    
    # Case 7: Check index 2. Range [1, 2) -> {1}. 1 is Load. Expect 0.
    Step(24, check_idx=2),
    Step(25, flush=True),
    Step(26, push={"is_load": 1, "is_store": 0, "op_type": 0, "imm": 0}),
    Step(27, flush=True, push={"is_load": 0, "is_store": 1, "op_type": 0, "imm": 0}),
    Step(28),
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
        self.store_buffer = RegArray(LSQEntryType, 1, initializer=[0])

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        push_en = Bits(1)(0)
        pop_en = Bits(1)(0)
        push_is_load = Bits(1)(0)
        push_is_store = Bits(1)(0)
        push_op = Bits(3)(0)
        push_rd = Bits(6)(0)
        push_rs1 = Bits(6)(0)
        push_rs2 = Bits(6)(0)
        push_imm = Bits(32)(0)
        active_idx = Bits(5)(0)
        flush_en = Bits(1)(0)

        for idx, step in enumerate(STEPS):
            cond = cycle_val == UInt(32)(step.cycle)
            if step.push is not None:
                push_en = cond.select(Bits(1)(1), push_en)
                push_is_load = cond.select(Bits(1)(step.push["is_load"]), push_is_load)
                push_is_store = cond.select(Bits(1)(step.push["is_store"]), push_is_store)
                push_op = cond.select(Bits(3)(step.push["op_type"]), push_op)
                push_rd = cond.select(Bits(6)((idx + 1) % 64), push_rd)
                push_rs1 = cond.select(Bits(6)((idx + 2) % 64), push_rs1)
                push_rs2 = cond.select(Bits(6)((idx + 3) % 64), push_rs2)
                push_imm = cond.select(Bits(32)(step.push["imm"]), push_imm)
                active_idx = cond.select(Bits(5)(idx), active_idx)

            if step.pop:
                pop_en = cond.select(Bits(1)(1), pop_en)

            if step.flush:
                flush_en = cond.select(Bits(1)(1), flush_en)

        push_entry = LSQPushEntry(
            is_load=push_is_load,
            is_store=push_is_store,
            op_type=push_op,
            rd_physical=push_rd,
            rs1_physical=push_rs1,
            rs2_physical=push_rs2,
            imm=push_imm,
        )

        self.queue.build(push_en, push_entry, pop_en, active_idx, flush_en, self.store_buffer)

        # Issue logic
        issue_idx_val = Bits(self.queue.queue.addr_bits)(0)
        issue_en = Bits(1)(0)
        ready_indices_map = {}
        check_idx_val = Bits(self.queue.queue.addr_bits)(0)

        for step in STEPS:
            cond = cycle_val == UInt(32)(step.cycle)
            if step.issue_idx is not None:
                issue_en = cond.select(Bits(1)(1), issue_en)
                issue_idx_val = cond.select(Bits(self.queue.queue.addr_bits)(step.issue_idx), issue_idx_val)
            if step.reg_ready is not None:
                ready_indices_map[step.cycle] = step.reg_ready
            if step.check_idx is not None:
                check_idx_val = cond.select(Bits(self.queue.queue.addr_bits)(step.check_idx), check_idx_val)

        with Condition(issue_en):
            self.queue.mark_issued(issue_idx_val)

        is_store_before_res = self.queue.is_store_before(check_idx_val)

        class MockRegisterReady:
            def __init__(self, ready_indices_map, cycle_val):
                self.ready_indices_map = ready_indices_map
                self.cycle_val = cycle_val

            def __getitem__(self, index):
                is_ready = Bits(1)(0)
                for cycle, indices in self.ready_indices_map.items():
                    cond = self.cycle_val == UInt(32)(cycle)
                    cycle_ready = Bits(1)(0)
                    if indices:
                        for idx in indices:
                            cycle_ready = cycle_ready | (index == Bits(6)(idx))
                    is_ready = cond.select(cycle_ready, is_ready)
                return is_ready

            def read(self, index):
                return self.__getitem__(index)

        mock_ready = MockRegisterReady(ready_indices_map, cycle_val)
        selection = self.queue.select_first_ready(mock_ready)

        front_entry = self.queue.queue._dtype.view(self.queue.queue.front())

        log_str = (
            "cycle: {}, head: {}, tail: {}, count: {}, push_en: {}, pop_en: {}, "
            "front_valid: {}, front_queue_idx: {}, sel_valid: {}, sel_idx: {}, "
            "check_idx: {}, is_store_before: {}, contents: "
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
            selection.valid,
            selection.index,
            check_idx_val,
            is_store_before_res,
        ]

        for i in range(self.depth):
            entry = self.queue.queue._dtype.view(self.queue.queue[i])
            log_str += f"E{i}:{{}},{{}},{{}},{{}},{{}},{{}},{{}}; "
            args.extend(
                [
                    entry.valid,
                    entry.active_list_idx,
                    entry.lsq_queue_idx,
                    entry.is_load,
                    entry.is_store,
                    entry.imm,
                    entry.issued,
                ]
            )

        log(log_str, *args)


def parse_line(line: str) -> Optional[Dict[str, Any]]:
    base_match = re.search(
        r"cycle: (\d+), head: (\d+), tail: (\d+), count: (\d+), push_en: (\d+), pop_en: (\d+), "
        r"front_valid: (\d+), front_queue_idx: (\d+), sel_valid: (\d+), sel_idx: (\d+), "
        r"check_idx: (\d+), is_store_before: (\d+), contents: (.*)",
        line,
    )
    if not base_match:
        return None

    entry_block = base_match.group(13)
    entries: Dict[int, Dict[str, int]] = {}
    for match in re.finditer(r"E(\d+):([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+);", entry_block):
        idx = int(match.group(1))
        entries[idx] = {
            "valid": int(match.group(2)),
            "active_idx": int(match.group(3)),
            "queue_idx": int(match.group(4)),
            "is_load": int(match.group(5)),
            "is_store": int(match.group(6)),
            "imm": int(match.group(7)),
            "issued": int(match.group(8)),
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
        "sel_valid": int(base_match.group(9)),
        "sel_idx": int(base_match.group(10)),
        "check_idx": int(base_match.group(11)),
        "is_store_before": int(base_match.group(12)),
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
            "is_load": 0,
            "is_store": 0,
            "imm": 0,
            "issued": 0,
            "rs1": 0,
            "rs2": 0,
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
            assert log_entry["front_queue_idx"] == expected_front["queue_idx"], "Front idx mismatch"

        for i in range(DEPTH):
            logged = log_entry["entries"].get(i)
            stored = queue_storage[i]
            assert logged is not None, f"Missing entry log for slot {i}"
            for field, value in stored.items():
                if field in ["rs1", "rs2"]: continue
                assert logged[field if field != "queue_idx" else "queue_idx"] == value, (
                    f"Cycle {cycle}: slot {i}, field {field} mismatch"
                )

        step = step_map.get(cycle)
        
        # Check selection
        expected_sel_valid = 0
        expected_sel_idx = 0
        
        if step and step.reg_ready is not None:
            ready_regs = set(step.reg_ready)
            for i in range(count):
                idx = (head + i) % DEPTH
                entry = queue_storage[idx]

                if entry["issued"]:
                    continue

                if entry["is_store"]:
                    # LSQ only selects Loads, and Stores block subsequent Loads
                    break

                rs1_ok = entry["rs1"] in ready_regs

                if rs1_ok:
                    expected_sel_valid = 1
                    expected_sel_idx = idx
                    break
        
        assert log_entry["sel_valid"] == expected_sel_valid, f"Cycle {cycle}: expected sel_valid {expected_sel_valid}, got {log_entry['sel_valid']}"
        if expected_sel_valid:
            assert log_entry["sel_idx"] == expected_sel_idx, f"Cycle {cycle}: expected sel_idx {expected_sel_idx}, got {log_entry['sel_idx']}"

        # Check is_store_before
        if step and step.check_idx is not None:
            chk = step.check_idx
            expected_store_before = 0
            
            for i in range(DEPTH):
                # Check if i is between head and chk
                is_bet = False
                if head <= chk:
                    is_bet = head <= i < chk
                else:
                    is_bet = (head <= i) or (i < chk)
                
                if is_bet and queue_storage[i]["is_store"]:
                    expected_store_before = 1
                    break
            
            assert log_entry["is_store_before"] == expected_store_before, \
                f"Cycle {cycle}: expected is_store_before({chk})={expected_store_before}, got {log_entry['is_store_before']}"

        push = step.push if step else None
        pop = step.pop if step else False
        flush = step.flush if step else False

        if flush:
            head = 0
            tail = 0
            count = 0
        else:
            if step and step.issue_idx is not None:
                queue_storage[step.issue_idx]["issued"] = 1

            if push:
                idx = STEPS.index(step)
                entry = {
                    "valid": 1,
                    "active_idx": idx,
                    "queue_idx": tail % 32,
                    "is_load": push["is_load"],
                    "is_store": push["is_store"],
                    "imm": push["imm"],
                    "issued": 0,
                    "rs1": (idx + 2) % 64,
                    "rs2": (idx + 3) % 64,
                }
                queue_storage[tail] = entry
                tail = (tail + 1) % DEPTH

            if pop and count > 0:
                # queue_storage[head]["valid"] = 0
                head = (head + 1) % DEPTH

            if push and not pop:
                count += 1
            elif pop and not push and count > 0:
                count -= 1
            
    if step and step.issue_idx is not None:
        queue_storage[step.issue_idx]["issued"] = 1

    # assert count == 0, "Queue should be empty after scenario"


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
