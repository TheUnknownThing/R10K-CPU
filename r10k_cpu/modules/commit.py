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
        with Condition(front_entry.ready):
            register_ready[front_entry.dest_old_physical] = Bits(1)(0)

        mispredict = front_entry.is_branch & (front_entry.predict_branch != front_entry.actual_branch)
        flush_recover = front_entry.ready & mispredict

        commit_write_enable = front_entry.ready
        commit_logical = front_entry.dest_logical
        commit_physical = front_entry.dest_new_physical

        # front_entry ready indicates whether to pop instruction
        return (
            front_entry.ready,
            front_entry.ready & front_entry.is_alu,
            front_entry.ready & ~front_entry.is_alu,
            front_entry.dest_old_physical,
            commit_write_enable,
            commit_logical,
            commit_physical,
            flush_recover,
        )