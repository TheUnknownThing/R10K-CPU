from assassyn.frontend import *
from assassyn.ir.dtype import RecordValue
from r10k_cpu.common import (
    ALUQueueEntryType,
    ALU_CODE_LEN,
    OPERANT_FROM_LEN,
    ALU_Code,
    OperantFrom,
)
from r10k_cpu.downstreams.active_list import ActiveList
from r10k_cpu.downstreams.register_ready import RegisterReady


ALU_OP_COUNT = len(ALU_Code)

class ALU(Module):
    """
    Performs arithmetic and logic operations.
    It needs to modify active list (to notify the branch outcome),
    write results to the physical register file,
    and update register_ready accordingly.
    """

    def __init__(self):
        super().__init__(ports={"instr": Port(ALUQueueEntryType)})
        self.name = "ALU"

    @module.combinational
    def build(self, physical_register_file: Array, register_ready: RegisterReady, active_list: ActiveList):
        instr: RecordValue = ALUQueueEntryType.view(self.pop_all_ports(False))

        op_a = self._select_operand(instr, instr.operant1_from, physical_register_file)
        op_b = self._select_operand(instr, instr.operant2_from, physical_register_file)

        op_select = self._decode_one_hot(instr.alu_op)

        op_a_int = op_a.bitcast(Int(32))
        op_b_int = op_b.bitcast(Int(32))
        shamt = op_b[0:4]
        shamt_u = shamt.bitcast(UInt(5))

        results= [Bits(32)(0) for _ in range(ALU_OP_COUNT)]

        results[ALU_Code.ADD.value] = (op_a_int + op_b_int).bitcast(Bits(32))
        results[ALU_Code.SUB.value] = (op_a_int - op_b_int).bitcast(Bits(32))
        results[ALU_Code.SLL.value] = op_a << shamt_u
        results[ALU_Code.SRL.value] = op_a >> shamt_u
        results[ALU_Code.SRA.value] = (op_a_int >> shamt_u).bitcast(Bits(32))
        results[ALU_Code.AND.value] = op_a & op_b
        results[ALU_Code.OR.value] = op_a | op_b
        results[ALU_Code.XOR.value] = op_a ^ op_b
        results[ALU_Code.SLT.value] = (op_a_int < op_b_int).select(
            Bits(32)(1), Bits(32)(0)
        )
        results[ALU_Code.SLTU.value] = (op_a < op_b).select(
            Bits(32)(1), Bits(32)(0)
        )

        result_value = op_select.select1hot(*results)
        pc_plus_four = (instr.PC.bitcast(Int(32)) + Int(32)(4)).bitcast(Bits(32))
        jalr_target = (
            physical_register_file[instr.rs1_physical].bitcast(Int(32))
            + instr.imm.bitcast(Int(32))
        ).bitcast(Bits(32))
        rd_value = instr.is_jalr.select(pc_plus_four, result_value)

        rd_zero = Bits(6)(0)
        rd_has_dest = instr.rd_physical != rd_zero
        write_valid = instr.valid & rd_has_dest

        with Condition(write_valid):
            physical_register_file[instr.rd_physical] = rd_value
            register_ready.mark_ready(instr.rd_physical, enable=write_valid)

        non_zero = result_value != Bits(32)(0)
        branch_core = instr.branch_flip.select(~non_zero, non_zero)
        branch_valid = instr.valid & instr.is_branch
        branch_taken = branch_valid & branch_core

        with Condition(instr.valid):
            # We always pass actual_branch here, but it only matters when is_branch is true
            active_list_index = instr.active_list_idx
            active_list.set_ready(
                index=active_list_index,
                actual_branch=branch_taken,
                new_imm=jalr_target,
                new_imm_enable=instr.is_jalr,
            )


    @staticmethod
    def _decode_one_hot(alu_op: Value) -> Value:
        op_select = Bits(ALU_OP_COUNT)(0)

        def mask(idx: int) -> Value:
            return Bits(ALU_OP_COUNT)(1 << idx)

        for opcode in ALU_Code:
            cond = alu_op == Bits(ALU_CODE_LEN)(opcode.value)
            op_select = cond.select(mask(opcode.value), op_select)
        return op_select

    @staticmethod
    def _select_operand(
        instr: RecordValue, selector: Value, physical_register_file: Array
    ) -> Value:
        literal_four = Bits(32)(4)
        sources = {
            OperantFrom.RS1: physical_register_file[instr.rs1_physical],
            OperantFrom.RS2: physical_register_file[instr.rs2_physical],
            OperantFrom.IMM: instr.imm,
            OperantFrom.PC: instr.PC,
            OperantFrom.LITERAL_FOUR: literal_four,
        }

        value = Bits(32)(0)
        for source, data in sources.items():
            cond = selector == Bits(OPERANT_FROM_LEN)(source.value)
            value = cond.select(data, value)
        return value
