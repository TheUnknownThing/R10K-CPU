from abc import ABC, abstractmethod
from dataclasses import dataclass
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
