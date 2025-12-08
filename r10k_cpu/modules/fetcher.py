from assassyn.frontend import *


class Fetcher(Module):
    PC: Array

    def __init__(self):
        super().__init__(ports={})
        self.PC = RegArray(Bits(32), 1)

    @module.combinational
    def build(self):
        return self.PC, self.PC[0]