from dataclasses import dataclass
from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue, CircularQueueSelection
from r10k_cpu.common import alu_queue_entry_type, OperantFrom, OPERANT_FROM_LEN

@dataclass(frozen=True)
class ALUQueuePushEntry:
    rs1_physical: Value
    rs2_physical: Value
    rd_physical: Value
    alu_op: Value
    imm: Value
    operant1_from: Value
    operant2_from: Value
    PC: Value
    is_branch: Value
    branch_flip: Value

class ALUQueue(Downstream):
    queue: CircularQueue

    def __init__(self, depth: int):
        super().__init__()
        self.queue = CircularQueue(alu_queue_entry_type, depth)
    
    @downstream.combinational
    def build(self, push_enable: Value, push_data: ALUQueuePushEntry, pop_enable: Value, active_list_idx: Value):
        # self.queue.operate(pop_enable=pop_enable, push_enable=push_enable, push_data=push_data)
        entry = alu_queue_entry_type.bundle(
            valid=push_enable.optional(Bits(1)(0)),
            active_list_idx=active_list_idx,
            alu_queue_idx=(self.queue.get_tail().bitcast(UInt(5)) + UInt(1)(1)).bitcast(Bits(5)),  # Next index
            rs1_physical=push_data.rs1_physical.optional(Bits(6)(0)),
            rs2_physical=push_data.rs2_physical.optional(Bits(6)(0)),
            rd_physical=push_data.rd_physical.optional(Bits(6)(0)),
            alu_op=push_data.alu_op.optional(Bits(4)(0)),
            imm=push_data.imm.optional(Bits(32)(0)),
            operant1_from=push_data.operant1_from.optional(Bits(OPERANT_FROM_LEN)(0)),
            operant2_from=push_data.operant2_from.optional(Bits(OPERANT_FROM_LEN)(0)),
            PC=push_data.PC.optional(Bits(32)(0)),
            is_branch=push_data.is_branch.optional(Bits(1)(0)),
            branch_flip=push_data.branch_flip.optional(Bits(1)(0)),
        )
        push_valid = push_enable.optional(Bits(1)(0))
        pop_enable = pop_enable.optional(Bits(1)(0))

        self.queue.operate(push_enable=push_valid, push_data=entry, pop_enable=pop_enable)

    def select_first_ready(self, register_ready: Array) -> CircularQueueSelection:
        def selector(value: Value) -> Value:
            entry = alu_queue_entry_type.view(value)
            
            rs1_needed = (entry.operant1_from == Bits(OPERANT_FROM_LEN)(OperantFrom.RS1.value)) | \
                         (entry.operant2_from == Bits(OPERANT_FROM_LEN)(OperantFrom.RS1.value))
            rs2_needed = (entry.operant1_from == Bits(OPERANT_FROM_LEN)(OperantFrom.RS2.value)) | \
                         (entry.operant2_from == Bits(OPERANT_FROM_LEN)(OperantFrom.RS2.value))

            rs1_ready = self._operand_ready(register_ready, entry.rs1_physical, rs1_needed)
            rs2_ready = self._operand_ready(register_ready, entry.rs2_physical, rs2_needed)
            return entry.valid & rs1_ready & rs2_ready

        return self.queue.choose(selector)

    @staticmethod
    def _operand_ready(register_ready: Array, physical: Value, needed: Value) -> Value:
        ready_bit = register_ready[physical].bitcast(Bits(1))
        return (~needed) | (needed & ready_bit)

    def valid(self) -> Value:
        return ~self.queue.is_empty()
