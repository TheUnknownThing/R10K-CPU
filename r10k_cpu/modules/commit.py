from assassyn.frontend import *
from dataclass.circular_queue import CircularQueue

class Commit(Module):
    """Commits instructions from the Active List."""

    def __init__(self):
        super().__init__(ports={})
        self.name = "Commit"

    @module.combinational
    def build(self, active_list_queue: CircularQueue, map_table_active: Array, map_table_0: Array, map_table_1: Array):
        """Graduate instructions from the Active List, free physical registers, and recover branch mispredictions."""

        front_entry = active_list_queue.front()
        with Condition(front_entry.ready):
            with Condition(map_table_active[0]):
                map_table_0[front_entry.dest_logical] = front_entry.dest_new_physical
            with Condition(~map_table_active[0]):
                map_table_1[front_entry.dest_logical] = front_entry.dest_new_physical
            
            with Condition(front_entry.is_branch & (front_entry.predict_branch != front_entry.actual_branch)):
                map_table_active[0] = ~map_table_active[0]
                # TODO: add other recovery steps

        # front_entry ready indicates whether to pop instruction
        return front_entry.ready, front_entry.dest_old_physical, front_entry.is_alu