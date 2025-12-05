from dataclasses import dataclass
from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue
from r10k_cpu.common import alu_queue_entry_type

@dataclass(frozen=True)
class ALUQueuePushEntry:
    rs1_physical: Value
    rs2_physical: Value
    rd_physical: Value
    alu_op: Value
    imm: Value

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
        )
        push_valid = push_enable.optional(Bits(1)(0))
        pop_enable = pop_enable.optional(Bits(1)(0))

        self.queue.operate(push_enable=push_valid, push_data=entry, pop_enable=pop_enable)


    def valid(self) -> Value:
        return ~self.queue.is_empty()
