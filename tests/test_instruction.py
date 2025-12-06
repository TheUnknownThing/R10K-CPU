from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import re

from assassyn.frontend import *
from assassyn.backend import elaborate
from assassyn.utils import run_simulator
from tests.utils import run_quietly

from r10k_cpu.instruction import select_instruction_args, RV32I_ALU_Code, OperantFrom, MemoryOpType

@dataclass
class InstructionTestCase:
    name: str
    instruction: int
    expected: dict

TEST_CASES = [
    InstructionTestCase(
        "ADD",
        0x003100B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SUB",
        0x403100B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 1, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "XOR",
        0x003140B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 5, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "OR",
        0x003160B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 8, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "AND",
        0x003170B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 9, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SLL",
        0x003110B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 2, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SRL",
        0x003150B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 7, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SRA",
        0x403150B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 6, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SLT",
        0x003120B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 3, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SLTU",
        0x003130B3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 1, 'imm': 0, 'alu_op': 4, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "ADDI",
        0x02A10093,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "XORI",
        0x02A14093,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 5, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "ORI",
        0x02A16093,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 8, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "ANDI",
        0x02A17093,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 9, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SLLI",
        0x00511093,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 5, 'alu_op': 2, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SRLI",
        0x00515093,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 5, 'alu_op': 7, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SRAI",
        0x40515093,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 1029, 'alu_op': 6, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SLTI",
        0x02A12093,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 3, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "SLTIU",
        0x02A13093,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 4, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "LB",
        0x02A10083,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 1, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 0}
    ),
    InstructionTestCase(
        "LH",
        0x02A11083,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 1, 'is_store': 0, 'mem_op': 1, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 0}
    ),
    InstructionTestCase(
        "LW",
        0x02A12083,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 1, 'is_store': 0, 'mem_op': 2, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 0}
    ),
    InstructionTestCase(
        "LBU",
        0x02A14083,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 1, 'is_store': 0, 'mem_op': 3, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 0}
    ),
    InstructionTestCase(
        "LHU",
        0x02A15083,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 1, 'is_store': 0, 'mem_op': 4, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 0}
    ),
    InstructionTestCase(
        "SB",
        0x02310523,
        {'has_rd': 0, 'has_rs1': 1, 'has_rs2': 1, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 1, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 0}
    ),
    InstructionTestCase(
        "SH",
        0x02311523,
        {'has_rd': 0, 'has_rs1': 1, 'has_rs2': 1, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 1, 'mem_op': 1, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 0}
    ),
    InstructionTestCase(
        "SW",
        0x02312523,
        {'has_rd': 0, 'has_rs1': 1, 'has_rs2': 1, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 1, 'mem_op': 2, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 0}
    ),
    InstructionTestCase(
        "BNE",
        0x04311063,
        {'has_rd': 0, 'has_rs1': 1, 'has_rs2': 1, 'imm': 64, 'alu_op': 1, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 1, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "BLT",
        0x04314063,
        {'has_rd': 0, 'has_rs1': 1, 'has_rs2': 1, 'imm': 64, 'alu_op': 3, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 1, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "BLTU",
        0x04316063,
        {'has_rd': 0, 'has_rs1': 1, 'has_rs2': 1, 'imm': 64, 'alu_op': 4, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 1, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "BEQ",
        0x04310063,
        {'has_rd': 0, 'has_rs1': 1, 'has_rs2': 1, 'imm': 64, 'alu_op': 1, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 1, 'branch_flip': 1, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "BGE",
        0x04315063,
        {'has_rd': 0, 'has_rs1': 1, 'has_rs2': 1, 'imm': 64, 'alu_op': 3, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 1, 'branch_flip': 1, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "BGEU",
        0x04317063,
        {'has_rd': 0, 'has_rs1': 1, 'has_rs2': 1, 'imm': 64, 'alu_op': 4, 'operant1_from': 0, 'operant2_from': 1, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 1, 'branch_flip': 1, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "JAL",
        0x000100EF,
        {'has_rd': 1, 'has_rs1': 0, 'has_rs2': 0, 'imm': 65536, 'alu_op': 0, 'operant1_from': 3, 'operant2_from': 4, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 1, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "JALR",
        0x02A100E7,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 0, 'operant1_from': 3, 'operant2_from': 4, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 1, 'is_jalr': 1, 'is_alu': 1}
    ),
    InstructionTestCase(
        "LUI",
        0x123450B7,
        {'has_rd': 1, 'has_rs1': 0, 'has_rs2': 0, 'imm': 305418240, 'alu_op': 8, 'operant1_from': 2, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "AUIPC",
        0x12345097,
        {'has_rd': 1, 'has_rs1': 0, 'has_rs2': 0, 'imm': 305418240, 'alu_op': 0, 'operant1_from': 3, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 0, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
    InstructionTestCase(
        "EBREAK",
        0x02A100F3,
        {'has_rd': 1, 'has_rs1': 1, 'has_rs2': 0, 'imm': 42, 'alu_op': 0, 'operant1_from': 0, 'operant2_from': 2, 'is_load': 0, 'is_store': 0, 'mem_op': 0, 'is_branch': 0, 'branch_flip': 0, 'is_terminator': 1, 'is_jump': 0, 'is_jalr': 0, 'is_alu': 1}
    ),
]

class Driver(Module):
    cycle: Array
    
    def __init__(self):
        super().__init__(ports={})
        self.cycle = RegArray(UInt(32), 1, initializer=[0])

    @module.combinational
    def build(self):
        self.cycle[0] = self.cycle[0] + UInt(32)(1)
        cycle_val = self.cycle[0]
        
        instr_val = Bits(32)(0)
        
        for i, test in enumerate(TEST_CASES):
            cond = cycle_val == UInt(32)(i + 1)
            instr_val = cond.select(Bits(32)(test.instruction), instr_val)
            
        args = select_instruction_args(instr_val)
        
        log_str = "cycle: {}, instr: {:x}, "
        log_args = [cycle_val, instr_val]
        
        fields = [
            "has_rd", "has_rs1", "has_rs2", "imm", 
            "alu_op", "operant1_from", "operant2_from",
            "is_load", "is_store", "mem_op",
            "is_branch", "branch_flip", "is_terminator",
            "is_jump", "is_jalr", "is_alu"
        ]
        
        for field in fields:
            log_str += f"{field}: {{}}, "
            log_args.append(getattr(args, field))
            
        log(log_str, *log_args)

def check(raw: str):
    lines = raw.strip().split("\n")
    history = {}
    
    for line in lines:
        m = re.search(r"cycle: (\d+), instr: ([0-9a-f]+), (.*)", line)
        if m:
            cycle = int(m.group(1))
            instr = int(m.group(2), 16)
            rest = m.group(3)
            
            data = {"cycle": cycle, "instr": instr}
            
            # Parse fields
            # has_rd: 1, has_rs1: 1, ...
            field_pairs = rest.split(", ")
            for pair in field_pairs:
                if not pair.strip(): continue
                parts = pair.split(": ")
                if len(parts) == 2:
                    k, v = parts
                    v = v.strip().rstrip(",")
                    data[k] = int(v)
            
            history[cycle] = data

    for i, test in enumerate(TEST_CASES):
        cycle = i + 1
        log_entry = history.get(cycle)
        assert log_entry, f"Missing log for cycle {cycle}"
        assert log_entry["instr"] == test.instruction, f"Instruction mismatch at cycle {cycle}"
        
        print(f"Checking {test.name}...")
        for k, v in test.expected.items():
            got = log_entry.get(k)
            assert got == v, f"{test.name}: Expected {k}={v}, got {got}"

def test_instruction_decode():
    sys = SysBuilder("test_instruction")
    with sys:
        driver = Driver()
        driver.build()
        
    sim, _ = elaborate(sys, verilog=True, verbose=False, sim_threshold=len(TEST_CASES) + 2)
    raw, _, _ = run_quietly(run_simulator, sim)
    check(raw)
