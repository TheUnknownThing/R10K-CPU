from __future__ import annotations

import math
from dataclasses import dataclass

from assassyn.frontend import *


@dataclass(frozen=True)
class RegisterReadyWrite:
    enable: Value
    physical_idx: Value
    ready_value: Value


class RegisterReady(Downstream):
    """
    Tracks whether each physical register holds valid data.

    Backed by a single packed register so we can atomically reset all bits on flush.
    Writers register their intents via mark_ready/mark_not_ready before build() is called.
    """

    def __init__(self, num_registers: int = 64):
        if num_registers <= 0:
            raise ValueError("num_registers must be positive")
        super().__init__()

        self.num_registers = num_registers
        self.index_bits = max(1, math.ceil(math.log2(num_registers)))
        storage_dtype = Bits(num_registers)

        self._ready_bits = RegArray(
            storage_dtype, 1, initializer=[(1 << num_registers) - 1]
        )
        self._writes: list[RegisterReadyWrite] = []

        self._all_ready = UInt(num_registers)((1 << num_registers) - 1)

    def mark_ready(self, physical_idx: Value, enable: Value) -> None:
        self._writes.append(
            RegisterReadyWrite(
                enable=enable,
                physical_idx=physical_idx,
                ready_value=Bits(1)(1),
            )
        )

    def mark_not_ready(self, physical_idx: Value, enable: Value) -> None:
        self._writes.append(
            RegisterReadyWrite(
                enable=enable,
                physical_idx=physical_idx,
                ready_value=Bits(1)(0),
            )
        )

    def read(self, physical_idx: Value) -> Value:
        idx  = physical_idx.bitcast(UInt(self.index_bits))
        bits = self._ready_bits[0].bitcast(UInt(self.num_registers))
        return ((bits >> idx) & UInt(1)(1)).bitcast(Bits(1))

    def state(self) -> Value:
        return self._ready_bits[0]

    @downstream.combinational
    def build(self, *, flush_recover: Value):
        flush_bit = flush_recover.optional(Bits(1)(0))
        ready_uint = self._ready_bits[0].bitcast(UInt(self.num_registers))
        next_ready = ready_uint

        zero_enable = Bits(1)(0)
        zero_idx = Bits(self.index_bits)(0)

        for write in self._writes:
            en = write.enable.optional(zero_enable)
            idx = write.physical_idx.optional(zero_idx)
            next_ready = self._apply_write(next_ready, en, idx, write.ready_value)

        next_ready = flush_bit.select(self._all_ready, next_ready)
        self._ready_bits[0] = next_ready.bitcast(Bits(self.num_registers))

    def _apply_write(
        self, base_value: Value, enable: Value, idx: Value, ready_value: Value
    ) -> Value:
        enable_bit = enable.bitcast(Bits(1))
        ready_bit  = ready_value.bitcast(Bits(1))

        idx_uint = idx.bitcast(UInt(self.index_bits))

        base_bits = base_value.bitcast(Bits(self.num_registers))

        one_hot_uint = UInt(self.num_registers)(1) << idx_uint
        mask_bits    = one_hot_uint.bitcast(Bits(self.num_registers))

        full_bits    = self._all_ready.bitcast(Bits(self.num_registers))
        inv_mask_bits = full_bits ^ mask_bits

        set_bits   = base_bits | mask_bits
        clear_bits = base_bits & inv_mask_bits

        updated_bits = ready_bit.select(set_bits, clear_bits)
        result_bits = enable_bit.select(updated_bits, base_bits)

        return result_bits.bitcast(UInt(self.num_registers))
