import functools
from assassyn.frontend import *
from r10k_cpu.downstreams.active_list import ActiveList, InstructionPushEntry
from r10k_cpu.downstreams.alu_queue import ALUQueuePushEntry
from r10k_cpu.downstreams.free_list import FreeList
from r10k_cpu.downstreams.lsq import LSQPushEntry
from r10k_cpu.downstreams.map_table import MapTable, MapTableWriteEntry
from r10k_cpu.instruction import select_instruction_args
from r10k_cpu.utils import Bool, attach_context


class Decoder(Module):
    PC: Port

    def __init__(self):
        super().__init__(ports={"PC": Port(Bits(32))})

    @module.combinational
    def build(
        self,
        instruction_reg: Array,
        map_table: MapTable,
        free_list: FreeList,
        active_list: ActiveList,
    ):
        PC: Value = self.pop_all_ports(
            validate=True
        )  # pyright: ignore[reportAssignmentType]

        instruction: Value = instruction_reg[0]
        rd = instruction[7:11]
        rs1 = instruction[15:19]
        rs2 = instruction[20:24]
        args = select_instruction_args(instruction)

        has_dest = args.has_rd
        logical_rd = has_dest.select(rd, Bits(5)(0))
        is_zero_register = logical_rd == Bits(5)(0)
        dest_valid = has_dest & ~is_zero_register

        old_physical_rd = dest_valid.select(map_table.read_spec(logical_rd), Bits(6)(0))
        physical_rd = dest_valid.select(free_list.free_reg(), free_list.zero_reg)
        physical_rs1 = map_table.read_spec(rs1)
        physical_rs2 = map_table.read_spec(rs2)

        wait_until(~active_list.is_full())

        # Branch predictor is attached outside of the decoder
        active_list_entry_partial = functools.partial(
            InstructionPushEntry,
            valid=attach_context(Bool(1)),
            pc=PC,
            dest_logical=logical_rd,
            dest_new_physical=physical_rd,
            dest_old_physical=old_physical_rd,
            has_dest=dest_valid,
            imm=args.imm,
            is_branch=args.is_branch,
            is_alu=args.is_alu,
            is_jump=args.is_jump,
            is_jalr=args.is_jalr,
            is_terminator=args.is_terminator,
        )

        alu_push_enable = args.is_alu
        alu_queue_entry = ALUQueuePushEntry(
            rs1_physical=physical_rs1,
            rs2_physical=physical_rs2,
            rd_physical=physical_rd,
            alu_op=args.alu_op,
            imm=args.imm,
            operant1_from=args.operant1_from,
            operant2_from=args.operant2_from,
            PC=PC,
            is_branch=args.is_branch,
            branch_flip=args.branch_flip,
        )

        lsq_push_enable = ~(args.is_alu)
        lsq_entry = LSQPushEntry(
            rs1_physical=physical_rs1,
            rs2_physical=physical_rs2,
            rd_physical=physical_rd,
            imm=args.imm,
            is_load=args.is_load,
            is_store=args.is_store,
            op_type=args.mem_op,
        )

        free_list_pop_enable = dest_valid

        map_table_entry = MapTableWriteEntry(
            enable=dest_valid,
            logical_idx=logical_rd,
            physical_value=physical_rd,
        )

        return (
            active_list_entry_partial,
            alu_push_enable,
            alu_queue_entry,
            lsq_push_enable,
            lsq_entry,
            free_list_pop_enable,
            map_table_entry,
        )
