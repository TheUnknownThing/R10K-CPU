from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from assassyn.frontend import *
from r10k_cpu.utils import Bool, attach_context


@dataclass
class PredictFeedback:
    addr: Value
    predict_branch: Value
    actual_branch: Value


class Predictor(Downstream, ABC):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def build_predict(self, branch_addr: Value) -> Value:
        pass

    @abstractmethod
    def build_feedback(self, feed_back: PredictFeedback):
        pass

    @downstream.combinational
    def build(self, branch_addr: Value, feed_back: PredictFeedback) -> Value:
        feedback_valid = feed_back.addr.valid()
        with Condition(feedback_valid):
            self.build_feedback(feed_back)

        is_valid = branch_addr.valid()
        with Condition(is_valid):
            branch_predict = self.build_predict(branch_addr)
            branch_predict = attach_context(branch_predict)

        return branch_predict


class AlwaysBranchPredictor(Predictor):
    def __init__(self):
        super().__init__()

    def build_predict(self, branch_addr: Value) -> Value:
        return Bool(1)

    def build_feedback(self, feed_back: PredictFeedback):
        pass


class NeverBranchPredictor(Predictor):
    def __init__(self):
        super().__init__()

    def build_predict(self, branch_addr: Value) -> Value:
        return Bool(0)

    def build_feedback(self, feed_back: PredictFeedback):
        pass


class BinaryPredictState(Enum):
    StronglyB = 0
    WeaklyB = 1
    WeaklyNo = 2
    StronglyNo = 3


class BinaryPredictor(Predictor):
    bits: int

    states: Array

    def __init__(self, bits: int, init_state: BinaryPredictState):
        super().__init__()

        assert bits > 0
        self.bits = bits
        size = 1 << bits
        self.states = RegArray(UInt(2), size, [init_state.value] * size)

    def build_predict(self, branch_addr: Value) -> Value:
        state = self.states[self.extract_branch_bits(branch_addr)]

        return (state == UInt(2)(BinaryPredictState.StronglyB.value)) | (
            state == UInt(2)(BinaryPredictState.WeaklyB.value)
        )

    def extract_branch_bits(self, branch_addr):
        return branch_addr[0 : (self.bits - 1)]

    def build_feedback(self, feed_back: PredictFeedback):
        addr = feed_back.addr
        actual_branch = feed_back.actual_branch

        branch_bits = self.extract_branch_bits(addr)
        state = self.states[branch_bits]

        new_state = actual_branch.select(
            (state == UInt(2)(0)).select(state, state - UInt(2)(1)),
            ((state == UInt(2)(3)).select(state, state + UInt(2)(1))),
        )
        self.states[branch_bits] = new_state
