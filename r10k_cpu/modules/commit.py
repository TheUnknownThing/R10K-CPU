from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue
from r10k_cpu.common import ROBEntryType
from r10k_cpu.downstreams.fetcher_impl import FetcherFlushEntry
from r10k_cpu.downstreams.map_table import MapTable


class Commit(Module):
    """Commits instructions from the Active List."""

    def __init__(self):
        super().__init__(ports={})
        self.name = "Commit"

    @module.combinational
    def build(
        self,
        active_list_queue: CircularQueue,
        map_table: MapTable,
        register_file: Array,
    ):
        """Graduate instructions, free physical registers, and surface map-table updates."""

        front_entry = ROBEntryType.view(active_list_queue.front())
        retire_with_dest = front_entry.ready & front_entry.has_dest

        is_branch = front_entry.is_branch
        mispredict = is_branch & (
            front_entry.predict_branch != front_entry.actual_branch
        )
        flush_recover = front_entry.ready & mispredict

        commit_write_enable = retire_with_dest
        commit_logical = retire_with_dest.select(front_entry.dest_logical, Bits(5)(0))
        commit_physical = retire_with_dest.select(
            front_entry.dest_new_physical, Bits(6)(0)
        )

        flush_fetcher = front_entry.ready & (mispredict | front_entry.is_jump)
        flush_PC = front_entry.is_jalr.select(Bits(32)(0), front_entry.pc)
        flush_offset = front_entry.is_jalr.select(
            front_entry.imm,
            (mispredict & ~front_entry.actual_branch).select(
                Bits(32)(4), front_entry.imm
            ),
        )
        fetcher_flush_entry = FetcherFlushEntry(
            enable=flush_fetcher,
            PC=flush_PC,
            offset=flush_offset,
        )

        out_branch = front_entry.ready & is_branch

        need_push_freelist = front_entry.ready & front_entry.has_dest
        need_pop_activelist = front_entry.ready

        with Condition(need_pop_activelist & ~flush_recover):
            log_parts = ["PC=0x{:08X}"]
            for i in range(32):
                log_parts.append(f"x{i}=0x{{:08X}}")
            log_format = " ".join(log_parts)
            new_regs = [
                register_file[
                    (commit_write_enable & (commit_logical == Bits(5)(i))).select(
                        commit_physical, map_table.read_commit(Bits(5)(i))
                    )
                ]
                for i in range(32)
            ]
            log(log_format, front_entry.pc, *new_regs)

        return (
            need_push_freelist,
            need_pop_activelist,
            front_entry.ready & front_entry.is_alu, # ALU pop enable
            front_entry.ready & ~front_entry.is_alu, # LSQ pop enable
            retire_with_dest.select(front_entry.dest_old_physical, Bits(6)(0)),
            commit_write_enable,
            commit_logical,
            commit_physical,
            flush_recover,
            fetcher_flush_entry,
            out_branch,
        )
