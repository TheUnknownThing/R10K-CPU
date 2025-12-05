from dataclasses import dataclass
from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue
from r10k_cpu.common import lsq_entry_type

@dataclass(frozen=True)
class LSQPushEntry:
    address: Value
    data: Value
    is_load: Value
    is_store: Value
    op_type: Value

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
            address=push_data.address.optional(Bits(32)(0)),
            data=push_data.data.optional(Bits(32)(0)),
            is_load=push_data.is_load.optional(Bits(1)(0)),
            is_store=push_data.is_store.optional(Bits(1)(0)),
            op_type=push_data.op_type.optional(Bits(3)(0)),
        )
        push_valid = push_enable.optional(Bits(1)(0))
        pop_enable = pop_enable.optional(Bits(1)(0))

        self.queue.operate(push_enable=push_valid, push_data=entry, pop_enable=pop_enable)


    def valid(self) -> Value:
        return ~self.queue.is_empty()
