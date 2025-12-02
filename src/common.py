from assassyn.frontend import Bits, Record
from .config import data_depth

# TODO: This is subject to change based on design

rob_entry = Record(
    valid=Bits(1),
    pc=Bits(32),
    dest_logical=Bits(5),
    dest_new_physical=Bits(5),
    dest_old_physical=Bits(5),
    ready=Bits(1),
    mispredicted=Bits(1),
)

lsq_status = Record(
    addr_ready=Bits(1),
    data_ready=Bits(1),
    committed=Bits(1),
)

lsq_entry = Record(
    valid=Bits(1),
    rob_idx=Bits(5),
    addr=Bits(data_depth),
    physical_reg=Bits(5),
    offset=Bits(32), # TODO: FIX THIS
    status=lsq_status
)
