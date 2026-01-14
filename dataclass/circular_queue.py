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
        """Choose the first element in the queue matching the given selector using a tree mux."""

        pointer = self._head[0]
        distance = self._zero
        count_uint = self._count[0].bitcast(UInt(self.count_bits))

        candidates = []
        for offset in range(self.depth):
            offset_uint = UInt(self.count_bits)(offset)
            has_entry = offset_uint < count_uint
            value = self._storage[pointer]
            matches = selector(value, pointer).bitcast(Bits(1))
            candidate_valid = has_entry & matches

            candidates.append(
                (
                    value,
                    pointer,
                    distance,
                    candidate_valid,
                )
            )

            pointer = self._increment_pointer(pointer)
            distance_uint = distance.bitcast(UInt(self.count_bits))
            distance = (distance_uint + self._one).bitcast(Bits(self.count_bits))

        # Pad to the next power of two to build a balanced tree.
        if not candidates:
            raise ValueError("CircularQueue depth must be positive.")

        next_power = 1 << math.ceil(math.log2(len(candidates)))
        zero_data, zero_index, zero_distance = candidates[0][0], self._zero_addr, self._zero
        for _ in range(len(candidates), next_power):
            candidates.append((zero_data, zero_index, zero_distance, Bits(1)(0)))

        while len(candidates) > 1:
            next_layer = []
            for i in range(0, len(candidates), 2):
                left_data, left_index, left_distance, left_valid = candidates[i]
                right_data, right_index, right_distance, right_valid = candidates[i + 1]

                # Prefer the left (earlier) element when both are valid.
                chosen_data = left_valid.select(left_data, right_data)
                chosen_index = left_valid.select(left_index, right_index)
                chosen_distance = left_valid.select(left_distance, right_distance)
                chosen_valid = left_valid | right_valid

                next_layer.append((chosen_data, chosen_index, chosen_distance, chosen_valid))
            candidates = next_layer

        selected_data, selected_index, selected_distance, selected_valid = candidates[0]

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

    def get_count(self) -> Value:
        return self._count[0]

    def _increment_pointer(self, pointer: Value) -> Value:
        pointer_uint = pointer.bitcast(UInt(self.addr_bits))
        wrapped = pointer_uint == self._last_index
        incremented = pointer_uint + self._one_addr
        next_value = wrapped.select(UInt(self.addr_bits)(0), incremented)
        return next_value.bitcast(Bits(self.addr_bits))
