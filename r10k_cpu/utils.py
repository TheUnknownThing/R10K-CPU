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
    return value | value


def replace_bundle(bundle: RecordValue | ArrayRead, **kwargs) -> RecordValue:
    record = bundle.dtype
    assert isinstance(record, Record)
    field_names = record.fields.keys()
    for x in field_names:
        if x not in kwargs:
            kwargs[x] = bundle.__getattr__(x)
    return record.bundle(**kwargs)
