from ..config import ConfigDict
from typing import List

CONFIG_NAME = "learning"

class LearningConfig(ConfigDict):
    """
    Configuration for learning rates and gradient norm balancing
    """
    grad_norm_lr: float = 0.05
    grad_norm_initial_refresh_rate: int = 50
    grad_norm_alpha: float = 0

    loss_priority: List[float] = [0.3, 0.7]

    lr: float = 0.00003


