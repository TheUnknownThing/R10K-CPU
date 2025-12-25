from assassyn.frontend import *
from assassyn.backend import *
from assassyn import utils
from typing import List

from r10k_cpu.downstreams.fetcher_impl import FetcherImpl
from r10k_cpu.downstreams.free_list import FreeList
from r10k_cpu.downstreams.active_list import ActiveList
from r10k_cpu.downstreams.alu_queue import ALUQueue
from r10k_cpu.downstreams.lsq import LSQ, StoreBuffer
from r10k_cpu.downstreams.map_table import MapTable, MapTableWriteEntry
from r10k_cpu.downstreams.register_ready import RegisterReady
from r10k_cpu.downstreams.predictor import (
    AlwaysBranchPredictor,
    PredictFeedback,
    Predictor,
)
from r10k_cpu.downstreams.scheduler_down import SchedulerDown
from r10k_cpu.downstreams.speculation_state import SpeculationState
from r10k_cpu.modules.commit import Commit
from r10k_cpu.modules.decoder import Decoder
from r10k_cpu.modules.driver import Driver
from r10k_cpu.modules.fetcher import Fetcher
from r10k_cpu.modules.lsu import LSU
from r10k_cpu.modules.alu import ALU, Multiply_ALU
from r10k_cpu.modules.writeback import WriteBack
from r10k_cpu.modules.scheduler import Scheduler

from r10k_cpu.common import LSQEntryType


def build_cpu(
    sram_file: str | None = None,
    verilog: bool = False,
    resource_base: str = os.getcwd(),
    sim_threshold: int = 20480,
    idle_threshold: int = 20480,
):
    """Build and elaborate the Naive memory-capable RV32I CPU."""

    if sim_threshold <= 0 or idle_threshold <= 0:
        raise ValueError("Thresholds must be positive.")

    sys = SysBuilder("MIPS_R10K_OoO")

    with sys:
        driver = Driver()
        commit = Commit()
        free_list = FreeList(register_number=2**6)  # 64 physical registers
        active_list = ActiveList(depth=2**5)  # Active List depth = 32
        alu = ALU()
        mul_alu = Multiply_ALU()
        lsu = LSU()
        writeback = WriteBack()
        alu_queue = ALUQueue(depth=2**5)  # ALU Queue depth = 32
        lsq = LSQ(depth=2**5)  # LSQ depth = 32
        map_table = MapTable(num_logical=32, physical_bits=6)
        decoder = Decoder()
        fetcher = Fetcher()
        fetcher_impl = FetcherImpl()
        speculation_state = SpeculationState()
        scheduler = Scheduler()
        scheduler_down = SchedulerDown()
        predictor: Predictor = AlwaysBranchPredictor()

        physical_register_file = RegArray(Bits(32), 64, initializer=[0] * 64)
        # Tracks readiness of each physical register; packed so we can atomically reset on flush.
        register_ready = RegisterReady(num_registers=64)

        # This buffer stores store instruction that have been committed but not yet executed.
        store_buffer = StoreBuffer()

        dcache = SRAM(width=32, depth=0x100000, init_file=sram_file)
        dcache.name = "memory_data"

        icache = SRAM(width=32, depth=0x100000, init_file=sram_file)
        icache.name = "memory_instruction"

        PC_reg, PC_addr = fetcher.build()

        driver.build(fetcher=fetcher, commit=commit, scheduler=scheduler)

        (
            push_freelist,
            pop_activelist,
            alu_pop,
            mem_pop,
            old_physical,
            commit_write_enable,
            commit_logical,
            commit_physical,
            flush_recover,
            fetcher_flush_entry,
            out_branch,
        ) = commit.build(
            active_list_queue=active_list.queue,
            map_table=map_table,
            register_file=physical_register_file,
        )

        alu.build(
            physical_register_file=physical_register_file,
            register_ready=register_ready,
            active_list=active_list,
        )

        mul_alu.build(
            physical_register_file=physical_register_file,
            register_ready=register_ready,
            active_list=active_list,
            flush=commit.flush,
        )

        lsu.build(
            physical_register_file=physical_register_file,
            memory=dcache,
            wb=writeback,
        )

        scheduler_down_entry, store_buffer_pop_enable = scheduler.build(
            alu_queue=alu_queue,
            lsq=lsq,
            store_buffer=store_buffer,
            register_ready=register_ready,
            alu=alu,
            multiply_alu=mul_alu,
            lsu=lsu,
        )

        scheduler_down.build(scheduler_down_entry, flush_recover)

        writeback.build(
            active_list=active_list,
            register_ready=register_ready,
            physical_register_file=physical_register_file,
            memory=dcache,
        )

        (
            fetcher_entry,
            active_list_entry_partial,
            alu_push_enable,
            alu_queue_entry,
            lsq_push_enable,
            lsq_entry,
            free_list_pop_enable,
            map_table_entry,
            into_speculating,
        ) = decoder.build(
            icache.dout,
            map_table,
            free_list,
            active_list,
            speculation_state,
            register_ready,
        )

        # TODO: Branch prediction is temporarily always jump
        predict_branch = predictor.build(
            alu_queue_entry.PC,
            PredictFeedback(
                Bits(32)(0),
                Bits(1)(0),
                Bits(1)(0),
            ),
        )

        fetcher_impl.build(
            PC_reg=PC_reg,
            PC_addr=PC_addr,
            decoder=decoder,
            icache=icache,
            entry=fetcher_entry,
            flush_entry=fetcher_flush_entry,
            predict_branch=predict_branch,
        )

        active_list_entry = active_list_entry_partial(predict_branch=predict_branch)

        commit_write = MapTableWriteEntry(
            enable=commit_write_enable,
            logical_idx=commit_logical,
            physical_value=commit_physical,
        )

        map_table.build(
            rename_write=map_table_entry,
            commit_write=commit_write,
            flush_to_commit=flush_recover,
        )

        free_list.build(
            push_enable=push_freelist,
            push_data=old_physical,
            pop_enable=free_list_pop_enable,
            make_snapshot=into_speculating,
            flush_recover=flush_recover,
        )

        active_list_idx = active_list.build(
            pop_enable=pop_activelist,
            push_inst=active_list_entry,
            flush=flush_recover,
        )

        alu_queue.build(
            pop_enable=alu_pop,
            push_enable=alu_push_enable,
            push_data=alu_queue_entry,
            active_list_idx=active_list_idx,
            flush=flush_recover,
        )

        store_buffer_push_enable, store_buffer_push_data = lsq.build(
            pop_enable=mem_pop,
            push_enable=lsq_push_enable,
            push_data=lsq_entry,
            active_list_idx=active_list_idx,
            flush=flush_recover,
        )

        speculation_state.build(
            into_speculating=into_speculating,
            out_speculating=out_branch,
        )

        register_ready.build(flush_recover=flush_recover)

        store_buffer.build(
            push_enable=store_buffer_push_enable,
            push_data=store_buffer_push_data,
            pop_enable=store_buffer_pop_enable,
        )

        sys.expose_on_top(PC_reg, "Output")
        sys.expose_on_top(physical_register_file, "Output")

    conf = config(
        verilog=verilog,  # pyright: ignore[reportArgumentType]
        verbose=False,
        sim_threshold=sim_threshold,
        idle_threshold=idle_threshold,
        resource_base=resource_base,
        fifo_depth=1,
    )

    simulator_path, verilog_path = elaborate(sys, **conf)
    return sys, simulator_path, verilog_path


if __name__ == "__main__":
    sys, simulator_path, verilog_path = build_cpu(
        sram_file="asms/sum100/sum100.hex",
        verilog=True,
        sim_threshold=3000,
    )
    sim_output = utils.run_simulator(simulator_path)
    with open("out/sum100_sim.out", "w") as f:
        f.write(sim_output)
    ver_output = utils.run_verilator(verilog_path)
    with open("out/sum100_ver.out", "w") as f:
        f.write(ver_output)
