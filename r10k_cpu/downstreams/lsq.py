from dataclasses import dataclass
from assassyn.frontend import *
from assassyn.ir.array import ArrayRead
from dataclass.circular_queue import CircularQueue, CircularQueueSelection
from r10k_cpu.common import LSQEntryType
from r10k_cpu.utils import is_between, replace_bundle

@dataclass(frozen=True)
class LSQPushEntry:
    rs1_physical: Value
    rs2_physical: Value
    rd_physical: Value
    imm: Value
    is_load: Value
    is_store: Value
    op_type: Value

class LSQ(Downstream):
    queue: CircularQueue

    def __init__(self, depth: int):
        super().__init__()
        self.queue = CircularQueue(LSQEntryType, depth)
    
    @downstream.combinational
    def build(self, push_enable: Value, push_data: LSQPushEntry, pop_enable: Value, active_list_idx: Value):
        entry = LSQEntryType.bundle(
            valid=push_enable.optional(Bits(1)(0)),
            active_list_idx=active_list_idx,
            lsq_queue_idx=(self.queue.get_tail().bitcast(UInt(5)) + UInt(1)(1)).bitcast(Bits(5)),  # Next index
            imm=push_data.imm.optional(Bits(32)(0)),
            is_load=push_data.is_load.optional(Bits(1)(0)),
            is_store=push_data.is_store.optional(Bits(1)(0)),
            op_type=push_data.op_type.optional(Bits(3)(0)),
            rd_physical=push_data.rd_physical.optional(Bits(6)(0)),
            rs1_physical=push_data.rs1_physical.optional(Bits(6)(0)),
            rs2_physical=push_data.rs2_physical.optional(Bits(6)(0)),
            issued=Bits(1)(0),
        )
        push_valid = push_enable.optional(Bits(1)(0))
        pop_enable = pop_enable.optional(Bits(1)(0))

        self.queue.operate(push_enable=push_valid, push_data=entry, pop_enable=pop_enable)

    def select_first_ready(self, register_ready: Array) -> CircularQueueSelection:
        def selector(value: ArrayRead, index: Value) -> Value:
            entry = LSQEntryType.view(value)
            rs1_ready = self._operand_ready(register_ready, entry.rs1_physical)
            rs2_ready = self._operand_ready(register_ready, entry.rs2_physical)
            
            # rs1 is always needed for address
            # rs2 is needed for store data
            rs2_needed = entry.is_store

            store_before = self.is_store_before(index)
            is_store = value.is_store
            
            return entry.valid & rs1_ready & ((~rs2_needed) | rs2_ready) & ~entry.issued & (~store_before | is_store)

        return self.queue.choose(selector)
    
    def mark_issued(self, index: Value):
        bundle = self.queue[index]
        new_bundle = replace_bundle(
            bundle,
            issued=Bits(1)(1),
        )
        self.queue[index] = new_bundle

    @staticmethod
    def _operand_ready(register_ready: Array, physical: Value) -> Value:
        ready_bit = register_ready[physical].bitcast(Bits(1))
        return ready_bit

    def valid(self) -> Value:
        return ~self.queue.is_empty()
        
    def is_store_before(self, index: Value) -> Value:
        before = Bits(1)(0)
        is_head = self.queue._head[0] == index

        for i in range(self.queue.depth):
            is_valid = is_between(UInt(self.queue.addr_bits)(i), self.queue._head[0], index)
            before |= is_valid & self.queue[i].is_store

        return before & ~is_head
