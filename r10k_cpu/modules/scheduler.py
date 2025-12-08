from assassyn.frontend import *
from r10k_cpu.common import LSQEntryType, ROBEntryType
from dataclass.circular_queue import CircularQueueSelection
from r10k_cpu.downstreams.alu_queue import ALUQueue
from r10k_cpu.downstreams.lsq import LSQ

class Scheduler(Module):
    """Schedules instructions for execution"""

    def __init__(self):
        super().__init__(ports={})
        self.name = "Scheduler"

    @module.combinational
    def build(self, alu_queue: ALUQueue, lsq: LSQ, store_buffer: Array, register_ready: Array, alu: Module, lsu: Module):
        """Select ready instructions from active list and LSQ for execution."""
        alu_selection = alu_queue.select_first_ready(register_ready=register_ready)
        lsq_selection = lsq.select_first_ready(register_ready=register_ready)

        buffer_instr = store_buffer[0]
        
        with Condition(alu_selection.valid):
            alu_queue.mark_issued(index=alu_selection.index)
            alu.async_called(instr=alu_selection.data)
        
        with Condition(buffer_instr.is_store):
            # NOTE: why we use is_store here?
            # Because the `buffer_instr.valid` refers to the buildin method of the ArrayRead
            lsu.async_called(instr=buffer_instr)
            store_buffer[0] = LSQEntryType.bundle(
                valid=Bits(1)(0),
                active_list_idx=Bits(5)(0),
                lsq_queue_idx=Bits(5)(0),
                imm=Bits(32)(0),
                is_load=Bits(1)(0),
                is_store=Bits(1)(0),
                op_type=Bits(3)(0),
                rd_physical=Bits(6)(0),
                rs1_physical=Bits(6)(0),
                rs2_physical=Bits(6)(0),
                issued=Bits(1)(0),
            )
        
        with Condition(lsq_selection.valid & ~buffer_instr.is_store):
            lsq.mark_issued(index=lsq_selection.index)
            lsu.async_called(instr=lsq_selection.data)
