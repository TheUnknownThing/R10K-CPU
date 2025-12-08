from assassyn.frontend import *
from assassyn.backend import *
from assassyn import utils
from typing import List

from r10k_cpu.downstreams.free_list import FreeList
from r10k_cpu.downstreams.active_list import ActiveList
from r10k_cpu.downstreams.alu_queue import ALUQueue
from r10k_cpu.downstreams.lsq import LSQ
from r10k_cpu.downstreams.map_table import MapTable, MapTableWriteEntry
from r10k_cpu.modules.commit import Commit
from r10k_cpu.modules.decoder import Decoder
from r10k_cpu.modules.driver import Driver
from r10k_cpu.modules.lsu import LSU
from r10k_cpu.modules.alu import ALU
from r10k_cpu.modules.writeback import WriteBack

DEFAULT_WORKSPACE = Path(__file__).with_name(".workspace")


def build_cpu(
    workspace: Path | str | None = None,
    sim_threshold: int = 256,
    idle_threshold: int = 256,
):
    """Build and elaborate the Naive memory-capable RV32I CPU."""

    if sim_threshold <= 0 or idle_threshold <= 0:
        raise ValueError("Thresholds must be positive.")

    workspace_path = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE
    workspace_path.mkdir(parents=True, exist_ok=True)

    data_image_file = workspace_path / "data.hex"
    words: List[int] = []
    if data_image_file.exists():
        with open(data_image_file, "r", encoding="utf-8") as src:
            for raw in src:
                raw = raw.split("//")[0].strip()
                if not raw:
                    continue
                words.append(int(raw, 16))

    data_word_depth = max(1, (len(words) + 3) // 4)

    sys = SysBuilder("MIPS_R10K_OoO")

    with sys:
        driver = Driver()
        commit = Commit()
        free_list = FreeList(register_number=2**6)  # 64 physical registers
        active_list = ActiveList(depth=2**5)  # Active List depth = 32
        alu = ALU()
        lsu = LSU()
        writeback = WriteBack()
        alu_queue = ALUQueue(depth=2**5)  # ALU Queue depth = 32
        lsq = LSQ(depth=2**5)  # LSQ depth = 32
        map_table = MapTable(num_logical=32, physical_bits=6)
        decoder = Decoder()

        physical_register_file = RegArray(Bits(32), 64, initializer=[0] * 64)
        # NOTE: register_ready indicates whether a physical register contains valid data.
        # It is maintained by Writeback stage (sets to 1) and Commit stage (sets to 0).
        register_ready = RegArray(
            Bits(1), 64, initializer=[1] * 64
        )  # All registers are free at start

        dcache = SRAM(width=32, depth=data_word_depth, init_file=str(data_image_file))
        dcache.name = "memory_data"

        driver.build(commit=commit)

        (
            pop_instruction,
            alu_pop,
            mem_pop,
            old_physical,
            commit_write_enable,
            commit_logical,
            commit_physical,
            flush_recover,
        ) = commit.build(
            active_list_queue=active_list.queue,
            register_ready=register_ready,
        )

        alu.build(
            physical_register_file=physical_register_file,
            register_ready=register_ready,
            active_list=active_list,
        )

        lsu.build(
            physical_register_file=physical_register_file,
            memory=dcache,
            wb=writeback,
        )

        writeback.build(
            active_list=active_list,
            register_ready=register_ready,
            physical_register_file=physical_register_file,
            memory=dcache,
        )

        (
            active_list_entry_partial,
            alu_push_enable,
            alu_queue_entry,
            lsq_push_enable,
            lsq_entry,
            free_list_pop_enable,
            map_table_entry,
        ) = decoder.build(dcache.dout, map_table, free_list, active_list)

        # TODO: Branch prediction is temporarily always jump
        active_list_entry = active_list_entry_partial(predict_branch=Bits(1)(1))

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
            push_enable=pop_instruction,
            push_data=old_physical,
            pop_enable=free_list_pop_enable,
        )

        active_list_idx = active_list.build(
            pop_enable=pop_instruction,
            push_inst=active_list_entry,
        )

        alu_queue.build(
            pop_enable=alu_pop,
            push_enable=alu_push_enable,
            push_data=alu_queue_entry,
            active_list_idx=active_list_idx,
        )

        lsq.build(
            pop_enable=mem_pop,
            push_enable=lsq_push_enable,
            push_data=lsq_entry,
            active_list_idx=active_list_idx,
        )

    print(sys)
    conf = config(
        verilog=utils.has_verilator(), # pyright: ignore[reportArgumentType]
        sim_threshold=sim_threshold,
        idle_threshold=idle_threshold,
        resource_base=str(workspace_path),
        fifo_depth=1,
    )

    simulator_path, verilog_path = elaborate(sys, **conf)
    print("Building simulator binary...")
    simulator_binary = utils.build_simulator(simulator_path)
    print(f"Simulator binary built: {simulator_binary}")
    return sys, simulator_binary, verilog_path


if __name__ == "__main__":
    sys, simulator_binary, verilog_path = build_cpu()
    sim_output = utils.run_simulator(binary_path=simulator_binary)
    print("Simulation output:\n", sim_output)
    utils.run_verilator(verilog_path)
