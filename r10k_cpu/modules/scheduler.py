from assassyn.frontend import *
from r10k_cpu.common import (
    LSQEntryType,
)
from r10k_cpu.downstreams.alu_queue import ALUQueue
from r10k_cpu.downstreams.lsq import LSQ, StoreBuffer
from r10k_cpu.downstreams.register_ready import RegisterReady
from r10k_cpu.downstreams.scheduler_down import SchedulerDownEntry


class Scheduler(Module):
    """Schedules instructions for execution"""

    def __init__(self):
        super().__init__(ports={})
        self.name = "Scheduler"

    @module.combinational
    def build(
        self,
        alu_queue: ALUQueue,
        lsq: LSQ,
        store_buffer: StoreBuffer,
        register_ready: RegisterReady,
        alu: Module,
        multiply_alu: Module,
        lsu: Module,
    ):
        """Select ready instructions from active list and LSQ for execution."""
        alu_selection = alu_queue.select_first_ready(register_ready=register_ready)
        lsq_selection = lsq.select_first_ready(register_ready=register_ready)

        buffer_instr = LSQEntryType.view(store_buffer.reg[0])

        return (
            SchedulerDownEntry(
                alu_selection=alu_selection,
                alu=alu,
                multiply_alu=multiply_alu,
                alu_queue=alu_queue,
                buffer_valid=buffer_instr.valid,
                buffer_instr=buffer_instr,
                lsu=lsu,
                lsq_selection=lsq_selection,
                lsq=lsq,
            ),
            buffer_instr.valid,
        )
