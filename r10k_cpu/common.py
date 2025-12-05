from assassyn.frontend import Bits, Record
from .config import data_depth

# TODO: This is subject to change based on design

rob_entry_type = Record(
    pc=Bits(32),
    dest_logical=Bits(5),
    dest_new_physical=Bits(6),
    dest_old_physical=Bits(6),
    ready=Bits(1),
    is_branch=Bits(1),
    is_alu=Bits(1),             # 1 for ALU, 0 for LSQ
    predict_branch=Bits(1),
    actual_branch=Bits(1),      # waiting ALU to fill this in
)

lsq_status_type = Record(
    addr_ready=Bits(1),
    data_ready=Bits(1),
    committed=Bits(1),
)

lsq_entry_type = Record(
    valid=Bits(1),
    active_list_idx=Bits(5),
    lsq_queue_idx=Bits(5),
    address=Bits(data_depth),
    data=Bits(32),
    is_load=Bits(1),
    is_store=Bits(1),
    op_type=Bits(3),  # load/store type
    # TODO: ad lsq entry status
)

# NOTE: this is subject to change based on design
alu_queue_entry_type = Record(
    valid=Bits(1),
    active_list_idx=Bits(5),
    alu_queue_idx=Bits(5),
    rs1_physical=Bits(6),
    rs2_physical=Bits(6),
    rd_physical=Bits(6),
    alu_op=Bits(4),
    imm=Bits(32),
)