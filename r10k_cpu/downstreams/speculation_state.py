from dataclasses import dataclass
from assassyn.frontend import *
from r10k_cpu.utils import Bool


@dataclass
class SpeculationState(Downstream):
    speculating: Array

    def __init__(self):
        super().__init__()
        self.speculating = RegArray(Bool, 1)
        self.inst_address = RegArray(Bits(32), 1)
        self.offset = RegArray(Bits(32), 1)

    @downstream.combinational
    def build(
        self,
        into_speculating: Value,
        out_speculating: Value,
    ):
        into_speculating = into_speculating.optional(Bool(0))
        out_speculating = out_speculating.optional(Bool(0))

        new_speculating = (self.speculating[0] | into_speculating) & ~out_speculating
        self.speculating[0] = new_speculating
