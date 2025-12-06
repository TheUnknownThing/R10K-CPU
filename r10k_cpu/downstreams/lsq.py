from dataclasses import dataclass
from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue, CircularQueueSelection
from r10k_cpu.common import lsq_entry_type
from r10k_cpu.config import data_depth

@dataclass(frozen=True)
class LSQPushEntry:
    address: Value
    data: Value
    is_load: Value
    is_store: Value
    op_type: Value
    rd_physical: Value
    rs1_physical: Value
    rs2_physical: Value
    rs1_needed: Value
    rs2_needed: Value

class LSQ(Downstream):
    queue: CircularQueue

    def __init__(self, depth: int):
        super().__init__()
        self.queue = CircularQueue(lsq_entry_type, depth)
    
    @downstream.combinational
    def build(self, push_enable: Value, push_data: LSQPushEntry, pop_enable: Value, active_list_idx: Value):
        # self.queue.operate(pop_enable=pop_enable, push_enable=push_enable, push_data=push_data)
        entry = lsq_entry_type.bundle(
            valid=push_enable.optional(Bits(1)(0)),
            active_list_idx=active_list_idx,
            lsq_queue_idx=(self.queue.get_tail().bitcast(UInt(5)) + UInt(1)(1)).bitcast(Bits(5)),  # Next index
            address=push_data.address.optional(Bits(data_depth)(0)),
            data=push_data.data.optional(Bits(32)(0)),
            is_load=push_data.is_load.optional(Bits(1)(0)),
            is_store=push_data.is_store.optional(Bits(1)(0)),
            op_type=push_data.op_type.optional(Bits(3)(0)),
            rd_physical=push_data.rd_physical.optional(Bits(6)(0)),
            rs1_physical=push_data.rs1_physical.optional(Bits(6)(0)),
            rs2_physical=push_data.rs2_physical.optional(Bits(6)(0)),
            rs1_needed=push_data.rs1_needed.optional(Bits(1)(1)),
            rs2_needed=push_data.rs2_needed.optional(Bits(1)(0)),
        )
        push_valid = push_enable.optional(Bits(1)(0))
        pop_enable = pop_enable.optional(Bits(1)(0))

        self.queue.operate(push_enable=push_valid, push_data=entry, pop_enable=pop_enable)

    def select_first_ready(self, register_ready: Array) -> CircularQueueSelection:
        def selector(value: Value) -> Value:
            entry = lsq_entry_type.view(value)
            rs1_ready = self._operand_ready(register_ready, entry.rs1_physical, entry.rs1_needed)
            rs2_ready = self._operand_ready(register_ready, entry.rs2_physical, entry.rs2_needed)
            return entry.valid & rs1_ready & rs2_ready

        return self.queue.choose(selector)

    @staticmethod
    def _operand_ready(register_ready: Array, physical: Value, needed: Value) -> Value:
        ready_bit = register_ready[physical].bitcast(Bits(1))
        return (~needed) | (needed & ready_bit)

    def valid(self) -> Value:
        return ~self.queue.is_empty()
