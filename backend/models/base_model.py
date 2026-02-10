from abc import ABC, abstractmethod
import tensorflow as tf


class BaseMLModel(ABC):
    """Abstract base for all ML model definitions."""

    @abstractmethod
    def build(self) -> tf.keras.Model:
        """Build and return the compiled Keras model."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return a unique identifier for this model."""
        ...

    @abstractmethod
    def get_description(self) -> str:
        """Human-readable description."""
        ...
