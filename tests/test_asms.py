import os
import re
import shutil
import pytest

from assassyn.frontend import *
from assassyn.utils import run_simulator, build_simulator, run_verilator

from main import build_cpu
from r10k_cpu.utils import prepare_byte_files
from utils import run_quietly

test_cases_path = "asms"
work_path = "tmp"


def test_asms():
    work_hex_paths = [
        os.path.join(work_path, fname)
        for fname in ["exe.hex", "exe_b0.hex", "exe_b1.hex", "exe_b2.hex", "exe_b3.hex"]
    ]

    os.makedirs(work_path, exist_ok=True)
    sys, simulator_path, verilog_path = build_cpu(
        sram_files=work_hex_paths, sim_threshold=10000000
    )
    simulator_binary, stdout, stderr = run_quietly(build_simulator, simulator_path)
    assert (
        simulator_binary
    ), f"Build simulator failed with stdout: \n{stdout}\n stderr: \n{stderr}\n"
    print(f"Simulator built at {simulator_binary}")

    test_cases = ['test_div', 'queens', 'store_byte_half', 'arithmetic', 'test_mul', 'vector_add', 'logic_ops', 'multiarray', 'bubble_sort', 'sum100', 'hanoi', 'quick_sort', 'qsort', 'empty', 'primes', 'math_comprehensive', 'sum', 'magic', 'matrix_mul', 'vector_mul', 'test_rem', 'fibonacci']
    # test_cases = ['store_byte_half']
    print(test_cases)

    for test_case in test_cases:
        hex_path = os.path.join(test_cases_path, test_case, test_case + ".hex")
        out_path = os.path.join(test_cases_path, test_case, test_case + ".out")
        with open(out_path, "r") as f:
            expected_result = int(f.readline())

        shutil.copyfile(hex_path, work_hex_paths[0])
        prepare_byte_files(work_hex_paths[0])

        raw, stdout, stderr = run_quietly(run_simulator, binary_path=simulator_binary)
        assert isinstance(
            raw, str
        ), f"Run simulator failed with stdout: \n{stdout}\n stderr: \n{stderr}\n"

        result = raw.splitlines()[-1]
        assert (
            "PC=0x00000008" in result
        ), f"The processor is not down properly while testing {test_case}"

        ret = re.search(r"x10=(0x[0-9a-fA-F]+)", result)
        assert (
            ret
        ), f"Can't find result in the last line of output while testing {test_case}"
        ret = int(ret.group(1), 16)
        assert (
            ret == expected_result
        ), f"Test failed for {test_case}: expect result is {expected_result}, get {ret}, the raw output is\n{raw}"
        print(f"{test_case} passed!")


@pytest.mark.slow
def test_asms_verilator():
    work_hex_paths = [
        os.path.join(work_path, fname)
        for fname in ["exe_bf.hex", "exe_b0.hex", "exe_b1.hex", "exe_b2.hex", "exe_b3.hex"]
    ]

    os.makedirs(work_path, exist_ok=True)
    sys, simulator_path, verilog_path = build_cpu(
        sram_files=work_hex_paths, sim_threshold=10000000, verilog=True
    )

    test_cases = os.listdir(test_cases_path)
    print(test_cases)

    for test_case in test_cases:
        hex_path = os.path.join(test_cases_path, test_case, test_case + ".hex")
        out_path = os.path.join(test_cases_path, test_case, test_case + ".out")
        with open(out_path, "r") as f:
            expected_result = int(f.readline())

        shutil.copyfile(hex_path, work_hex_paths[0])
        prepare_byte_files(work_hex_paths[0])

        raw, _, stderr = run_quietly(run_verilator, verilog_path)
        assert isinstance(raw, str), f"Run verilator failed with stderr: \n {stderr}"

        result = [line for line in raw.splitlines() if line.startswith("@line")][-1]
        assert (
            "PC=0x00000008" in result
        ), f"The processor is not down properly while testing {test_case}"

        ret = re.search(r"x10=(0x[0-9a-fA-F]+)", result)
        assert (
            ret
        ), f"Can't find result in the last line of output while testing {test_case}"
        ret = int(ret.group(1), 16)
        assert (
            ret == expected_result
        ), f"Test failed for {test_case}: expect result is {expected_result}, get {ret}, the raw output is \n{raw}"
        print(f"{test_case} passed!")
