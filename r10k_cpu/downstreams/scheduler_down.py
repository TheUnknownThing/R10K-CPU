from dataclasses import dataclass
from assassyn.frontend import *
from dataclass.circular_queue import CircularQueueSelection
from r10k_cpu.downstreams.alu_queue import ALUQueue
from r10k_cpu.downstreams.lsq import LSQ


@dataclass(frozen=True)
class SchedulerDownEntry:
    alu_selection: CircularQueueSelection
    alu: Module
    alu_queue: ALUQueue
    is_store_buffer_valid: Value
    lsu: Module
    lsq_selection: CircularQueueSelection
    lsq: LSQ


class SchedulerDown(Downstream):
    def __init__(self):
        super().__init__()

    @downstream.combinational
    def build(self, entry: SchedulerDownEntry, flush: Value):
        flush = flush.optional(Bits(1)(0))

        with Condition(entry.alu_selection.valid.optional(Bits(1)(0)) & ~flush):
            entry.alu_queue.mark_issued(index=entry.alu_selection.index)
            entry.alu.async_called(instr=entry.alu_selection.data)

        with Condition(
            entry.lsq_selection.valid.optional(Bits(1)(0))
            & ~entry.is_store_buffer_valid.optional(Bits(1)(0))
            & ~flush
        ):
            entry.lsq.mark_issued(index=entry.lsq_selection.index)
            entry.lsu.async_called(instr=entry.lsq_selection.data)
