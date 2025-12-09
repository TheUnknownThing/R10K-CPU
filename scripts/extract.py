#!/usr/bin/env python3

import os
import argparse
import subprocess

parser = argparse.ArgumentParser(description="Compile c file and extract to hex file.")
parser.add_argument("filename", type=str, help="The path to the input file")
parser.add_argument("--output", "-o", type=str, help="Specify the output file", required=False)
parser.add_argument(
    "--optimize", "-O", type=int, choices=[0, 1, 2, 3], help="Specify the optimization level", required=False, default=3
)
parser.add_argument("--disassemble", "-d", help="Generate disassemble file", action="store_true")
args = vars(parser.parse_args())

filename: str = args["filename"]
optimization_level = args["optimize"]
gen_dis = args["disassemble"]

raw_name, _ = os.path.splitext(os.path.basename(filename))
dirname = os.path.dirname(filename)

elf_name = os.path.join(dirname, raw_name + ".elf")
bin_name = os.path.join(dirname, raw_name + ".bin")
hex_name = os.path.join(dirname, raw_name + ".hex")
dis_name = os.path.join(dirname, raw_name + ".dis")

script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)
linker_script_path = os.path.join(script_dir, "link.ld")
boot_path = os.path.join(script_dir, "boot.s")

subprocess.check_output(
    [
        "riscv64-unknown-elf-gcc",
        "-march=rv32i",
        "-mabi=ilp32",
        "-nostdlib",
        "-nostartfiles",
        "-T",
        linker_script_path,
        f"-O{optimization_level}",
        boot_path,
        filename,
        "-o",
        elf_name,
    ],
)

subprocess.check_output(["riscv64-unknown-elf-objcopy", "-O", "binary", elf_name, bin_name])
if gen_dis:
    dis = subprocess.check_output(["riscv64-unknown-elf-objdump", "-d", "-j", ".data", "-j", ".text", elf_name])
    with open(dis_name, "wb") as f:
        f.write(dis)

with open(bin_name, "rb") as bin, open(hex_name, "w") as hex:
    while True:
        instruction = bin.read(4)
        if not instruction:
            break
        code = int.from_bytes(instruction, byteorder="little")
        hex.write(f"{code:08x}\n")

os.remove(elf_name)
os.remove(bin_name)
