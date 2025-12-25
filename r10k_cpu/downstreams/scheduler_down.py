from dataclasses import dataclass
from assassyn.frontend import *
from assassyn.ir.dtype import RecordValue
from dataclass.circular_queue import CircularQueueSelection
from r10k_cpu.common import ALU_CODE_LEN, ALU_Code
from r10k_cpu.downstreams.alu_queue import ALUQueue
from r10k_cpu.downstreams.lsq import LSQ
from r10k_cpu.modules.alu import Multiply_ALU


@dataclass(frozen=True)
class SchedulerDownEntry:
    alu_selection: CircularQueueSelection
    alu: Module
    multiply_alu: Multiply_ALU
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
            is_mul = (
                (
                    entry.alu_selection.data.alu_op
                    == Bits(ALU_CODE_LEN)(ALU_Code.MUL.value)
                )
                | (
                    entry.alu_selection.data.alu_op
                    == Bits(ALU_CODE_LEN)(ALU_Code.MULH.value)
                )
                | (
                    entry.alu_selection.data.alu_op
                    == Bits(ALU_CODE_LEN)(ALU_Code.MULSU.value)
                )
                | (
                    entry.alu_selection.data.alu_op
                    == Bits(ALU_CODE_LEN)(ALU_Code.MULU.value)
                )
            )
            is_div_or_rem = (
                (
                    entry.alu_selection.data.alu_op
                    == Bits(ALU_CODE_LEN)(ALU_Code.DIV.value)
                )
                | (
                    entry.alu_selection.data.alu_op
                    == Bits(ALU_CODE_LEN)(ALU_Code.DIVU.value)
                )
                | (
                    entry.alu_selection.data.alu_op
                    == Bits(ALU_CODE_LEN)(ALU_Code.REM.value)
                )
                | (
                    entry.alu_selection.data.alu_op
                    == Bits(ALU_CODE_LEN)(ALU_Code.REMU.value)
                )
            )
            issue_mul_alu = is_mul | (is_div_or_rem & ~entry.multiply_alu.div_busy[0])
            issue_alu = ~(is_mul | is_div_or_rem)

            with Condition(issue_mul_alu):
                alu_call = entry.multiply_alu.async_called(
                    instr=entry.alu_selection.data
                )
                alu_call.bind.set_fifo_depth(instr=1)
                entry.multiply_alu.div_busy[0] = is_div_or_rem
                
            with Condition(issue_alu):
                alu_call = entry.alu.async_called(instr=entry.alu_selection.data)
                alu_call.bind.set_fifo_depth(instr=1)

            with Condition(issue_alu | issue_mul_alu):
                entry.alu_queue.mark_issued(index=entry.alu_selection.index)


        issue_lsq = (
            entry.lsq_selection.valid.optional(Bits(1)(0)) & ~buffer_valid & ~flush
        )

        with Condition(issue_lsq):
            entry.lsq.mark_issued(index=entry.lsq_selection.index)

        with Condition(issue_lsq | buffer_valid):
            lsu_call = entry.lsu.async_called(
                instr=buffer_valid.select(
                    entry.buffer_instr.value(), entry.lsq_selection.data.value()
                )
            )
            lsu_call.bind.set_fifo_depth(instr=1)
