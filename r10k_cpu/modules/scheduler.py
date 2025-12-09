from assassyn.frontend import *
from r10k_cpu.common import LSQEntryType, ROBEntryType
from dataclass.circular_queue import CircularQueueSelection
from r10k_cpu.downstreams.alu_queue import ALUQueue
from r10k_cpu.downstreams.lsq import LSQ
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
        store_buffer: Array,
        register_ready: RegisterReady,
        alu: Module,
        lsu: Module,
    ):
        """Select ready instructions from active list and LSQ for execution."""
        alu_selection = alu_queue.select_first_ready(register_ready=register_ready)
        lsq_selection = lsq.select_first_ready(register_ready=register_ready)

        buffer_instr = LSQEntryType.view(store_buffer[0])

        with Condition(buffer_instr.valid):
            # You can transform it to RecordValue and check its valid field
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

        return SchedulerDownEntry(
            alu_selection=alu_selection,
            alu=alu,
            alu_queue=alu_queue,
            is_store_buffer_valid=buffer_instr.valid,
            lsu=lsu,
            lsq_selection=lsq_selection,
            lsq=lsq,
        )
