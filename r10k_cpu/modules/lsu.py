from assassyn.frontend import *
from r10k_cpu.downstreams.active_list import ActiveList
from r10k_cpu.common import LSQEntryType

class LSU(Module):
    """Performs load and store operations."""

    def __init__(self):
        super().__init__(ports={"instr": LSQEntryType, "committed": Bits(1)})
        self.name = "LSU"
    
    @module.combinational
    def build(self, physical_register_file: Array, memory: SRAM, wb: Module):
        instr, committed = self.pop_all_ports(False)
        
        store_active = (instr.is_store & instr.valid & committed).bitcast(Bits(1)) # store only when committed
        load_active = (instr.is_load & instr.valid).bitcast(Bits(1))
        need_update_active_list = (instr.is_load & instr.valid).bitcast(Bits(1)) | (instr.is_store & instr.valid & ~committed).bitcast(Bits(1))

        addr = (physical_register_file[instr.rs1_physical].bitcast(Int(32)) + instr.imm.bitcast(Int(32))).bitcast(Bits(32))
        val = instr.is_store.select(physical_register_file[instr.rs2_physical], Bits(32)(0))

        # YEAH... Assassyn do not support writing a half word or a byte yet...
        # So we just write a full word always.
        memory.build(we=store_active, re=load_active, addr=addr, wdata=val)

        wb.async_called(
            is_load=load_active,
            is_store=store_active,
            need_update_active_list=need_update_active_list,
            op_type=instr.op_type,
            dest_physical=instr.rd_physical,
            active_list_idx=instr.active_list_idx,
        )
