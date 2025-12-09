from math import ceil, log2
from r10k_cpu.common import (
    ALU_CODE_LEN,
    MEMORY_OP_TYPE_LEN,
    OPERANT_FROM_LEN,
    MemoryOpType,
    RV32I_ALU_Code,
)
from assassyn.frontend import Value, Bits

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from r10k_cpu.utils import Bool, sext


class OperantFrom(Enum):
    RS1 = 0
    RS2 = 1
    IMM = 2
    PC = 3
    LITERAL_FOUR = 4


OPERANT_FROM_LEN = ceil(log2(len(OperantFrom)))


@dataclass
class InstructionArgs:
    has_rd: Value
    has_rs1: Value
    has_rs2: Value
    imm: Value

    is_alu: Value
    alu_op: Value
    operant1_from: Value
    operant2_from: Value

    is_load: Value
    is_store: Value
    mem_op: Value

    is_branch: Value
    branch_flip: Value
    is_terminator: Value
    is_jump: Value
    is_jalr: Value


def default_instruction_arguments() -> InstructionArgs:
    return InstructionArgs(
        has_rd=Bool(0),
        has_rs1=Bool(0),
        has_rs2=Bool(0),
        imm=Bits(32)(0),
        is_alu=Bool(0),
        alu_op=Bits(ALU_CODE_LEN)(0),
        operant1_from=Bits(OPERANT_FROM_LEN)(0),
        operant2_from=Bits(OPERANT_FROM_LEN)(0),
        is_load=Bool(0),
        is_store=Bool(0),
        mem_op=Bits(MEMORY_OP_TYPE_LEN)(0),
        is_branch=Bool(0),
        branch_flip=Bool(0),
        is_terminator=Bool(0),
        is_jump=Bool(0),
        is_jalr=Bool(0),
    )


@dataclass
class ALUInfo:
    alu_op: RV32I_ALU_Code
    operant1_from: OperantFrom
    operant2_from: OperantFrom


@dataclass
class Instruction:
    opcode: int
    funct3: Optional[int]
    funct7: Optional[int]

    alu_info: ALUInfo

    has_rd: bool
    has_rs1: bool
    has_rs2: bool
    imm: Optional[Callable[[Value], Value]]

    is_jump: bool
    is_jalr: bool
    is_alu: bool = True

    def matches(self, instruction: Value) -> Value:
        op_match = instruction[0:6] == Bits(7)(self.opcode)
        funct3_match = (
            Bool(1)
            if self.funct3 is None
            else instruction[12:14] == Bits(3)(self.funct3)
        )
        funct7_match = (
            Bool(1)
            if self.funct7 is None
            else instruction[25:31] == Bits(7)(self.funct7)
        )
        return op_match & funct3_match & funct7_match

    def select_args(
        self, cond: Value, instruction: Value, args: InstructionArgs
    ) -> InstructionArgs:

        args.alu_op = cond.select(
            Bits(ALU_CODE_LEN)(self.alu_info.alu_op.value), args.alu_op
        )
        args.operant1_from = cond.select(
            Bits(OPERANT_FROM_LEN)(self.alu_info.operant1_from.value),
            args.operant1_from,
        )
        args.operant2_from = cond.select(
            Bits(OPERANT_FROM_LEN)(self.alu_info.operant2_from.value),
            args.operant2_from,
        )

        if self.has_rd:
            args.has_rd = cond.select(Bool(1), args.has_rd)
        if self.has_rs1:
            args.has_rs1 = cond.select(Bool(1), args.has_rs1)
        if self.has_rs2:
            args.has_rs2 = cond.select(Bool(1), args.has_rs2)
        if self.imm is not None:
            args.imm = cond.select(self.imm(instruction), args.imm)
        if self.is_jump:
            args.is_jump = cond.select(Bool(1), args.is_jump)
        if self.is_jalr:
            args.is_jalr = cond.select(Bool(1), args.is_jalr)
        if self.is_alu:
            args.is_alu = cond.select(Bool(1), args.is_alu)
        return args


class RTypeInstruction(Instruction):
    def __init__(self, opcode: int, alu_op: RV32I_ALU_Code, funct3: int, funct7: int):
        super().__init__(
            opcode=opcode,
            funct3=funct3,
            funct7=funct7,
            alu_info=ALUInfo(alu_op, OperantFrom.RS1, OperantFrom.RS2),
            has_rd=True,
            has_rs1=True,
            has_rs2=True,
            imm=None,
            is_jump=False,
            is_jalr=False,
        )


class ITypeInstruction(Instruction):
    is_load: bool
    mem_op: Optional[MemoryOpType]
    is_terminator: bool
    is_jalr: bool

    def __init__(
        self,
        opcode: int,
        alu_op: RV32I_ALU_Code,
        funct3: int,
        funct7: Optional[int] = None,
        is_load: bool = False,
        mem_op: Optional[MemoryOpType] = None,
        is_terminator: bool = False,
        operant1_from: OperantFrom = OperantFrom.RS1,
        operant2_from: OperantFrom = OperantFrom.IMM,
        is_jalr: bool = False,
    ):
        def imm_fn(instruction: Value) -> Value:
            return sext(instruction[20:31], Bits(32))

        super().__init__(
            opcode=opcode,
            funct3=funct3,
            funct7=funct7,
            alu_info=ALUInfo(alu_op, operant1_from, operant2_from),
            has_rd=True,
            has_rs1=True,
            has_rs2=False,
            imm=imm_fn,
            is_jump=is_jalr,
            is_jalr=is_jalr,
            is_alu=not is_load,
        )
        self.is_load = is_load
        self.mem_op = mem_op
        self.is_terminator = is_terminator
        self.is_jalr = is_jalr

    def select_args(
        self, cond: Value, instruction: Value, args: InstructionArgs
    ) -> InstructionArgs:
        args = super().select_args(cond, instruction, args)
        if self.is_load:
            args.is_load = cond.select(Bool(1), args.is_load)
        if self.mem_op is not None:
            args.mem_op = cond.select(
                Bits(MEMORY_OP_TYPE_LEN)(self.mem_op.value), args.mem_op
            )
        if self.is_terminator:
            args.is_terminator = cond.select(Bool(1), args.is_terminator)
        if self.is_jalr:
            args.is_jump = cond.select(Bool(1), args.is_jump)
            args.is_jalr = cond.select(Bool(1), args.is_jalr)
        return args


class STypeInstruction(Instruction):
    mem_op: MemoryOpType

    def __init__(
        self,
        opcode: int,
        alu_op: RV32I_ALU_Code,
        funct3: int,
        mem_op: MemoryOpType,
    ):
        def imm_fn(instruction: Value) -> Value:
            imm_4_0 = instruction[7:11]
            imm_11_5 = instruction[25:31]
            return sext(imm_11_5.concat(imm_4_0), Bits(32))

        super().__init__(
            opcode=opcode,
            funct3=funct3,
            funct7=None,
            alu_info=ALUInfo(alu_op, OperantFrom.RS1, OperantFrom.IMM),
            has_rd=False,
            has_rs1=True,
            has_rs2=True,
            imm=imm_fn,
            is_jump=False,
            is_jalr=False,
            is_alu=False,
        )
        self.mem_op = mem_op

    def select_args(
        self, cond: Value, instruction: Value, args: InstructionArgs
    ) -> InstructionArgs:
        args = super().select_args(cond, instruction, args)
        args.is_store = cond.select(Bool(1), args.is_store)
        args.mem_op = cond.select(
            Bits(MEMORY_OP_TYPE_LEN)(self.mem_op.value), args.mem_op
        )
        return args


class BTypeInstruction(Instruction):
    OPCODE = 0b1100011

    branch_flip: bool

    @staticmethod
    def imm_fn(instruction: Value) -> Value:
        imm_11 = instruction[7:7]
        imm_4_1 = instruction[8:11]
        imm_10_5 = instruction[25:30]
        imm_12 = instruction[31:31]
        return sext(
            imm_12.concat(imm_11).concat(imm_10_5).concat(imm_4_1).concat(Bits(1)(0)),
            Bits(32),
        )

    def __init__(self, alu_op: RV32I_ALU_Code, funct3: int, branch_flip: bool = False):

        super().__init__(
            opcode=self.OPCODE,
            funct3=funct3,
            funct7=None,
            alu_info=ALUInfo(alu_op, OperantFrom.RS1, OperantFrom.RS2),
            has_rd=False,
            has_rs1=True,
            has_rs2=True,
            imm=self.imm_fn,
            is_jump=False,
            is_jalr=False,
        )
        self.branch_flip = branch_flip

    def select_args(
        self, cond: Value, instruction: Value, args: InstructionArgs
    ) -> InstructionArgs:
        args = super().select_args(cond, instruction, args)
        if self.branch_flip:
            args.branch_flip = cond.select(Bool(1), args.branch_flip)
        args.is_branch = cond.select(Bool(1), args.is_branch)
        return args


class UTypeInstruction(Instruction):
    def __init__(
        self,
        opcode: int,
        alu_op: RV32I_ALU_Code,
        operant1_from: OperantFrom,
        operant2_from: OperantFrom,
    ):
        def imm_fn(instruction: Value) -> Value:
            return instruction[12:31].concat(Bits(12)(0))

        super().__init__(
            opcode=opcode,
            funct3=None,
            funct7=None,
            alu_info=ALUInfo(alu_op, operant1_from, operant2_from),
            has_rd=True,
            has_rs1=False,
            has_rs2=False,
            imm=imm_fn,
            is_jump=False,
            is_jalr=False,
        )


class JTypeInstruction(Instruction):
    def __init__(self, opcode: int, alu_op: RV32I_ALU_Code):
        def imm_fn(instruction: Value) -> Value:
            imm_19_12 = instruction[12:19]
            imm_11 = instruction[20:20]
            imm_10_1 = instruction[21:30]
            imm_20 = instruction[31:31]
            return sext(
                imm_20.concat(imm_19_12)
                .concat(imm_11)
                .concat(imm_10_1)
                .concat(Bits(1)(0)),
                Bits(32),
            )

        super().__init__(
            opcode=opcode,
            funct3=None,
            funct7=None,
            alu_info=ALUInfo(alu_op, OperantFrom.PC, OperantFrom.LITERAL_FOUR),
            has_rd=True,
            has_rs1=False,
            has_rs2=False,
            imm=imm_fn,
            is_jump=True,
            is_jalr=False,
        )


class Instructions(Enum):
    ADD = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.ADD, funct3=0x0, funct7=0x00
    )
    SUB = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.SUB, funct3=0x0, funct7=0x20
    )
    XOR = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.XOR, funct3=0x4, funct7=0x00
    )
    OR = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.OR, funct3=0x6, funct7=0x00
    )
    AND = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.AND, funct3=0x7, funct7=0x00
    )
    SLL = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.SLL, funct3=0x1, funct7=0x00
    )
    SRL = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.SRL, funct3=0x5, funct7=0x00
    )
    SRA = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.SRA, funct3=0x5, funct7=0x20
    )
    SLT = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.SLT, funct3=0x2, funct7=0x00
    )
    SLTU = RTypeInstruction(
        opcode=0b0110011, alu_op=RV32I_ALU_Code.SLTU, funct3=0x3, funct7=0x00
    )

    ADDI = ITypeInstruction(opcode=0b0010011, alu_op=RV32I_ALU_Code.ADD, funct3=0x0)
    XORI = ITypeInstruction(opcode=0b0010011, alu_op=RV32I_ALU_Code.XOR, funct3=0x4)
    ORI = ITypeInstruction(opcode=0b0010011, alu_op=RV32I_ALU_Code.OR, funct3=0x6)
    ANDI = ITypeInstruction(opcode=0b0010011, alu_op=RV32I_ALU_Code.AND, funct3=0x7)
    SLLI = ITypeInstruction(
        opcode=0b0010011, alu_op=RV32I_ALU_Code.SLL, funct3=0x1, funct7=0x00
    )
    SRLI = ITypeInstruction(
        opcode=0b0010011, alu_op=RV32I_ALU_Code.SRL, funct3=0x5, funct7=0x00
    )
    SRAI = ITypeInstruction(
        opcode=0b0010011, alu_op=RV32I_ALU_Code.SRA, funct3=0x5, funct7=0x20
    )
    SLTI = ITypeInstruction(opcode=0b0010011, alu_op=RV32I_ALU_Code.SLT, funct3=0x2)
    SLTIU = ITypeInstruction(opcode=0b0010011, alu_op=RV32I_ALU_Code.SLTU, funct3=0x3)

    LB = ITypeInstruction(
        opcode=0b0000011,
        alu_op=RV32I_ALU_Code.ADD,
        funct3=0x0,
        is_load=True,
        mem_op=MemoryOpType.BYTE,
    )
    LH = ITypeInstruction(
        opcode=0b0000011,
        alu_op=RV32I_ALU_Code.ADD,
        funct3=0x1,
        is_load=True,
        mem_op=MemoryOpType.HALF,
    )
    LW = ITypeInstruction(
        opcode=0b0000011,
        alu_op=RV32I_ALU_Code.ADD,
        funct3=0x2,
        is_load=True,
        mem_op=MemoryOpType.WORD,
    )
    LBU = ITypeInstruction(
        opcode=0b0000011,
        alu_op=RV32I_ALU_Code.ADD,
        funct3=0x4,
        is_load=True,
        mem_op=MemoryOpType.BYTE_U,
    )
    LHU = ITypeInstruction(
        opcode=0b0000011,
        alu_op=RV32I_ALU_Code.ADD,
        funct3=0x5,
        is_load=True,
        mem_op=MemoryOpType.HALF_U,
    )

    SB = STypeInstruction(
        opcode=0b0100011,
        alu_op=RV32I_ALU_Code.ADD,
        funct3=0x0,
        mem_op=MemoryOpType.BYTE,
    )
    SH = STypeInstruction(
        opcode=0b0100011,
        alu_op=RV32I_ALU_Code.ADD,
        funct3=0x1,
        mem_op=MemoryOpType.HALF,
    )
    SW = STypeInstruction(
        opcode=0b0100011,
        alu_op=RV32I_ALU_Code.ADD,
        funct3=0x2,
        mem_op=MemoryOpType.WORD,
    )

    # alu 结果非零跳转，全零不跳转
    BNE = BTypeInstruction(alu_op=RV32I_ALU_Code.SUB, funct3=0x1)
    BLT = BTypeInstruction(alu_op=RV32I_ALU_Code.SLT, funct3=0x4)
    BLTU = BTypeInstruction(alu_op=RV32I_ALU_Code.SLTU, funct3=0x6)

    # alu 结果全零跳转，非零不跳转
    BEQ = BTypeInstruction(alu_op=RV32I_ALU_Code.SUB, funct3=0x0, branch_flip=True)
    BGE = BTypeInstruction(alu_op=RV32I_ALU_Code.SLT, funct3=0x5, branch_flip=True)
    BGEU = BTypeInstruction(alu_op=RV32I_ALU_Code.SLTU, funct3=0x7, branch_flip=True)

    JAL = JTypeInstruction(opcode=0b1101111, alu_op=RV32I_ALU_Code.ADD)
    JALR = ITypeInstruction(
        opcode=0b1100111,
        funct3=0x0,
        alu_op=RV32I_ALU_Code.ADD,
        operant1_from=OperantFrom.RS1,
        operant2_from=OperantFrom.IMM,
        is_jalr=True,
    )

    LUI = UTypeInstruction(
        opcode=0b0110111,
        alu_op=RV32I_ALU_Code.OR,
        operant1_from=OperantFrom.IMM,
        operant2_from=OperantFrom.IMM,
    )
    AUIPC = UTypeInstruction(
        opcode=0b0010111,
        alu_op=RV32I_ALU_Code.ADD,
        operant1_from=OperantFrom.PC,
        operant2_from=OperantFrom.IMM,
    )

    EBREAK = ITypeInstruction(
        opcode=0b1110011, funct3=0x0, alu_op=RV32I_ALU_Code.ADD, is_terminator=True
    )


def select_instruction_args(instruction: Value) -> InstructionArgs:
    args = default_instruction_arguments()
    for instr in Instructions:
        instr_obj: Instruction = instr.value
        cond = instr_obj.matches(instruction)
        args = instr_obj.select_args(cond, instruction, args)
    return args
