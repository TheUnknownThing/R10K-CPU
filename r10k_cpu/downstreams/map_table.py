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

        storage_dtype = Bits(self._storage_bits)

        # _spec_table holds the speculative mappings, commit_table holds the committed mappings
        self._spec_table = RegArray(storage_dtype, 1, initializer=[0])
        self._commit_table = RegArray(storage_dtype, 1, initializer=[0])

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
        rename_write: MapTableWriteEntry ,
        commit_write: MapTableWriteEntry,
        flush_to_commit: Value,
    ) -> None:
        rename_en = rename_write.enable.optional(Bits(1)(0))
        rename_logical = rename_write.logical_idx.optional(Bits(self._index_bits)(0))
        rename_physical = rename_write.physical_value.optional(Bits(self.physical_bits)(0))

        commit_en = commit_write.enable.optional(Bits(1)(0))
        commit_logical = commit_write.logical_idx.optional(Bits(self._index_bits)(0))
        commit_physical = commit_write.physical_value.optional(Bits(self.physical_bits)(0))

        spec_bits = self._spec_table[0].bitcast(UInt(self._storage_bits))
        commit_bits = self._commit_table[0].bitcast(UInt(self._storage_bits))

        flush_bit = flush_to_commit.bitcast(Bits(1))

        commit_bits_next = self._apply_write(commit_bits, commit_en, commit_logical, commit_physical)
        spec_after_flush = flush_bit.select(commit_bits_next, spec_bits)
        spec_bits_next = self._apply_write(spec_after_flush, flush_bit.select(self._zero_enable, rename_en), rename_logical, rename_physical)

        self._commit_table[0] = commit_bits_next.bitcast(Bits(self._storage_bits))
        self._spec_table[0] = spec_bits_next.bitcast(Bits(self._storage_bits))

    def read_spec(self, logical_idx: Value) -> Value:
        """Read the speculative physical mapping for a given logical index."""
        return self._read_entry(self._spec_table[0], logical_idx)

    def read_commit(self, logical_idx: Value) -> Value:
        """Read the committed physical mapping for a given logical index."""
        return self._read_entry(self._commit_table[0], logical_idx)

    def spec_state(self) -> Value:
        return self._spec_table[0]

    def commit_state(self) -> Value:
        return self._commit_table[0]

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
        base_bits = base_value.bitcast(Bits(self._storage_bits))

        chunks = []
        for i in range(self.num_logical):
            lo, hi = self._entry_ranges[i]
            chunk = base_bits[lo:hi]
            
            is_target = (idx_bits == self._index_literals[i])
            should_update = is_target & enable_bit
            
            new_chunk = should_update.select(phys_bits, chunk)
            chunks.append(new_chunk)

        # Concatenate chunks. concat expects MSB first, so we reverse the list.
        # chunks[0] is LSB (index 0), chunks[-1] is MSB.
        result = concat(*reversed(chunks))

        return result.bitcast(UInt(self._storage_bits))

    def _read_entry(self, table_value: Value, logical_idx: Value) -> Value:
        idx_bits = logical_idx.bitcast(Bits(self._index_bits))
        result = Bits(self.physical_bits)(0)

        for literal, (lo, hi) in zip(self._index_literals, self._entry_ranges):
            chunk = table_value[lo:hi]
            match = idx_bits == literal
            result = match.select(chunk, result)

        return result
