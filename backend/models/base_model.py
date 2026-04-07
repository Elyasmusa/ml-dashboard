from abc import ABC, abstractmethod

import torch.nn as nn


class BaseMLModel(ABC):
    """Abstract base for all ML model definitions."""

    @abstractmethod
    def build(self) -> nn.Module:
        """Build and return the PyTorch model."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return a unique identifier for this model."""
        ...

    @abstractmethod
    def get_description(self) -> str:
        """Human-readable description."""
        ...
