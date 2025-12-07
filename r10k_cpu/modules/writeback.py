from assassyn.frontend import *
from r10k_cpu.downstreams.active_list import ActiveList

class WriteBack(Module):
    """Handles the write-back stage of the LSU."""

    def __init__(self):
        super().__init__(ports={
            "is_load": Bits(1),
            "is_store": Bits(1),
            "need_update_active_list": Bits(1),
            "op_type": Bits(3),
            "dest_physical": Bits(6),
            "active_list_idx": Bits(5),
            "addr": Bits(32),
        })
        self.name = "WriteBack"
    
    @module.combinational
    def build(self, active_list: ActiveList, register_ready: Array, physical_register_file: Array, memory: SRAM):
        (
            is_load, 
            is_store, 
            need_update_active_list,
            op_type, 
            dest_physical, 
            active_list_idx,
            addr,
        ) = self.pop_all_ports(False)

        with Condition(is_load):
            memory_out = memory.dout[0]
            physical_register_file[dest_physical] = self.process_memory_data(op_type, memory_out, addr)
            register_ready[dest_physical] = Bits(1)(1)
        
        with Condition(need_update_active_list):
            active_list.set_ready(index=active_list_idx)
        
        # If we have already committed the store, we do not need to do anything here.

    @staticmethod
    def process_memory_data(op_type: Value, data: Value, address: Value) -> Value:
        """Process data read from memory based on operation type."""
        byte_offset = address[0:2].bitcast(UInt(2))
        shift_amt = (byte_offset << UInt(5)(3)).bitcast(Bits(5))
        data_shifted = (data.bitcast(UInt(32)) >> shift_amt).bitcast(Bits(32))

        byte_val = data_shifted[0:8]
        half_val = data_shifted[0:16]

        res = data
        res = (op_type == Bits(3)(2)).select(data, res)  # Word
        res = (op_type == Bits(3)(0)).select(byte_val.sext(Bits(32)), res)  # Byte
        res = (op_type == Bits(3)(1)).select(half_val.sext(Bits(32)), res)  # Half-word
        res = (op_type == Bits(3)(3)).select(byte_val.zext(Bits(32)), res)  # Byte Unsigned
        res = (op_type == Bits(3)(4)).select(half_val.zext(Bits(32)), res)  # Half-word Unsigned
        return res
