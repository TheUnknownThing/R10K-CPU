import os
import re
import shutil
import pytest

from assassyn.frontend import *
from assassyn.utils import run_simulator, build_simulator, run_verilator

from main import build_cpu
from utils import run_quietly

test_cases_path = "asms"
work_path = "tmp"


def test_asms():
    work_hex_path = os.path.join(work_path, "exe.hex")

    os.makedirs(work_path, exist_ok=True)
    sys, simulator_path, verilog_path = build_cpu(
        sram_file=work_hex_path, sim_threshold=1000000
    )
    simulator_binary, stdout, stderr = run_quietly(build_simulator, simulator_path)
    assert simulator_binary, f"Build simulator failed with stdout: \n{stdout}\n stderr: \n{stderr}\n"
    print(f"Simulator built at {simulator_binary}")

    test_cases = os.listdir(test_cases_path)
    print(test_cases)

    for test_case in test_cases:
        hex_path = os.path.join(test_cases_path, test_case, test_case + ".hex")
        out_path = os.path.join(test_cases_path, test_case, test_case + ".out")
        with open(out_path, "r") as f:
            expected_result = int(f.readline())

        shutil.copyfile(hex_path, work_hex_path)

        raw, stdout, stderr = run_quietly(run_simulator, binary_path=simulator_binary)
        assert isinstance(raw, str), f"Run simulator failed with stdout: \n{stdout}\n stderr: \n{stderr}\n"

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
        ), f"Test failed for {test_case}: expect result is {expected_result}, get {ret}"
        print(f"{test_case} passed!")

@pytest.mark.slow
def test_asms_verilator():
    work_hex_path = os.path.join(work_path, "exe.hex")

    os.makedirs(work_path, exist_ok=True)
    sys, simulator_path, verilog_path = build_cpu(
        sram_file=work_hex_path, sim_threshold=1000000, verilog=True
    )

    test_cases = os.listdir(test_cases_path)
    print(test_cases)

    for test_case in test_cases:
        hex_path = os.path.join(test_cases_path, test_case, test_case + ".hex")
        out_path = os.path.join(test_cases_path, test_case, test_case + ".out")
        with open(out_path, "r") as f:
            expected_result = int(f.readline())

        shutil.copyfile(hex_path, work_hex_path)

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
        ), f"Test failed for {test_case}: expect result is {expected_result}, get {ret}"
        print(f"{test_case} passed!")
