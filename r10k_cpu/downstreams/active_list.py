from dataclasses import dataclass
from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue
from r10k_cpu.common import rob_entry_type


@dataclass(frozen=True)
class InstructionPushEntry:
    valid: Value
    pc: Value
    dest_logical: Value
    dest_new_physical: Value
    dest_old_physical: Value
    is_branch: Value
    predict_branch: Value


class ActiveList(Downstream):
    queue: CircularQueue

    def __init__(self, depth: int):
        super().__init__()
        self.queue = CircularQueue(rob_entry_type, depth)

    @downstream.combinational
    def build(
        self,
        push_inst: InstructionPushEntry,
        retire_enable: Value,
    ):
        push_valid = push_inst.valid.optional(Bits(1)(0))
        entry = rob_entry_type.bundle(
            pc=push_inst.pc.optional(Bits(32)(0)),
            dest_logical=push_inst.dest_logical.optional(Bits(5)(0)),
            dest_new_physical=push_inst.dest_new_physical.optional(Bits(6)(0)),
            dest_old_physical=push_inst.dest_old_physical.optional(Bits(6)(0)),
            ready=Bits(1)(0),
            is_branch=push_inst.is_branch.optional(Bits(1)(0)),
            predict_branch=push_inst.predict_branch.optional(Bits(1)(0)),
            actual_branch=Bits(1)(0),
        )
        retire_enable = retire_enable.optional(Bits(1)(0))

        self.queue.operate(push_enable=push_valid, push_data=entry, pop_enable=retire_enable)

    def set_ready(self, index: Value):
        bundle = self.queue[index]
        new_bundle = rob_entry_type.bundle(
            pc=bundle.pc,
            dest_logical=bundle.dest_logical,
            dest_new_physical=bundle.dest_new_physical,
            dest_old_physical=bundle.dest_old_physical,
            ready=Bits(1)(1),
            is_branch=bundle.is_branch,
            predict_branch=bundle.predict_branch,
            actual_branch=bundle.actual_branch,
        )
        self.queue[index] = new_bundle

    def is_full(self) -> Value:
        return self.queue.is_full()
