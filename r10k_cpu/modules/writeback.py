from assassyn.frontend import *
from r10k_cpu.downstreams.active_list import ActiveList

class WriteBack(Module):
    """Handles the write-back stage of the LSU."""

    def __init__(self):
        super().__init__(ports={
            "is_load": Bits(1),
            "is_store": Bits(1),
            "op_type": Bits(3),
            "dest_physical": Bits(6),
            "active_list_idx": Bits(6),
        })
        self.name = "WriteBack"
    
    @module.combinational
    def build(self, active_list: ActiveList, register_ready: Array, physical_register_file: Array, memory: SRAM):
        (
            is_load, 
            is_store, 
            op_type, 
            dest_physical, 
            active_list_idx
        ) = self.pop_all_ports(False)

        with Condition(is_load):
            memory_out = memory.dout[0]
            physical_register_file[dest_physical] = self.process_memory_data(op_type, memory_out)
            register_ready[dest_physical] = Bits(1)(1)
            active_list.set_ready(index=active_list_idx)
        
        with Condition(is_store):
            pass

    @staticmethod
    def process_memory_data(op_type: Value, data: Value) -> Value:
        """Process data read from memory based on operation type."""
        if op_type == Bits(3)(0):  # Byte
            return data[0:8].sext(Bits(32))
        elif op_type == Bits(3)(1):  # Half-word
            return data[0:16].sext(Bits(32))
        elif op_type == Bits(3)(2):  # Word
            return data
        elif op_type == Bits(3)(3):  # Byte Unsigned
            return data[0:8].zext(Bits(32))
        elif op_type == Bits(3)(4):  # Half-word Unsigned
            return data[0:16].zext(Bits(32))
        else:
            return data  # Default case
