from assassyn.frontend import *
from assassyn.backend import *
from assassyn import utils

from r10k_cpu.downstreams.free_list import FreeList
from r10k_cpu.downstreams.active_list import ActiveList
from r10k_cpu.downstreams.alu_queue import ALUQueue
from r10k_cpu.downstreams.lsq import LSQ
from r10k_cpu.modules.commit import Commit
from r10k_cpu.modules.driver import Driver

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

    sys = SysBuilder("MIPS_R10K_OoO")

    with sys:
        driver = Driver()
        commit = Commit()
        free_list = FreeList(register_number=2**6)  # 64 physical registers
        active_list = ActiveList(depth=2**5)  # Active List depth = 32
        alu_queue = ALUQueue(depth=2**5)  # ALU Queue depth = 32
        lsq = LSQ(depth=2**5)  # LSQ depth = 32

        map_table_0 = RegArray(Bits(6), 32, initializer=[i for i in range(32)])
        map_table_1 = RegArray(Bits(6), 32, initializer=[i for i in range(32)])
        map_table_active = RegArray(Bits(1), 1, initializer=[0])  # 0 for map_table_0, 1 for map_table_1

        physical_register_file = RegArray(Bits(32), 64, initializer=[0] * 64)
        """
        NOTE: register_ready indicates whether a physical register contains valid data. 
        It is maintained by Writeback stage (sets to 1) and Commit stage (sets to 0).
        """
        register_ready = RegArray(Bits(1), 64, initializer=[1] * 64)  # All registers are free at start

        driver.build(commit=commit)

        pop_instruction, alu_pop, mem_pop, old_physical = commit.build(
            active_list_queue=active_list.queue,
            map_table_active=map_table_active,
            map_table_0=map_table_0,
            map_table_1=map_table_1,
            register_ready=register_ready,
        )

        free_list.build(
            push_enable=pop_instruction,
            push_data=old_physical,
            # TODO: pop_enable needs to be set to ID's return signal
        )

        active_list.build(
            pop_enable=pop_instruction,
            # TODO: push_inst needs to be set to ID's return signal
        )

        alu_queue.build(
            pop_enable=alu_pop,
            # TODO: push_enable and push_data need to be set to ID's return signal
        )

        lsq.build(
            pop_enable=mem_pop,
            # TODO: push_enable and push_data need to be set to ID's return signal
        )

        pass

    print(sys)
    conf = config(
        verilog=utils.has_verilator(),
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