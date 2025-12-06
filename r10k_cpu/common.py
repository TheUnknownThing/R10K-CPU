from enum import Enum
from math import ceil, log2
from assassyn.frontend import Bits, Record

# TODO: This is subject to change based on design

rob_entry_type = Record(
    pc=Bits(32),
    dest_logical=Bits(5),
    dest_new_physical=Bits(6),
    dest_old_physical=Bits(6),
    imm=Bits(32),
    ready=Bits(1),
    is_branch=Bits(1),
    is_alu=Bits(1),  # 1 for ALU, 0 for LSQ
    predict_branch=Bits(1),
    actual_branch=Bits(1),  # waiting ALU to fill this in
)


class MemoryOpType(Enum):
    BYTE = 0
    HALF = 1
    WORD = 2
    BYTE_U = 3
    HALF_U = 4


MEMORY_OP_TYPE_LEN = ceil(log2(len(MemoryOpType)))


lsq_entry_type = Record(
    valid=Bits(1),
    active_list_idx=Bits(5),
    lsq_queue_idx=Bits(5),
    rs1_physical=Bits(6),
    rs2_physical=Bits(6),
    rd_physical=Bits(6),
    imm=Bits(32),
    is_load=Bits(1),
    is_store=Bits(1),
    op_type=Bits(MEMORY_OP_TYPE_LEN),
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
    rs1_needed=Bits(1),
    rs2_needed=Bits(1),
    PC=Bits(32),
)
