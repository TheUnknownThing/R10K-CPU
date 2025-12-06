from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from assassyn.frontend import *


@dataclass(frozen=True)
class MapTableWriteEntry:
    enable: Value
    logical_idx: Value
    physical_value: Value


class MapTable(Downstream):
    """Multi-writer architectural-to-physical register map backed by packed registers."""

    def __init__(
        self,
        num_logical: int = 32,
        physical_bits: int = 6
    ) -> None:
        super().__init__()

        self.num_logical = num_logical
        self.physical_bits = physical_bits
        self._index_bits = max(1, math.ceil(math.log2(num_logical)))
        self._storage_bits = num_logical * physical_bits
        
        initializer = [i for i in range(num_logical)]

        packed_init = self._pack_initializer(initializer)

        storage_dtype = Bits(self._storage_bits)
        self._spec_table = RegArray(storage_dtype, 1, initializer=[packed_init])
        self._commit_table = RegArray(storage_dtype, 1, initializer=[packed_init])

        self._index_literals = [Bits(self._index_bits)(i) for i in range(num_logical)]
        self._entry_ranges = [
            (i * physical_bits, (i + 1) * physical_bits - 1) for i in range(num_logical)
        ]

        self._entry_mask = UInt(self._storage_bits)((1 << physical_bits) - 1)
        self._entry_stride = UInt(self._storage_bits)(physical_bits)
        self._zero_enable = Bits(1)(0)
        self._zero_index = Bits(self._index_bits)(0)
        self._zero_physical = Bits(self.physical_bits)(0)

    @property
    def logical_bits(self) -> int:
        return self._index_bits

    @downstream.combinational
    def build(
        self,
        *,
        rename_write: Optional[MapTableWriteEntry] = None,
        commit_write: Optional[MapTableWriteEntry] = None,
        flush_to_commit: Optional[Value] = None,
    ) -> None:
        rename_port = rename_write if rename_write is not None else self.idle_port()
        commit_port = commit_write if commit_write is not None else self.idle_port()

        rename_en = rename_port.enable
        rename_logical = rename_port.logical_idx
        rename_physical = rename_port.physical_value

        commit_en = commit_port.enable
        commit_logical = commit_port.logical_idx
        commit_physical = commit_port.physical_value

        flush = flush_to_commit if flush_to_commit is not None else self._zero_enable

        spec_bits = self._spec_table[0].bitcast(UInt(self._storage_bits))
        commit_bits = self._commit_table[0].bitcast(UInt(self._storage_bits))

        commit_bits_next = self._apply_write(commit_bits, commit_en, commit_logical, commit_physical)
        spec_after_flush = flush.select(commit_bits_next, spec_bits)
        spec_bits_next = self._apply_write(spec_after_flush, rename_en, rename_logical, rename_physical)

        self._commit_table[0] = commit_bits_next.bitcast(Bits(self._storage_bits))
        self._spec_table[0] = spec_bits_next.bitcast(Bits(self._storage_bits))

    def read_spec(self, logical_idx: Value) -> Value:
        return self._read_entry(self._spec_table[0], logical_idx)

    def read_commit(self, logical_idx: Value) -> Value:
        return self._read_entry(self._commit_table[0], logical_idx)

    def spec_state(self) -> Value:
        return self._spec_table[0]

    def commit_state(self) -> Value:
        return self._commit_table[0]

    def idle_port(self) -> MapTableWriteEntry:
        return MapTableWriteEntry(
            enable=self._zero_enable,
            logical_idx=self._zero_index,
            physical_value=self._zero_physical,
        )

    def _apply_write(
        self,
        base_value: Value,
        enable: Value,
        logical_idx: Value,
        physical_value: Value,
    ) -> Value:
        enable_bit = enable.bitcast(Bits(1))
        idx_bits = logical_idx.bitcast(Bits(self._index_bits))
        phys_bits = physical_value.bitcast(Bits(self.physical_bits))

        base_uint = base_value.bitcast(UInt(self._storage_bits))
        idx_uint = idx_bits.bitcast(UInt(self._index_bits))
        idx_wide = idx_uint.zext(UInt(self._storage_bits))
        shift_amount = idx_wide * self._entry_stride
        mask = self._entry_mask << shift_amount
        inverted_mask = (~mask).bitcast(UInt(self._storage_bits))
        cleared = base_uint & inverted_mask

        phys_uint = phys_bits.bitcast(UInt(self.physical_bits))
        phys_wide = phys_uint.zext(UInt(self._storage_bits))
        shifted = phys_wide << shift_amount

        updated = cleared | shifted
        updated_bits = updated.bitcast(Bits(self._storage_bits))
        base_bits = base_uint.bitcast(Bits(self._storage_bits))
        selected_bits = enable_bit.select(updated_bits, base_bits)
        return selected_bits.bitcast(UInt(self._storage_bits))

    def _read_entry(self, table_value: Value, logical_idx: Value) -> Value:
        idx_bits = logical_idx.bitcast(Bits(self._index_bits))
        result = Bits(self.physical_bits)(0)

        for literal, (lo, hi) in zip(self._index_literals, self._entry_ranges):
            chunk = table_value[lo:hi]
            match = idx_bits == literal
            result = match.select(chunk, result)

        return result

    def _pack_initializer(self, values: Sequence[int]) -> int:
        mask = (1 << self.physical_bits) - 1
        total = 0
        for idx, value in enumerate(values):
            total |= (value & mask) << (idx * self.physical_bits)
        return total
