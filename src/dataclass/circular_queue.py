from __future__ import annotations

import math
from dataclasses import dataclass

from assassyn.frontend import *


@dataclass
class CircularQueueView:
    """Lightweight bundle describing the observable queue signals."""

    read_data: Value
    read_valid: Value
    write_ready: Value
    empty: Value
    full: Value
    count: Value


class CircularQueue:
    """Single-read, single-write circular queue built on top of RegArray."""

    def __init__(
        self,
        element_shape: DType,
        depth: int,
        *,
        initializer: list[int] | None = None,
        name: str | None = None,
    ) -> None:
        if depth <= 0:
            raise ValueError("Queue depth must be positive.")
        self.depth = depth
        self.name = name or "circular_queue"
        self.addr_bits = max(1, math.ceil(math.log2(depth)))
        self.count_bits = max(1, math.ceil(math.log2(depth + 1)))
        if initializer is None:
            initializer = [0] * depth
        elif len(initializer) != depth:
            raise ValueError(
                f"Queue initializer length {len(initializer)} does not match depth {depth}."
            )

        self._element_shape = element_shape
        self._storage = RegArray(element_shape, depth, initializer=initializer)
        self._head = RegArray(Bits(self.addr_bits), 1, initializer=[0])
        self._tail = RegArray(Bits(self.addr_bits), 1, initializer=[0])
        self._count = RegArray(Bits(self.count_bits), 1, initializer=[0])
        self._last_index = UInt(self.addr_bits)(depth - 1)
        self._one_addr = UInt(self.addr_bits)(1)
        self._one_count = UInt(self.count_bits)(1)
        self._count_full = Bits(self.count_bits)(depth)

    def operate(
        self,
        *,
        write_enable: Value,
        write_data: Value,
        read_enable: Value,
    ) -> CircularQueueView:
        """Drive the queue for a single cycle and expose its handshake signals."""

        empty = self._count[0] == Bits(self.count_bits)(0)
        full = self._count[0] == self._count_full
        read_valid = ~empty
        write_ready = ~full

        assume(~(read_enable & ~read_valid))
        assume(~(write_enable & ~write_ready))

        read_data = self._storage[self._head[0]]

        with Condition(read_enable):
            self._storage[self._tail[0]] = write_data

        next_head = self._increment_pointer(self._head[0])
        next_tail = self._increment_pointer(self._tail[0])

        with Condition(read_enable):
            self._head[0] = next_head
        with Condition(write_enable):
            self._tail[0] = next_tail

        count_uint = self._count[0].bitcast(UInt(self.count_bits))
        inc_value = (count_uint + self._one_count).bitcast(Bits(self.count_bits))
        dec_value = (count_uint - self._one_count).bitcast(Bits(self.count_bits))

        with Condition(write_enable & ~read_enable):
            self._count[0] = inc_value
        with Condition(read_enable & ~write_enable):
            self._count[0] = dec_value

        return CircularQueueView(
            read_data=read_data,
            read_valid=read_valid,
            write_ready=write_ready,
            empty=empty,
            full=full,
            count=self._count[0],
        )

    def _increment_pointer(self, pointer: Value) -> Value:
        pointer_uint = pointer.bitcast(UInt(self.addr_bits))
        wrapped = pointer_uint == self._last_index
        incremented = pointer_uint + self._one_addr
        next_value = wrapped.select(UInt(self.addr_bits)(0), incremented)
        return next_value.bitcast(Bits(self.addr_bits))
