import math
from dataclasses import dataclass
from assassyn.frontend import *
from assassyn.ir.dtype import RecordValue
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
    def build(
        self,
        push_enable: Value,
        push_data: LSQPushEntry,
        pop_enable: Value,
        active_list_idx: Value,
        flush: Value,
    ):
        entry = LSQEntryType.bundle(
            valid=push_enable.optional(Bits(1)(0)),
            active_list_idx=active_list_idx,
            lsq_queue_idx=(self.queue.get_tail().bitcast(UInt(5))).bitcast(Bits(5)),
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

        store_buffer_push_data = LSQEntryType.view(self.queue[self.queue._head[0]])
        store_buffer_push_enable = pop_enable & store_buffer_push_data.is_store

        self.queue.operate(
            push_enable=push_valid,
            push_data=entry,
            pop_enable=pop_enable,
            clear=flush.optional(Bits(1)(0)),
        )

        return store_buffer_push_enable, store_buffer_push_data

    def select_first_ready(
        self, register_ready: RegisterReady
    ) -> CircularQueueSelection:
        count_uint = self.queue._count[0].bitcast(UInt(self.queue.count_bits))

        pointers = []
        distances = []
        values = []
        has_entries = []

        pointer = self.queue._head[0]
        distance = self.queue._zero

        for offset in range(self.queue.depth):
            offset_uint = UInt(self.queue.count_bits)(offset)
            has_entry = offset_uint < count_uint

            pointers.append(pointer)
            distances.append(distance)
            values.append(self.queue._storage[pointer])
            has_entries.append(has_entry)

            pointer = self.queue._increment_pointer(pointer)
            distance_uint = distance.bitcast(UInt(self.queue.count_bits))
            distance = (distance_uint + self.queue._one).bitcast(Bits(self.queue.count_bits))

        entries = [LSQEntryType.view(v) for v in values]
        store_flags = [has_entries[i] & entries[i].valid & entries[i].is_store for i in range(self.queue.depth)]

        # Prefix OR with log depth to know if a store appears before each position.
        store_prefix = store_flags[:]
        stages = math.ceil(math.log2(self.queue.depth))
        for stage in range(stages):
            step = 1 << stage
            for i in range(self.queue.depth):
                prev = Bits(1)(0) if i < step else store_prefix[i - step]
                store_prefix[i] = store_prefix[i] | prev

        any_store_before = [Bits(1)(0)] * self.queue.depth
        for i in range(self.queue.depth):
            any_store_before[i] = Bits(1)(0) if i == 0 else store_prefix[i - 1]

        candidates = []
        for i in range(self.queue.depth):
            rs1_ready = self._operand_ready(register_ready, entries[i].rs1_physical)
            matches = (
                entries[i].valid
                & rs1_ready
                & ~entries[i].issued
                & ~entries[i].is_store
                & ~any_store_before[i]
            )
            candidate_valid = has_entries[i] & matches

            candidates.append((values[i], pointers[i], distances[i], candidate_valid))

        next_power = 1 << math.ceil(math.log2(len(candidates)))
        zero_data, zero_index, zero_distance = candidates[0][0], self.queue._zero_addr, self.queue._zero
        for _ in range(len(candidates), next_power):
            candidates.append((zero_data, zero_index, zero_distance, Bits(1)(0)))

        while len(candidates) > 1:
            next_layer = []
            for i in range(0, len(candidates), 2):
                left_data, left_index, left_distance, left_valid = candidates[i]
                right_data, right_index, right_distance, right_valid = candidates[i + 1]

                chosen_data = left_valid.select(left_data, right_data)
                chosen_index = left_valid.select(left_index, right_index)
                chosen_distance = left_valid.select(left_distance, right_distance)
                chosen_valid = left_valid | right_valid

                next_layer.append((chosen_data, chosen_index, chosen_distance, chosen_valid))

            candidates = next_layer

        selected_data, selected_index, selected_distance, selected_valid = candidates[0]

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
            is_valid = is_between(
                UInt(self.queue.addr_bits)(i), self.queue._head[0], index
            )
            before |= is_valid & self.queue[i].is_store

        return before & ~is_head


class StoreBuffer(Downstream):
    reg: Array

    def __init__(self):
        super().__init__()
        self.reg = RegArray(LSQEntryType, 1)

    @downstream.combinational
    def build(self, push_enable: Value, push_data: RecordValue, pop_enable: Value):
        push_enable = push_enable.optional(Bits(1)(0))
        pop_enable = pop_enable.optional(Bits(1)(0))


        with Condition(push_enable):
            self.reg[0] = push_data

        with Condition(~push_enable & pop_enable):
            self.reg[0] = LSQEntryType.bundle(
                valid=Bits(1)(0),
                active_list_idx=Bits(5)(0),
                lsq_queue_idx=Bits(5)(0),
                imm=Bits(32)(0),
                is_load=Bits(1)(0),
                is_store=Bits(1)(0),
                op_type=Bits(3)(0),
                rd_physical=Bits(6)(0),
                rs1_physical=Bits(6)(0),
                rs2_physical=Bits(6)(0),
                issued=Bits(1)(0),
            )