from assassyn.frontend import *


def wallace_tree(adders: list[Value]) -> tuple[Value, Value]:

    assert len(adders) >= 3, "At least three adders are required"

    current_level = adders

    while len(current_level) > 2:
        next_level = []
        for i in range(0, len(current_level), 3):
            group = current_level[i : i + 3]
            if len(group) == 3:
                a, b, c = group
                sum_ = a ^ b ^ c
                carry = (a & b) | (b & c) | (a & c)
                next_level.append(sum_)
                next_level.append(carry << 1)
            else:
                next_level.extend(group)
        current_level = next_level

    assert len(current_level) == 2

    return current_level[0], current_level[1]
