from dataclasses import dataclass
from assassyn.frontend import *
from assassyn.ir.array import ArrayRead
from dataclass.circular_queue import CircularQueue, CircularQueueSelection
from r10k_cpu.common import LSQEntryType
from r10k_cpu.downstreams.register_ready import RegisterReady
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
    def build(self, push_enable: Value, push_data: LSQPushEntry, pop_enable: Value, active_list_idx: Value, flush: Value, store_buffer: Array):
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

        with Condition(pop_enable):
            # If we are popping a store instruction, we need to store it in the store buffer
            entry_to_pop = self.queue[self.queue._head[0]]
            with Condition(entry_to_pop.is_store):
                store_buffer[0] = entry_to_pop

        self.queue.operate(push_enable=push_valid, push_data=entry, pop_enable=pop_enable, clear=flush.optional(Bits(1)(0)))

    def select_first_ready(self, register_ready: RegisterReady) -> CircularQueueSelection:
        selected_index = self.queue._zero_addr
        selected_distance = self.queue._zero
        selected_valid = Bits(1)(0)

        pointer = self.queue._head[0]
        distance = self.queue._zero
        count_uint = self.queue._count[0].bitcast(UInt(self.queue.count_bits))

        seen_store = Bits(1)(0)

        for offset in range(self.queue.depth):
            offset_uint = UInt(self.queue.count_bits)(offset)
            has_entry = offset_uint < count_uint

            value = self.queue._storage[pointer]
            entry = LSQEntryType.view(value)

            rs1_ready = self._operand_ready(register_ready, entry.rs1_physical)
            # We only choose loads here, so rs2 is not needed

            matches = (
                entry.valid 
                & rs1_ready
                & ~entry.issued 
                & ~seen_store 
                & ~entry.is_store # LSQ only picks Loads here
            )

            candidate_valid = has_entry & matches
            
            new_hit = candidate_valid & ~selected_valid

            selected_index = new_hit.select(pointer, selected_index)
            selected_distance = new_hit.select(distance, selected_distance)
            selected_valid = selected_valid | candidate_valid

            seen_store = seen_store | (has_entry & entry.valid & entry.is_store)

            pointer = self.queue._increment_pointer(pointer)
            distance_uint = distance.bitcast(UInt(self.queue.count_bits))
            distance = (distance_uint + self.queue._one).bitcast(Bits(self.queue.count_bits))

        selected_data = self.queue._storage[selected_index]

        return CircularQueueSelection(
            data=LSQEntryType.view(selected_data),
            index=selected_index,
            distance=selected_distance,
            valid=selected_valid,
        )
    
    def mark_issued(self, index: Value):
        bundle = self.queue[index]
        new_bundle = replace_bundle(
            bundle,
            issued=Bits(1)(1),
        )
        self.queue[index] = new_bundle

    @staticmethod
    def _operand_ready(register_ready: RegisterReady, physical: Value) -> Value:
        ready_bit = register_ready.read(physical).bitcast(Bits(1))
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
