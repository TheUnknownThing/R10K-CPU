from abc import ABC
from dataclasses import dataclass, asdict
from typing import Any, Callable, Self
from assassyn.frontend import *
from assassyn.ir.dtype import RecordValue


@dataclass
class RecordWrapper(ABC):
    def foreach(self, method: Callable[[Value], Value]) -> Self:
        d = asdict(self)
        new_dict = {name: method(value) for name, value in d.items()}
        return type(self)(**new_dict)

    def dispatch(self, other: Self, method: Callable[[Value, Value], Value]) -> Self:
        assert type(self) is type(other)
        lefts = asdict(self)
        rights = asdict(other)
        new_dict = {name: method(l, r) for name, l, r in zip(lefts.keys(), lefts.values(), rights.values())}
        return type(self)(**new_dict)

    def to_bundle(self) -> RecordValue:
        d: dict[str, Value] = asdict(self)
        inner_types = {name: value.dtype for name, value in d.items()}
        record = Record(**inner_types)
        bundle = record.bundle(**d)
        return bundle

    @classmethod
    def from_bundle(cls, bundle: RecordValue) -> Self:
        return cls()


@dataclass
class ROBEntry(RecordWrapper):
    pc: Value = Bits(32)(0)
    dest_logical: Value = Bits(5)(0)
    dest_new_physical: Value = Bits(6)(0)
    dest_old_physical: Value = Bits(6)(0)
    ready: Value = Bits(1)(0)
    is_branch: Value = Bits(1)(0)
    predict_branch: Value = Bits(1)(0)
    actual_branch: Value = Bits(1)(0)


e = ROBEntry()
new_e = e.dispatch(ROBEntry(pc=Bits(32)(100)), lambda x, y: y)

b = new_e.to_bundle()
c = b.dtype.view(b.value())

print(c.pc)