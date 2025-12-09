from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Optional

from assassyn.frontend import *
from assassyn.ir.dtype import RecordValue
from assassyn.ir.array import ArrayRead


@dataclass
class CircularQueueSelection:
    """Metadata for the first queue element satisfying a selector."""

    data: Any
    index: Value
    distance: Value
    valid: Value


class CircularQueue:
    """Single-push, single-pop, multi-modify circular queue built on top of RegArray."""

    def __init__(
        self,
        dtype: DType,
        depth: int,
        *,
        initializer: list[int] | None = None,
        name: str | None = None,
        default_count: int = 0,
    ) -> None:
        if depth <= 0:
            raise ValueError("Queue depth must be positive.")
        assert default_count <= depth, "Default count must be less than or equal to depth."
        self.depth = depth
        self.name = name or "circular_queue"
        self.addr_bits = max(1, math.ceil(math.log2(depth)))
        self.count_bits = max(1, math.ceil(math.log2(depth + 1)))
        if initializer is None:
            initializer = [0] * depth
        elif len(initializer) != depth:
            raise ValueError(f"Queue initializer length {len(initializer)} does not match depth {depth}.")

        self._dtype = dtype
        self._storage = RegArray(dtype, depth, initializer=initializer)
        self._head = RegArray(Bits(self.addr_bits), 1, initializer=[0])
        self._tail = RegArray(Bits(self.addr_bits), 1, initializer=[default_count % depth])
        self._count = RegArray(Bits(self.count_bits), 1, initializer=[default_count])

        self._last_index = UInt(self.addr_bits)(depth - 1)
        self._one_addr = UInt(self.addr_bits)(1)
        self._one = UInt(self.count_bits)(1)
        self._count_full = Bits(self.count_bits)(depth)
        self._zero_addr = Bits(self.addr_bits)(0)
        self._zero = Bits(self.count_bits)(0)

    def is_full(self) -> Value:
        return self._count[0] == self._count_full

    def is_empty(self) -> Value:
        return self._count[0] == Bits(self.count_bits)(0)

    def count(self) -> Value:
        return self._count[0]

    def __getitem__(self, index: int | Value) -> ArrayRead:
        return self._storage.__getitem__(index)

    def __setitem__(self, index: int | Value, value):
        return self._storage.__setitem__(index, value)

    def front(self) -> ArrayRead:
        return self._storage[self._head[0]]

    def operate(
        self,
        *,
        push_enable: Value,
        push_data: Value | RecordValue,
        pop_enable: Value,
        clear: Optional[Value] = None,
    ) -> ArrayRead:
        """Drive the queue for a single cycle and expose its handshake signals."""

        clear_value = Bits(1)(0) if clear is None else clear

        empty = self.is_empty()
        full = self.is_full()

        assume(~(pop_enable & empty))
        assume(~(push_enable & full))

        pop_data = self._storage[self._head[0]]

        with Condition(push_enable & ~clear_value):
            self._storage[self._tail[0]] = push_data

        next_head = self._increment_pointer(self._head[0])
        next_tail = self._increment_pointer(self._tail[0])

        with Condition(pop_enable & ~clear_value):
            self._head[0] = next_head
        with Condition(push_enable & ~clear_value):
            self._tail[0] = next_tail

        count_uint = self._count[0].bitcast(UInt(self.count_bits))
        inc_value = (count_uint + self._one).bitcast(Bits(self.count_bits))
        dec_value = (count_uint - self._one).bitcast(Bits(self.count_bits))

        with Condition(push_enable & ~pop_enable & ~clear_value):
            self._count[0] = inc_value
        with Condition(pop_enable & ~push_enable & ~clear_value):
            self._count[0] = dec_value

        with Condition(clear_value):
            self._head[0] = self._zero_addr
            self._tail[0] = self._zero_addr
            self._count[0] = self._zero

        return pop_data

    def choose(self, selector: Callable[[ArrayRead, Value], Value]) -> CircularQueueSelection:
        """Choose the first element in the queue matching the given selector."""
        """Selector function takes (value, index) and returns Bool."""

        selected_data = self._storage[0]
        selected_index = self._zero_addr
        selected_distance = self._zero
        selected_valid = Bits(1)(0)

        pointer = self._head[0]
        distance = self._zero
        count_uint = self._count[0].bitcast(UInt(self.count_bits))

        for offset in range(self.depth):
            offset_uint = UInt(self.count_bits)(offset)
            has_entry = offset_uint < count_uint
            value = self._storage[pointer]
            matches = selector(value, pointer).bitcast(Bits(1))
            candidate_valid = has_entry & matches
            new_hit = candidate_valid & ~selected_valid

            selected_data = new_hit.select(value, selected_data)
            selected_index = new_hit.select(pointer, selected_index)
            selected_distance = new_hit.select(distance, selected_distance)
            selected_valid = selected_valid | candidate_valid

            pointer = self._increment_pointer(pointer)
            distance_uint = distance.bitcast(UInt(self.count_bits))
            incremented_distance = (distance_uint + self._one).bitcast(Bits(self.count_bits))
            distance = incremented_distance

        if isinstance(self._dtype, Record):
            data = self._dtype.view(selected_data)
        else:
            data = selected_data

        return CircularQueueSelection(
            data=data,
            index=selected_index,
            distance=selected_distance,
            valid=selected_valid,
        )

    def get_tail(self) -> Value:
        return self._tail[0]
    
    def get_head(self) -> Value:
        return self._head[0]

    def _increment_pointer(self, pointer: Value) -> Value:
        pointer_uint = pointer.bitcast(UInt(self.addr_bits))
        wrapped = pointer_uint == self._last_index
        incremented = pointer_uint + self._one_addr
        next_value = wrapped.select(UInt(self.addr_bits)(0), incremented)
        return next_value.bitcast(Bits(self.addr_bits))
