from assassyn.frontend import *
from assassyn.ir.dtype import RecordValue
from r10k_cpu.common import LSQEntryType

class LSU(Module):
    """Performs load and store operations."""

    def __init__(self):
        super().__init__(ports={"instr": Port(LSQEntryType)})
        self.name = "LSU"
    
    @module.combinational
    def build(self, physical_register_file: Array, memory: SRAM, wb: Module):
        instr: RecordValue = LSQEntryType.view(self.pop_all_ports(False))
        
        store_active = (instr.is_store & instr.valid).bitcast(Bits(1)) # store only when committed
        load_active = (instr.is_load & instr.valid).bitcast(Bits(1))
        need_update_active_list = load_active # store instruction always has ready bit.

        addr = (physical_register_file[instr.rs1_physical].bitcast(Int(32)) + instr.imm.bitcast(Int(32))).bitcast(Bits(32))[2:31].zext(Bits(32))
        val = store_active.select(physical_register_file[instr.rs2_physical], Bits(32)(0))

        # YEAH... Assassyn do not support writing a half word or a byte yet...
        # So we just write a full word always.
        memory.build(we=store_active, re=load_active, addr=addr[0:19], wdata=val)

        wb.async_called(
            is_load=load_active,
            is_store=store_active,
            need_update_active_list=need_update_active_list,
            op_type=instr.op_type,
            dest_physical=instr.rd_physical,
            active_list_idx=instr.active_list_idx,
            addr=addr,
        )
