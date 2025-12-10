from dataclasses import dataclass
from typing import Optional
from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue
from r10k_cpu.common import ROBEntryType
from r10k_cpu.utils import replace_bundle


@dataclass(frozen=True)
class InstructionPushEntry:
    valid: Value
    pc: Value
    dest_logical: Value
    dest_new_physical: Value
    dest_old_physical: Value
    has_dest: Value
    imm: Value
    is_branch: Value
    is_alu: Value
    predict_branch: Value
    is_jump: Value
    is_jalr: Value
    is_terminator: Value
    is_naturally_ready: Value


class ActiveList(Downstream):
    queue: CircularQueue

    def __init__(self, depth: int):
        super().__init__()
        self.queue = CircularQueue(ROBEntryType, depth)

    @downstream.combinational
    def build(
        self,
        push_inst: InstructionPushEntry,
        pop_enable: Value,
        flush: Value,
    ):
        flush = flush.optional(Bits(1)(0))
        push_valid = push_inst.valid.optional(Bits(1)(0))
        entry = ROBEntryType.bundle(
            pc=push_inst.pc.optional(Bits(32)(0)),
            dest_logical=push_inst.dest_logical.optional(Bits(5)(0)),
            dest_new_physical=push_inst.dest_new_physical.optional(Bits(6)(0)),
            dest_old_physical=push_inst.dest_old_physical.optional(Bits(6)(0)),
            has_dest=push_inst.has_dest.optional(Bits(1)(0)),
            imm=push_inst.imm.optional(Bits(32)(0)),
            ready=push_inst.is_naturally_ready.optional(Bits(1)(0)),
            is_branch=push_inst.is_branch.optional(Bits(1)(0)),
            is_alu=push_inst.is_alu.optional(Bits(1)(0)),
            predict_branch=push_inst.predict_branch.optional(Bits(1)(0)),
            actual_branch=Bits(1)(0),
            is_jump=push_inst.is_jump.optional(Bits(1)(0)),
            is_jalr=push_inst.is_jalr.optional(Bits(1)(0)),
            is_terminator=push_inst.is_terminator.optional(Bits(1)(0)),
        )
        pop_enable = pop_enable.optional(Bits(1)(0))

        self.queue.operate(
            push_enable=push_valid & ~flush,
            push_data=entry,
            pop_enable=pop_enable & ~flush,
            clear=flush,
        )

        return self.queue.get_tail()

    def set_ready(
        self,
        index: Value,
        actual_branch: Optional[Value] = None,
        new_imm: Optional[Value] = None,
        new_imm_enable: Optional[Value] = None,
    ) -> None:
        bundle = self.queue[index]
        imm_value = bundle.imm
        if new_imm is not None:
            imm_enable = new_imm_enable if new_imm_enable is not None else Bits(1)(0)
            imm_value = imm_enable.select(new_imm, bundle.imm)
        new_bundle = replace_bundle(
            bundle,
            ready=Bits(1)(1),
            actual_branch=(
                actual_branch if actual_branch is not None else bundle.actual_branch
            ),
            imm=imm_value,
        )
        self.queue[index] = new_bundle

    def is_full(self) -> Value:
        return self.queue.is_full()
