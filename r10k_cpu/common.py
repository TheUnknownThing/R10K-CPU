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
    predict_branch=Bits(1),
    actual_branch=Bits(1),
)

lsq_status_type = Record(
    addr_ready=Bits(1),
    data_ready=Bits(1),
    committed=Bits(1),
)

lsq_entry_type = Record(
    valid=Bits(1),
    rob_idx=Bits(5),
    addr=Bits(data_depth),
    physical_reg=Bits(6),
    offset=Bits(32),  # TODO: FIX THIS
    status=lsq_status_type,
)
