from assassyn.frontend import *
from assassyn.backend import *
from assassyn import utils

DEFAULT_WORKSPACE = Path(__file__).with_name(".workspace")

def build_cpu(
    depth_log: int = 4,
    workspace: Path | str | None = None,
    sim_threshold: int = 256,
    idle_threshold: int = 256,
):
    """Build and elaborate the Naive memory-capable RV32I CPU."""

    if depth_log <= 0:
        raise ValueError("depth_log must be positive.")
    if sim_threshold <= 0 or idle_threshold <= 0:
        raise ValueError("Thresholds must be positive.")
    
    workspace_path = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE
    workspace_path.mkdir(parents=True, exist_ok=True)

    sys = SysBuilder("MIPS_R10K_OoO")

    with sys:
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
