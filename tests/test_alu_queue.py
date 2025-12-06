from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import re

from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator

from tests.utils import run_quietly
from r10k_cpu.downstreams.alu_queue import ALUQueue, ALUQueuePushEntry


@dataclass
class Step:
    cycle: int
    push: Optional[Dict[str, int]] = None
    pop: bool = False


DEPTH = 4
STEPS = [
    Step(1, push={"rs1": 1, "rs2": 2, "rd": 10, "alu_op": 1, "imm": 0x10, "active_idx": 3, "pc": 0x1000, "op1_from": 0, "op2_from": 1}),
    Step(2, push={"rs1": 4, "rs2": 5, "rd": 11, "alu_op": 2, "imm": 0x20, "active_idx": 4, "pc": 0x1004, "op1_from": 0, "op2_from": 2}), # op2 from IMM
    Step(3, pop=True),
    Step(4, push={"rs1": 6, "rs2": 7, "rd": 12, "alu_op": 3, "imm": 0x30, "active_idx": 5, "pc": 0x1008, "is_branch": 1}, pop=True),
    Step(5, push={"rs1": 8, "rs2": 9, "rd": 13, "alu_op": 4, "imm": 0x40, "active_idx": 6, "pc": 0x100C}),
    Step(6, pop=True),
    Step(7, pop=True),
    Step(8, push={"rs1": 10, "rs2": 11, "rd": 14, "alu_op": 5, "imm": 0x50, "active_idx": 7, "pc": 0x1010}),
    Step(9, pop=True),
]


class Driver(Module):
    queue: ALUQueue
    depth: int
    cycle: Array

    def __init__(self, depth: int):
        super().__init__(ports={})
        self.queue = ALUQueue(depth)
        self.depth = depth
        self.cycle = RegArray(UInt(32), 1, initializer=[0])

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]

        push_en = Bits(1)(0)
        pop_en = Bits(1)(0)
        push_rs1 = Bits(6)(0)
        push_rs2 = Bits(6)(0)
        push_rd = Bits(6)(0)
        push_op = Bits(4)(0)
        push_imm = Bits(32)(0)
        push_op1_from = Bits(3)(0)
        push_op2_from = Bits(3)(0)
        push_is_branch = Bits(1)(0)
        push_branch_flip = Bits(1)(0)
        active_idx = Bits(5)(0)
        push_pc = Bits(32)(0)

        for step in STEPS:
            cond = cycle_val == UInt(32)(step.cycle)
            if step.push is not None:
                push_en = cond.select(Bits(1)(1), push_en)
                push_rs1 = cond.select(Bits(6)(step.push["rs1"]), push_rs1)
                push_rs2 = cond.select(Bits(6)(step.push["rs2"]), push_rs2)
                push_rd = cond.select(Bits(6)(step.push["rd"]), push_rd)
                push_op = cond.select(Bits(4)(step.push["alu_op"]), push_op)
                push_imm = cond.select(Bits(32)(step.push["imm"]), push_imm)
                push_op1_from = cond.select(Bits(3)(step.push.get("op1_from", 0)), push_op1_from)
                push_op2_from = cond.select(Bits(3)(step.push.get("op2_from", 1)), push_op2_from)
                push_is_branch = cond.select(Bits(1)(step.push.get("is_branch", 0)), push_is_branch)
                push_branch_flip = cond.select(Bits(1)(step.push.get("branch_flip", 0)), push_branch_flip)
                active_idx = cond.select(Bits(5)(step.push["active_idx"]), active_idx)
                push_pc = cond.select(Bits(32)(step.push["pc"]), push_pc)

            if step.pop:
                pop_en = cond.select(Bits(1)(1), pop_en)

        push_entry = ALUQueuePushEntry(
            rs1_physical=push_rs1,
            rs2_physical=push_rs2,
            rd_physical=push_rd,
            alu_op=push_op,
            imm=push_imm,
            operant1_from=push_op1_from,
            operant2_from=push_op2_from,
            is_branch=push_is_branch,
            branch_flip=push_branch_flip,
            PC=push_pc,
        )

        self.queue.build(push_en, push_entry, pop_en, active_idx)

        front_entry = self.queue.queue._dtype.view(self.queue.queue.front())
        log_str = (
            "cycle: {}, head: {}, tail: {}, count: {}, push_en: {}, pop_en: {}, "
            "active_idx: {}, valid: {}, front_valid: {}, front_alu_idx: {}, front_rd: {}, contents: "
        )

        args = [
            cycle_val,
            self.queue.queue._head[0],
            self.queue.queue._tail[0],
            self.queue.queue.count(),
            push_en,
            pop_en,
            active_idx,
            self.queue.valid(),
            front_entry.valid,
            front_entry.alu_queue_idx,
            front_entry.rd_physical,
        ]

        for i in range(self.depth):
            entry = self.queue.queue._dtype.view(self.queue.queue[i])
            log_str += f"E{i}:{{}},{{}},{{}},{{}},{{}},{{}},{{}},{{}},{{}},{{}},{{}},{{}},{{}}; "
            args.extend(
                [
                    entry.valid,
                    entry.active_list_idx,
                    entry.alu_queue_idx,
                    entry.rs1_physical,
                    entry.rs2_physical,
                    entry.rd_physical,
                    entry.alu_op,
                    entry.imm,
                    entry.operant1_from,
                    entry.operant2_from,
                    entry.is_branch,
                    entry.branch_flip,
                    entry.PC,
                ]
            )

        log(log_str, *args)


def parse_line(line: str) -> Optional[Dict[str, Any]]:
    base_match = re.search(
        r"cycle: (\d+), head: (\d+), tail: (\d+), count: (\d+), push_en: (\d+), pop_en: (\d+), "
        r"active_idx: (\d+), valid: (\d+), front_valid: (\d+), front_alu_idx: (\d+), front_rd: (\d+), contents: (.*)",
        line,
    )
    if not base_match:
        return None

    entry_block = base_match.group(12)
    entries: Dict[int, Dict[str, int]] = {}
    for match in re.finditer(r"E(\d+):([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+),([0-9]+);", entry_block):
        idx = int(match.group(1))
        entries[idx] = {
            "valid": int(match.group(2)),
            "active_idx": int(match.group(3)),
            "alu_idx": int(match.group(4)),
            "rs1": int(match.group(5)),
            "rs2": int(match.group(6)),
            "rd": int(match.group(7)),
            "op": int(match.group(8)),
            "imm": int(match.group(9)),
            "op1_from": int(match.group(10)),
            "op2_from": int(match.group(11)),
            "is_branch": int(match.group(12)),
            "branch_flip": int(match.group(13)),
            "pc": int(match.group(14)),
        }

    return {
        "cycle": int(base_match.group(1)),
        "head": int(base_match.group(2)),
        "tail": int(base_match.group(3)),
        "count": int(base_match.group(4)),
        "push_en": int(base_match.group(5)),
        "pop_en": int(base_match.group(6)),
        "active_idx": int(base_match.group(7)),
        "valid": int(base_match.group(8)),
        "front_valid": int(base_match.group(9)),
        "front_alu_idx": int(base_match.group(10)),
        "front_rd": int(base_match.group(11)),
        "entries": entries,
    }


def check(raw: str):
    lines = raw.strip().split("\n")
    history: Dict[int, Dict[str, Any]] = {}
    for line in lines:
        parsed = parse_line(line)
        if parsed:
            history[parsed["cycle"]] = parsed

    step_map = {step.cycle: step for step in STEPS}

    queue_storage: List[Dict[str, int]] = [
        {
            "valid": 0,
            "active_idx": 0,
            "alu_idx": 0,
            "rs1": 0,
            "rs2": 0,
            "rd": 0,
            "op": 0,
            "imm": 0,
            "op1_from": 0,
            "op2_from": 0,
            "is_branch": 0,
            "branch_flip": 0,
            "pc": 0,
        }
        for _ in range(DEPTH)
    ]
    head = 0
    tail = 0
    count = 0

    max_cycle = max(step.cycle for step in STEPS) + 2

    for cycle in range(1, max_cycle + 1):
        log_entry = history.get(cycle)
        if not log_entry:
            continue

        assert log_entry["head"] == head, f"Cycle {cycle}: expected head {head}, got {log_entry['head']}"
        assert log_entry["tail"] == tail, f"Cycle {cycle}: expected tail {tail}, got {log_entry['tail']}"
        assert log_entry["count"] == count, f"Cycle {cycle}: expected count {count}, got {log_entry['count']}"

        if count > 0:
            expected_front = queue_storage[head]
            assert log_entry["front_valid"] == expected_front["valid"], "Front valid mismatch"
            assert log_entry["front_rd"] == expected_front["rd"], "Front RD mismatch"
            assert log_entry["front_alu_idx"] == expected_front["alu_idx"], "Front idx mismatch"

        for i in range(DEPTH):
            stored = queue_storage[i]
            logged = log_entry["entries"].get(i)
            assert logged is not None, f"Cycle {cycle}: missing entry log for slot {i}"
            for field in stored:
                assert (
                    logged[field if field != "alu_idx" else "alu_idx"] == stored[field]
                ), f"Cycle {cycle}, slot {i}, field {field}: expected {stored[field]}, got {logged[field if field != 'alu_idx' else 'alu_idx']}"

        step = step_map.get(cycle)
        if step:
            push = step.push
            pop = step.pop
        else:
            push = None
            pop = False

        if push:
            entry = {
                "valid": 1,
                "active_idx": push["active_idx"],
                "alu_idx": (tail + 1) % 32,
                "rs1": push["rs1"],
                "rs2": push["rs2"],
                "rd": push["rd"],
                "op": push["alu_op"],
                "imm": push["imm"],
                "op1_from": push.get("op1_from", 0),
                "op2_from": push.get("op2_from", 1),
                "is_branch": push.get("is_branch", 0),
                "branch_flip": push.get("branch_flip", 0),
                "pc": push["pc"],
            }
            queue_storage[tail] = entry
            tail = (tail + 1) % DEPTH

        if pop and count > 0:
            head = (head + 1) % DEPTH

        if push and not pop:
            count += 1
        elif pop and not push and count > 0:
            count -= 1

    # Final sanity: queue should be empty after final pop
    assert count == 0, "Queue should be empty after final operations"


def test_alu_queue_behavior():
    sys = SysBuilder("alu_queue_test")
    with sys:
        driver = Driver(DEPTH)
        driver.build()

    max_cycle = max(step.cycle for step in STEPS)
    sim, _ = elaborate(sys, verilog=True, verbose=False, sim_threshold=max_cycle + 5)

    raw, std_out, std_err = run_quietly(run_simulator, sim)
    assert raw is not None, std_err
    check(raw)
