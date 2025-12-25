from assassyn.frontend import *


def combination_adder(
    a: Value, b: Value, ripple_carry_length: int, CIn: Value = Bits(1)(0)
) -> tuple[Value, Value]:
    """Combination of CLA and ripple-carry adder"""

    bits: int = a.dtype.bits  # pyright: ignore[reportAttributeAccessIssue]
    assert bits == b.dtype.bits, "Input operands must have the same bit width" # pyright: ignore[reportAttributeAccessIssue]

    def recursive(
        left: int, right: int, Cin: Value
    ) -> tuple[Value, Value, Value, Value]:
        if right - left <= ripple_carry_length:
            P = Bits(1)(1)
            G = Bits(0)(0)
            C = Cin
            S = Bits(0)(0)
            for i in range(left, right):
                pi = a[i:i] ^ b[i:i]
                gi = a[i:i] & b[i:i]
                new_P = P & pi
                new_G = gi | (pi & G)
                P = new_P
                G = new_G
                Si = pi ^ C
                S = Si.concat(S)
                C = gi | (pi & C)
            return P, G, S, C
        else:
            mid = (left + right) // 2

            P1, G1, S1, _ = recursive(left, mid, Cin)
            CMid = G1 | (P1 & Cin)
            P2, G2, S2, C2 = recursive(mid, right, CMid)
            G12 = (P2 & G1) | G2
            P12 = P1 & P2
            S = S2.concat(S1)

            return P12, G12, S, C2

    _, _, S, C = recursive(0, bits, CIn)

    return S, C
