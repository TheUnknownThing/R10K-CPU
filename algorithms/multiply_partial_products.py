from assassyn.frontend import *


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
