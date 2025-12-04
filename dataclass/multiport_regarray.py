from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence, Tuple

from assassyn.frontend import *


@dataclass(frozen=True)
class DualWriteReadResult:
    """Output bundle for the multi-read view of the register file."""

    values: Tuple[Value, ...]


class DualWriteRegArray:
    """Two-write-port register array implemented with explicit indexing."""

    def __init__(
        self,
        element_shape: DType,
        depth: int,
        *,
        num_read_ports: int = 2,
        initializer: list[int] | None = None,
        name: str | None = None,
        bypass_reads: bool = True,
    ) -> None:
        if depth <= 0:
            raise ValueError("Register array depth must be positive.")
        if num_read_ports < 0:
            raise ValueError("Number of read ports cannot be negative.")
        self.depth = depth
        self.name = name or "dual_write_regarray"
        self.num_read_ports = num_read_ports
        self.addr_bits = max(1, math.ceil(math.log2(depth)))
        self._element_shape = element_shape
        self._default_bypass = bypass_reads
        if initializer is None:
            initializer = [0] * depth
        elif len(initializer) != depth:
            raise ValueError(
                f"Initializer length {len(initializer)} does not match depth {depth}."
            )

        self._storage = [
            RegArray(element_shape, 1, initializer=[value]) for value in initializer
        ]
        self._index_literals = [Bits(self.addr_bits)(idx) for idx in range(depth)]

    def read_ports(
        self,
        read_addrs: Sequence[Value]
    ) -> DualWriteReadResult:
        """Compute the read-port values without mutating state."""

        self._validate_read_port_count(read_addrs)

        read_values = []
        for addr in read_addrs:
            value = self._read_mux(addr)
            read_values.append(value)

        return DualWriteReadResult(values=tuple(read_values))

    def write_ports(
        self,
        *,
        write0_enable: Value,
        write0_addr: Value,
        write0_data: Value,
        write1_enable: Value,
        write1_addr: Value,
        write1_data: Value,
    ) -> None:
        """Apply the write ports for the current cycle."""

        both_fire = write0_enable & write1_enable
        with Condition(both_fire):
            assume(write0_addr != write1_addr)

        self._commit_writes(
            write0_enable=write0_enable,
            write0_addr=write0_addr,
            write0_data=write0_data,
            write1_enable=write1_enable,
            write1_addr=write1_addr,
            write1_data=write1_data,
        )


    def _validate_read_port_count(self, read_addrs: Sequence[Value]) -> None:
        if len(read_addrs) != self.num_read_ports:
            raise ValueError(
                f"Expected {self.num_read_ports} read addresses, got {len(read_addrs)}."
            )

    def _commit_writes(
        self,
        *,
        write0_enable: Value,
        write0_addr: Value,
        write0_data: Value,
        write1_enable: Value,
        write1_addr: Value,
        write1_data: Value,
    ) -> None:
        for idx, literal in enumerate(self._index_literals):
            port0_hit = write0_enable & (write0_addr == literal)
            port1_hit = write1_enable & (write1_addr == literal)
            any_hit = port0_hit | port1_hit

            current_value = self._storage[idx][0]
            next_value = port0_hit.select(write0_data, current_value)
            next_value = port1_hit.select(write1_data, next_value)

            with Condition(any_hit):
                self._storage[idx][0] = next_value

    def _read_mux(self, addr: Value) -> Value:
        value = self._storage[0][0]
        for idx in range(1, self.depth):
            literal = self._index_literals[idx]
            match = addr == literal
            value = match.select(self._storage[idx][0], value)
        return value
