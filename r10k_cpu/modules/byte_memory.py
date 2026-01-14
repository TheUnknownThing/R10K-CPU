"""
Byte-addressable memory wrapper that supports sb, sh, and sw operations.

This module wraps 4 separate 8-bit SRAMs to form a 32-bit word-addressable
memory that supports byte, halfword, and word store operations.
"""

from assassyn.frontend import *
from r10k_cpu.common import MemoryOpType, MEMORY_OP_TYPE_LEN


class ByteAddressableMemory(Downstream):
    """
    A memory wrapper that uses 4 byte-wide SRAMs to support byte and halfword stores.
    
    The memory is organized as:
    - byte0: bits [7:0] of each word
    - byte1: bits [15:8] of each word
    - byte2: bits [23:16] of each word
    - byte3: bits [31:24] of each word
    
    For loads, all 4 bytes are always read and combined.
    For stores, byte write enables are computed based on op_type and byte offset.
    
    Note: The init_file should be the base path without extension. The class will
    look for _b0.hex, _b1.hex, _b2.hex, _b3.hex files for each byte lane, or
    use a preprocessing step to split the original hex file.
    """
    
    def __init__(self, depth: int, init_file: str | None = None):
        super().__init__()
        self.depth = depth
        self.init_file = init_file
        
        byte_files = [None, None, None, None]
        if init_file is not None:
            byte_files = self._prepare_byte_files(init_file)
        
        # Create 4 byte-wide SRAMs
        self.byte0 = SRAM(width=8, depth=depth, init_file=byte_files[0])
        self.byte1 = SRAM(width=8, depth=depth, init_file=byte_files[1])
        self.byte2 = SRAM(width=8, depth=depth, init_file=byte_files[2])
        self.byte3 = SRAM(width=8, depth=depth, init_file=byte_files[3])
        
        self.byte0.name = "byte_mem_0"
        self.byte1.name = "byte_mem_1"
        self.byte2.name = "byte_mem_2"
        self.byte3.name = "byte_mem_3"
    
    def _prepare_byte_files(self, init_file: str) -> list:
        """
        Split a 32-bit hex file into 4 byte hex files.
        
        Given init_file = "file.hex", creates:
        - file_b0.hex (bits 7:0)
        - file_b1.hex (bits 15:8)
        - file_b2.hex (bits 23:16)
        - file_b3.hex (bits 31:24)
        """
        import os
        
        base, ext = os.path.splitext(init_file)
        byte_files = [f"{base}_b{i}{ext}" for i in range(4)]
        
        # Check if we need to regenerate
        if os.path.exists(init_file):
            try:
                with open(init_file, 'r') as f:
                    lines = f.readlines()
                
                byte_data = [[], [], [], []]
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    # Parse 32-bit hex value
                    word = int(line, 16)
                    byte_data[0].append(f"{(word >> 0) & 0xFF:02x}")
                    byte_data[1].append(f"{(word >> 8) & 0xFF:02x}")
                    byte_data[2].append(f"{(word >> 16) & 0xFF:02x}")
                    byte_data[3].append(f"{(word >> 24) & 0xFF:02x}")
                
                for i in range(4):
                    with open(byte_files[i], 'w') as f:
                        f.write('\n'.join(byte_data[i]))
                        if byte_data[i]:
                            f.write('\n')
            except Exception as e:
                return [None, None, None, None]
        
        return byte_files
    
    @downstream.combinational
    def build(
        self,
        we: Value,
        re: Value,
        word_addr: Value,
        wdata: Value,
        op_type: Value,  # Memory operation type (BYTE, HALF, WORD)
        byte_offset: Value,  # Lower 2 bits of address for byte/halfword alignment
    ):
        """
        Build the byte-addressable memory.
        """
        is_byte_op = op_type == Bits(MEMORY_OP_TYPE_LEN)(MemoryOpType.BYTE.value)
        is_half_op = op_type == Bits(MEMORY_OP_TYPE_LEN)(MemoryOpType.HALF.value)
        is_word_op = op_type == Bits(MEMORY_OP_TYPE_LEN)(MemoryOpType.WORD.value)
        
        offset_0 = byte_offset == Bits(2)(0)
        offset_1 = byte_offset == Bits(2)(1)
        offset_2 = byte_offset == Bits(2)(2)
        offset_3 = byte_offset == Bits(2)(3)
        
        we0 = we & (is_word_op | (is_half_op & offset_0) | (is_byte_op & offset_0))
        we1 = we & (is_word_op | (is_half_op & offset_0) | (is_byte_op & offset_1))
        we2 = we & (is_word_op | (is_half_op & offset_2) | (is_byte_op & offset_2))
        we3 = we & (is_word_op | (is_half_op & offset_2) | (is_byte_op & offset_3))
        
        wdata_byte = wdata[0:7]  # Low byte of rs2
        wdata_half_lo = wdata[0:7]  # Low byte of halfword
        wdata_half_hi = wdata[8:15]  # High byte of halfword
        
        wdata_word_b0 = wdata[0:7]    # bits 0-7
        wdata_word_b1 = wdata[8:15]   # bits 8-15
        wdata_word_b2 = wdata[16:23]  # bits 16-23
        wdata_word_b3 = wdata[24:31]  # bits 24-31
        
        wdata0 = is_word_op.select(
            wdata_word_b0,
            is_half_op.select(
                offset_0.select(wdata_half_lo, Bits(8)(0)),
                offset_0.select(wdata_byte, Bits(8)(0))
            )
        )
        
        wdata1 = is_word_op.select(
            wdata_word_b1,
            is_half_op.select(
                offset_0.select(wdata_half_hi, Bits(8)(0)),
                offset_1.select(wdata_byte, Bits(8)(0))
            )
        )
        
        wdata2 = is_word_op.select(
            wdata_word_b2,
            is_half_op.select(
                offset_2.select(wdata_half_lo, Bits(8)(0)),
                offset_2.select(wdata_byte, Bits(8)(0))
            )
        )
        
        wdata3 = is_word_op.select(
            wdata_word_b3,
            is_half_op.select(
                offset_2.select(wdata_half_hi, Bits(8)(0)),
                offset_3.select(wdata_byte, Bits(8)(0))
            )
        )
        
        # Build each byte SRAM
        self.byte0.build(we=we0, re=re, addr=word_addr, wdata=wdata0)
        self.byte1.build(we=we1, re=re, addr=word_addr, wdata=wdata1)
        self.byte2.build(we=we2, re=re, addr=word_addr, wdata=wdata2)
        self.byte3.build(we=we3, re=re, addr=word_addr, wdata=wdata3)
    
    @property
    def dout(self):
        """
        Return a list that when indexed, concatenates the 4 byte SRAM outputs.
        This creates the concat expression in the caller's module context.
        """
        return _ByteMemoryDout(self.byte0, self.byte1, self.byte2, self.byte3)


class _ByteMemoryDout:
    """
    Helper class that creates the concat expression when indexed.
    This ensures the concat is created in the calling module's context.
    """
    def __init__(self, byte0, byte1, byte2, byte3):
        self.byte0 = byte0
        self.byte1 = byte1
        self.byte2 = byte2
        self.byte3 = byte3
    
    def __getitem__(self, idx):
        if idx != 0:
            raise IndexError("ByteAddressableMemory only has one output")
        # Create the concatenation in the caller's context
        b0 = self.byte0.dout[0]
        b1 = self.byte1.dout[0]
        b2 = self.byte2.dout[0]
        b3 = self.byte3.dout[0]
        # Concatenate: [b3(31:24), b2(23:16), b1(15:8), b0(7:0)]
        return b3.concat(b2).concat(b1).concat(b0)
