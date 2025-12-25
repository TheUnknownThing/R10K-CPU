from typing import Callable
from algorithms import wallace_tree
from algorithms.adder import combination_adder
from algorithms.multiply_partial_products import radix4_partial_products
from assassyn.frontend import *
from assassyn.ir.dtype import RecordValue
from r10k_cpu import utils
from r10k_cpu.common import (
    ALUQueueEntryType,
    ALU_CODE_LEN,
    OPERANT_FROM_LEN,
    ALU_Code,
    OperantFrom,
)
from r10k_cpu.downstreams.active_list import ActiveList
from r10k_cpu.downstreams.register_ready import RegisterReady
from r10k_cpu.utils import attach_context, leading_zero_count


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
    def build(
        self,
        physical_register_file: Array,
        register_ready: RegisterReady,
        active_list: ActiveList,
    ):
        instr: RecordValue = ALUQueueEntryType.view(self.pop_all_ports(False))

        op_a = self._select_operand(instr, instr.operant1_from, physical_register_file)
        op_b = self._select_operand(instr, instr.operant2_from, physical_register_file)

        op_select = self._decode_one_hot(instr.alu_op)

        op_a_int = op_a.bitcast(Int(32))
        op_b_int = op_b.bitcast(Int(32))
        shamt = op_b[0:4]
        shamt_u = shamt.bitcast(UInt(5))

        results = [Bits(32)(0) for _ in range(ALU_OP_COUNT)]

        results[ALU_Code.ADD.value] = combination_adder(op_a, op_b, 4)[0]
        results[ALU_Code.SUB.value] = combination_adder(op_a, ~op_b, 4, Bits(1)(1))[0]
        results[ALU_Code.SLL.value] = op_a << shamt_u
        results[ALU_Code.SRL.value] = op_a >> shamt_u
        results[ALU_Code.SRA.value] = (op_a_int >> shamt_u).bitcast(Bits(32))
        results[ALU_Code.AND.value] = op_a & op_b
        results[ALU_Code.OR.value] = op_a | op_b
        results[ALU_Code.XOR.value] = op_a ^ op_b
        results[ALU_Code.SLT.value] = (op_a_int < op_b_int).select(
            Bits(32)(1), Bits(32)(0)
        )
        results[ALU_Code.SLTU.value] = (op_a < op_b).select(Bits(32)(1), Bits(32)(0))

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


class Multiply_ALU(Module):
    div_busy: Array
    products: list[Array]

    instr: Port

    def __init__(self):
        super().__init__(ports={"instr": Port(ALUQueueEntryType)})
        self.name = "Multiply_ALU"
        self.div_busy = RegArray(Bits(1), 1)

    @module.combinational
    def build(
        self,
        physical_register_file: Array,
        register_ready: RegisterReady,
        active_list: ActiveList,
        flush: Array,
    ):
        instr: RecordValue = ALUQueueEntryType.view(self.pop_all_ports(False))

        op_a = physical_register_file[instr.rs1_physical]
        op_b = physical_register_file[instr.rs2_physical]

        is_op_a_signed = (instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.MULH.value)) | (
            instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.MULSU.value)
        )
        is_op_b_signed = instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.MULH.value)

        extended_op_a = is_op_a_signed.select(op_a[31:31], Bits(1)(0)).concat(op_a)
        extended_op_b = is_op_b_signed.select(op_b[31:31], Bits(1)(0)).concat(op_b)

        products = radix4_partial_products(extended_op_a, extended_op_b)
        product_bits: int = products[
            0
        ].dtype.bits  # pyright: ignore[reportAttributeAccessIssue]
        self.products = [RegArray(Bits(product_bits), 1) for _ in range(len(products))]
        for i in range(len(products)):
            self.products[i][0] = products[i]

        def update_register(flush, instr, result):
            physical_register_file[instr.rd_physical] = result

            register_ready.mark_ready(
                instr.rd_physical, enable=attach_context(~flush[0])
            )

            active_list_index = instr.active_list_idx
            with Condition(~flush[0]):
                active_list.set_ready(
                    index=active_list_index,
                    actual_branch=None,
                    new_imm=None,
                    new_imm_enable=None,
                )

        class MultiplyReduceLevel(Module):
            instr: Port

            def __init__(self):
                super().__init__(ports={"instr": Port(ALUQueueEntryType)})

            @module.combinational
            def build(self, products: list[Array], sum_level: Module, flush: Array):
                instr = self.instr.pop()
                sum, carry = wallace_tree.wallace_tree(
                    [products[i][0] for i in range(len(products))]
                )

                with Condition(~flush[0]):
                    sum_level.async_called(instr=instr, sum=sum, carry=carry)

        class MultiplySumLevel(Module):
            instr: Port
            sum: Port
            carry: Port

            def __init__(self):
                super().__init__(
                    ports={
                        "instr": Port(ALUQueueEntryType),
                        "sum": Port(Bits(product_bits)),
                        "carry": Port(Bits(product_bits)),
                    }
                )

            @module.combinational
            def build(self, flush: Array, update_register: Callable):
                instr, sum, carry = self.pop_all_ports(False)

                summary = combination_adder(sum, carry, 4)[0]

                is_higher_word = (
                    (instr.alu_op == (Bits(ALU_CODE_LEN)(ALU_Code.MULH.value)))
                    | (instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.MULSU.value))
                    | (instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.MULU.value))
                )
                result = is_higher_word.select(summary[32:63], summary[0:31])

                update_register(flush, instr, result)

        class Divider(Module):
            instr: Port
            op_a: Port
            op_b: Port
            quotient_sign: Port
            remainder_sign: Port

            PA: Array
            B: Array
            i: Array

            def __init__(self):
                super().__init__(
                    ports={
                        "instr": Port(ALUQueueEntryType),
                        "quotient_sign": Port(Bits(1)),
                        "remainder_sign": Port(Bits(1)),
                        "op_a": Port(Bits(32)),
                        "op_b": Port(Bits(32)),
                    }
                )
                self.PA = RegArray(Bits(32 + 32 + 1), 1)
                self.B = RegArray(Bits(32), 1)
                self.i = RegArray(UInt(6), 1)

            @module.combinational
            def build(self, flush: Array, update_register: Callable):
                with Condition(flush[0]):
                    with Condition(self.instr.valid()):
                        self.instr.pop()
                    with Condition(self.op_a.valid()):
                        self.op_a.pop()
                    with Condition(self.op_b.valid()):
                        self.op_b.pop()
                    with Condition(self.quotient_sign.valid()):
                        self.quotient_sign.pop()
                    with Condition(self.remainder_sign.valid()):
                        self.remainder_sign.pop()

                with Condition(~flush[0]):
                    is_new = self.op_a.valid()
                    with Condition(is_new):
                        op_a = self.op_a.pop()
                        op_b = self.op_b.pop()
                        lzc = leading_zero_count(op_a)
                        pa = (op_a << lzc).zext(Bits(32 + 32 + 1))

                        self.PA[0] = pa
                        self.B[0] = op_b
                        self.i[0] = lzc.zext(UInt(6))

                        self.async_called()

                    with Condition(~is_new):
                        is_loop_end = self.i[0] == Bits(6)(32)
                        with Condition(is_loop_end):
                            instr = self.instr.pop()
                            quotient_sign = self.quotient_sign.pop()
                            remainder_sign = self.remainder_sign.pop()

                            quotient = self.PA[0][0:31]
                            raw_remainder = self.PA[0][32:63]
                            is_remainder_negative = self.PA[0][64:64]
                            remainder = is_remainder_negative.select(
                                combination_adder(
                                    raw_remainder, self.B[0], 4
                                )[0],
                                raw_remainder,
                            )
                            final_quotient = quotient_sign.select(
                                utils.neg(quotient), quotient
                            )
                            final_remainder = remainder_sign.select(
                                utils.neg(remainder), remainder
                            )

                            is_div = (
                                instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.DIV.value)
                            ) | (
                                instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.DIVU.value)
                            )
                            result = is_div.select(final_quotient, final_remainder)

                            update_register(flush, instr, result)

                        with Condition(~is_loop_end):
                            is_negative = self.PA[0][64:64]
                            new_P = self.PA[0][31:63]
                            new_P = is_negative.select(
                                combination_adder(new_P, self.B[0].zext(Bits(33)), 4)[
                                    0
                                ],
                                combination_adder(
                                    new_P, ~self.B[0].zext(Bits(33)), 4, Bits(1)(1)
                                )[0],
                            )
                            new_A = self.PA[0][0:30].concat(~new_P[32:32])
                            self.PA[0] = new_P.concat(new_A)
                            self.i[0] = self.i[0] + UInt(6)(1)
                            self.async_called()

        mul_reduce_level = MultiplyReduceLevel()
        mul_sum_level = MultiplySumLevel()
        divider = Divider()
        mul_reduce_level.build(
            products=self.products, sum_level=mul_sum_level, flush=flush
        )
        mul_sum_level.build(flush=flush, update_register=update_register)

        def update_register_for_div(flush, instr, result):
            update_register(flush, instr, result)
            self.div_busy[0] = Bits(1)(0)

        divider.build(flush=flush, update_register=update_register_for_div)

        is_mul = (
            (instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.MUL.value))
            | (instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.MULH.value))
            | (instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.MULSU.value))
            | (instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.MULU.value))
        )

        with Condition(flush[0]):
            self.div_busy[0] = Bits(1)(0)

        with Condition(is_mul & ~flush[0]):
            mul_reduce_level.async_called(instr=instr)

        with Condition(~is_mul & ~flush[0]):
            is_div = instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.DIV.value)
            is_rem = instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.REM.value)
            is_divu = instr.alu_op == Bits(ALU_CODE_LEN)(ALU_Code.DIVU.value)

            is_signed = is_div | is_rem

            is_divider_zero = op_b == Bits(32)(0)
            is_overflow = (
                (op_a == Bits(32)(0x80000000))
                & (op_b == Bits(32)(0xFFFFFFFF))
                & is_signed
            )
            with Condition(is_divider_zero):
                is_div_like = is_div | is_divu
                update_register_for_div(
                    flush, instr, is_div_like.select(Bits(32)(0xFFFFFFFF), op_a)
                )
            with Condition(is_overflow):
                update_register_for_div(
                    flush, instr, is_div.select(Bits(32)(0x80000000), Bits(32)(0))
                )

            abs_op_a = (is_signed & op_a[31:31]).select(utils.neg(op_a), op_a)
            abs_op_b = (is_signed & op_b[31:31]).select(utils.neg(op_b), op_b)
            is_quotient_negative = (op_a[31:31] ^ op_b[31:31]) & is_signed
            is_remainder_negative = op_a[31:31] & is_signed

            with Condition(~is_divider_zero & ~is_overflow):
                divider.async_called(
                    instr=instr,
                    op_a=abs_op_a,
                    op_b=abs_op_b,
                    quotient_sign=is_quotient_negative,
                    remainder_sign=is_remainder_negative,
                )
