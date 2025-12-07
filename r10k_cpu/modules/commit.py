from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue

class Commit(Module):
    """Commits instructions from the Active List."""

    def __init__(self):
        super().__init__(ports={})
        self.name = "Commit"

    @module.combinational
    def build(self, active_list_queue: CircularQueue, register_ready: Array):
        """Graduate instructions, free physical registers, and surface map-table updates."""

        front_entry = active_list_queue.front()
        retire_with_dest = front_entry.ready & front_entry.has_dest
        with Condition(retire_with_dest):
            register_ready[front_entry.dest_old_physical] = Bits(1)(0)

        mispredict = front_entry.is_branch & (front_entry.predict_branch != front_entry.actual_branch)
        flush_recover = front_entry.ready & mispredict

        commit_write_enable = retire_with_dest
        commit_logical = retire_with_dest.select(front_entry.dest_logical, Bits(5)(0))
        commit_physical = retire_with_dest.select(front_entry.dest_new_physical, Bits(6)(0))

        # front_entry ready indicates whether to pop instruction
        return (
            front_entry.ready,
            front_entry.ready & front_entry.is_alu,
            front_entry.ready & ~front_entry.is_alu,
            retire_with_dest.select(front_entry.dest_old_physical, Bits(6)(0)),
            commit_write_enable,
            commit_logical,
            commit_physical,
            flush_recover,
        )