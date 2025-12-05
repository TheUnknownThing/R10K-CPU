from assassyn.frontend import *

class Driver(Module):
    """Issues fetch requests for every word in the program image."""

    def __init__(self):
        super().__init__(ports={})
        self.name = "Driver"

    @module.combinational
    def build(self, commit: Module):
        # fetcher.async_called()
        commit.async_called()