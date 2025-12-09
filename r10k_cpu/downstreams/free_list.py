from math import ceil, log2
from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue


class FreeList(Downstream):
    queue: CircularQueue
    zero_reg: Value

    # Only snapshot_head is needed to track the head position for recovery, because the push operations before branch are valid.
    snapshot_head: Array

    def __init__(self, register_number: int):
        super().__init__()
        bits = ceil(log2(register_number))

        # Initialize the free list with all registers available, except register 0 which is reserved.
        # To prevent overlap in speculative scenarios, we double the size of the free list.
        initializer = [i + 1 for i in range(register_number - 1)]
        initializer = initializer + [0] * (register_number * 2 - len(initializer))
        self.queue = CircularQueue(
            Bits(bits),
            register_number * 2,
            initializer=initializer,
            default_count=register_number - 1,
        )
        self.zero_reg = Bits(bits)(0)

        self.snapshot_head = RegArray(Bits(self.queue.addr_bits), 1)

    @downstream.combinational
    def build(
        self,
        pop_enable: Value,
        push_enable: Value,
        push_data: Value,
        make_snapshot: Value,
        flush_recover: Value,
    ):
        make_snapshot = make_snapshot.optional(Bits(1)(0))
        flush_recover = flush_recover.optional(Bits(1)(0))
        pop_enable = pop_enable.optional(Bits(1)(0))
        push_enable = push_enable.optional(Bits(1)(0))

        with Condition(make_snapshot):
            self.snapshot_head[0] = self.queue.get_head()

        with Condition(flush_recover):
            self.queue._head[0] = self.snapshot_head[0]
            self.queue._count[0] = (
                (self.queue.get_tail() > self.queue.get_head())
                .select(
                    (
                        self.queue._tail[0].bitcast(UInt(self.queue.addr_bits))
                        - self.snapshot_head[0].bitcast(UInt(self.queue.addr_bits))
                    ).zext(UInt(self.queue.count_bits)),
                    UInt(self.queue.count_bits)(self.queue.depth)
                    - (
                        self.snapshot_head[0].bitcast(UInt(self.queue.addr_bits))
                        - self.queue._tail[0].bitcast(UInt(self.queue.addr_bits))
                    ).zext(UInt(self.queue.count_bits)),
                )
                .bitcast(Bits(self.queue.count_bits))
            )

        self.queue.operate(
            pop_enable=pop_enable & ~flush_recover,
            push_enable=push_enable & ~flush_recover,
            push_data=push_data,
        )

    def free_reg(self) -> Value:
        return self.queue.front()

    def valid(self) -> Value:
        return ~self.queue.is_empty()
