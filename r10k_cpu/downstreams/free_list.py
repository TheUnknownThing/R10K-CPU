from math import ceil, log2
from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue


class FreeList(Downstream):
    queue: CircularQueue

    def __init__(self, register_number: int):
        super().__init__()
        bits = ceil(log2(register_number))
        initializer = [i for i in range(register_number)]
        self.queue = CircularQueue(Bits(bits), register_number, initializer=initializer, default_count=register_number)

    @downstream.combinational
    def build(self, pop_enable: Value, push_enable: Value, push_data: Value):
        self.queue.operate(pop_enable=pop_enable, push_enable=push_enable, push_data=push_data)

    def free_reg(self) -> Value:
        return self.queue.front()

    def valid(self) -> Value:
        return ~self.queue.is_empty()
