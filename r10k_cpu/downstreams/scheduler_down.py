from dataclasses import dataclass
from assassyn.frontend import *
from assassyn.ir.dtype import RecordValue
from dataclass.circular_queue import CircularQueueSelection
from r10k_cpu.downstreams.alu_queue import ALUQueue
from r10k_cpu.downstreams.lsq import LSQ


@dataclass(frozen=True)
class SchedulerDownEntry:
    alu_selection: CircularQueueSelection
    alu: Module
    alu_queue: ALUQueue
    buffer_valid: Value
    buffer_instr: RecordValue
    lsu: Module
    lsq_selection: CircularQueueSelection
    lsq: LSQ


class SchedulerDown(Downstream):
    def __init__(self):
        super().__init__()

    @downstream.combinational
    def build(self, entry: SchedulerDownEntry, flush: Value):
        flush = flush.optional(Bits(1)(0))
        buffer_valid = entry.buffer_valid.optional(Bits(1)(0))

        with Condition(entry.alu_selection.valid.optional(Bits(1)(0)) & ~flush):
            entry.alu_queue.mark_issued(index=entry.alu_selection.index)
            entry.alu.async_called(instr=entry.alu_selection.data)

        issue_lsq = (
            entry.lsq_selection.valid.optional(Bits(1)(0)) & ~buffer_valid & ~flush
        )

        with Condition(issue_lsq):
            entry.lsq.mark_issued(index=entry.lsq_selection.index)

        with Condition(issue_lsq | buffer_valid):
            entry.lsu.async_called(
                instr=buffer_valid.select(
                    entry.buffer_instr.value(), entry.lsq_selection.data.value()
                )
            )
