from dataclasses import dataclass
from assassyn.frontend import *
from r10k_cpu.common import FetcherFlushEntry, FetcherImplEntry
from r10k_cpu.modules.decoder import Decoder
from r10k_cpu.utils import Bool


class FetcherImpl(Downstream):
    stalled: Array

    def __init__(self):
        super().__init__()
        self.stalled = RegArray(Bool, size=1)

    @downstream.combinational
    def build(
        self,
        PC_reg: Array,
        PC_addr: Value,
        decoder: Decoder,
        icache: SRAM,
        flush_entry: FetcherFlushEntry,
        predict_branch: Value,
        entry: FetcherImplEntry,
    ):
        decode_success = entry.decode_success.optional(Bool(0))
        flush_enable = flush_entry.enable.optional(Bool(0))
        flush_PC = flush_entry.PC.optional(Bits(32)(0))
        flush_offset = flush_entry.offset.optional(Bits(32)(0))
        is_branch = entry.is_branch.optional(Bool(0))
        predict_branch = predict_branch.optional(Bool(0))
        branch_offset = entry.branch_offset.optional(Bits(32)(4))
        stall = entry.stall.optional(Bool(0))

        new_stalled = (self.stalled[0] | stall) & ~flush_enable

        offset = (is_branch & predict_branch).select(branch_offset, Bits(32)(4))

        new_PC = flush_enable.select(
            (flush_PC.bitcast(UInt(32)) + flush_offset.bitcast(UInt(32))).bitcast(Bits(32)),
            (PC_addr.bitcast(UInt(32)) + offset.bitcast(UInt(32))).bitcast(Bits(32)),
        )

        new_PC = (flush_enable | (~new_stalled & decode_success)).select(
            new_PC, PC_addr
        )

        PC_reg[0] = new_PC

        self.stalled[0] = new_stalled

        icache.build(
            we=Bool(0), re=Bool(1), addr=new_PC[2:31].zext(Bits(32))[0:19], wdata=Bits(32)(0)
        )

        with Condition(~new_stalled):
            log("New PC: 0x{:08X}", new_PC)
            decoder_call = decoder.async_called(PC=new_PC)
            decoder_call.bind.set_fifo_depth(PC=1)
