from math import ceil, log2
from assassyn.frontend import *
from assassyn.ir.dtype import RecordValue
from assassyn.ir.array import ArrayRead

Bool = Bits(1)


# For sext in assassyn is implemented incorrectly
def sext(value: Value, target_type: DType) -> Value:
    dtype: DType = value.dtype  # pyright: ignore[reportAssignmentType]
    bits: int = dtype.bits
    target_bits = target_type.bits
    delta_bits = target_bits - bits

    assert delta_bits > 0

    is_negative = value[bits - 1 : bits - 1]
    higher = is_negative.select(
        Bits(delta_bits)((1 << delta_bits) - 1), Bits(delta_bits)(0)
    )
    return higher.concat(value).bitcast(target_type)


def attach_context(value: Value) -> Value:
    """Attach context information to a value. Use for conditional control flow."""
    return value.bitcast(value.dtype)


def replace_bundle(bundle: RecordValue | ArrayRead, **kwargs) -> RecordValue:
    record = bundle.dtype
    assert isinstance(record, Record)
    field_names = record.fields.keys()
    for x in field_names:
        if x not in kwargs:
            kwargs[x] = bundle.__getattr__(x)
    return record.bundle(**kwargs)


def is_between(value: Value, lower: Value, upper: Value) -> Value:
    """Check whether value is between lower and upper (exclusive) in a circular queue."""
    """Attention: If lower == upper, this function returns True for all value, which is meaningful if the queue is full, but this may be unexpected in other cases."""
    is_wrapped = lower >= upper

    is_after_lower = value >= lower
    is_before_upper = value < upper

    return is_wrapped.select(
        is_after_lower | is_before_upper, is_after_lower & is_before_upper
    )


def neg(value: Value) -> Value:
    dtype: DType = value.dtype  # pyright: ignore[reportAssignmentType]
    bits: int = dtype.bits
    return ((~value).bitcast(UInt(bits)) + UInt(bits)(1)).bitcast(dtype)


def leading_zero_count(value: Value, *, trailing: bool = False) -> Value:
    """Count the number of leading zeros in a Bits value."""

    bits = value.dtype.bits  # pyright: ignore[reportAttributeAccessIssue]
    bit_count = ceil(log2(bits))

    def recursive(left: int, right: int) -> Value:
        if left == right:
            return UInt(bit_count)(0)
        if left + 1 == right:
            if trailing:
                return (~value[left:left]).zext(UInt(bit_count))
            else:
                return (~value[bits - 1 - left : bits - 1 - left]).zext(UInt(bit_count))
        mid = (left + right) // 2
        left_half = recursive(left, mid)
        right_half = recursive(mid, right)
        left_half_count = mid - left
        return (left_half == UInt(bit_count)(left_half_count)).select(
            left_half + right_half, left_half
        )

    return recursive(0, bits)


def prepare_byte_files(init_file: str) -> list[str]:
    """
    Split a 32-bit hex file into 4 byte hex files.

    Given init_file = "file.hex", creates:
    - file_bf.hex (offset truncated 32-bit words)
    - file_b0.hex (bits 7:0)
    - file_b1.hex (bits 15:8)
    - file_b2.hex (bits 23:16)
    - file_b3.hex (bits 31:24)
    """
    import os

    base, ext = os.path.splitext(init_file)
    offset_trunc_file = f"{base}_bf{ext}"
    byte_files = [f"{base}_b{i}{ext}" for i in range(4)]

    # Check if we need to regenerate
    if os.path.exists(init_file):
        try:
            with open(init_file, "r") as f:
                lines = f.readlines()

            trunc_data = []
            byte_data = [[], [], [], []]
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("@"):
                    # Add segment marker to all byte files
                    addr = int(line[1:], 16)
                    assert addr % 4 == 0, "Address in init file must be 4-byte aligned"
                    trunc_addr = addr // 4
                    line = f"@{trunc_addr:x}"
                    trunc_data.append(line)
                    for i in range(4):
                        byte_data[i].append(line)
                    continue
                # Parse 32-bit hex value
                word = int(line, 16)
                byte_data[0].append(f"{(word >> 0) & 0xFF:02x}")
                byte_data[1].append(f"{(word >> 8) & 0xFF:02x}")
                byte_data[2].append(f"{(word >> 16) & 0xFF:02x}")
                byte_data[3].append(f"{(word >> 24) & 0xFF:02x}")
                trunc_data.append(f"{word:08x}")

            for i in range(4):
                with open(byte_files[i], "w") as f:
                    f.write("\n".join(byte_data[i]))
                    if byte_data[i]:
                        f.write("\n")
            with open(offset_trunc_file, "w") as f:
                f.write("\n".join(trunc_data))
                if trunc_data:
                    f.write("\n")
        except Exception as e:
            print(f"Error processing init file {init_file}: {e}")
            raise

    return [offset_trunc_file] + byte_files
