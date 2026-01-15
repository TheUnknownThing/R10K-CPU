from algorithms.adder import combination_adder
from assassyn.frontend import *
from r10k_cpu.utils import sext


def basic_partial_products(a: Value, b: Value) -> list[Value]:
    bits_a: int = a.dtype.bits  # pyright: ignore[reportAttributeAccessIssue]
    bits_b: int = b.dtype.bits  # pyright: ignore[reportAttributeAccessIssue]

    products = []
    for i in range(bits_b):
        bit = b[i:i]
        partial_product = (
            bit.select(a, Bits(bits_a)(0))
            .concat(Bits(i)(0))
            .zext(Bits(bits_a + bits_b))
        )
        products.append(partial_product)
    return products


def radix4_partial_products(a: Value, b: Value) -> list[Value]:
    bits_a: int = a.dtype.bits  # pyright: ignore[reportAttributeAccessIssue]
    bits_b: int = b.dtype.bits  # pyright: ignore[reportAttributeAccessIssue]

    extended_a = sext(a.concat(Bits(1)(0)), Bits(bits_a + 2))
    neg_b = combination_adder(~b, Bits(bits_b)(1), 4)[0]

    bits = bits_a + bits_b

    products = []
    for i in range(0, bits_a, 2):
        slice_a = extended_a[i : i + 2]
        product = slice_a.case(
            {
                None: Bits(bits)(0), # pyright: ignore[reportArgumentType]
                Bits(3)(0b001): sext(b.concat(Bits(i)(0)), Bits(bits)),
                Bits(3)(0b010): sext(b.concat(Bits(i)(0)), Bits(bits)),
                Bits(3)(0b011): sext(b.concat(Bits(i + 1)(0)), Bits(bits)),
                Bits(3)(0b100): sext(neg_b.concat(Bits(i + 1)(0)), Bits(bits)),
                Bits(3)(0b101): sext(neg_b.concat(Bits(i)(0)), Bits(bits)),
                Bits(3)(0b110): sext(neg_b.concat(Bits(i)(0)), Bits(bits)),
            }
        )
        products.append(product)

    return products
