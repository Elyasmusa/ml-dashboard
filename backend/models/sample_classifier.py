import tensorflow as tf
from models.base_model import BaseMLModel


class SampleClassifier(BaseMLModel):
    def __init__(self, input_dim: int = 784, num_classes: int = 10):
        self.input_dim = input_dim
        self.num_classes = num_classes

    def get_name(self) -> str:
        return "sample_classifier"

    def get_description(self) -> str:
        return "A simple dense classifier for demonstration purposes."

    def build(self) -> tf.keras.Model:
        model = tf.keras.Sequential([
            tf.keras.layers.Input(shape=(self.input_dim,)),
            tf.keras.layers.Dense(128, activation="relu"),
            tf.keras.layers.Dropout(0.3),
            tf.keras.layers.Dense(64, activation="relu"),
            tf.keras.layers.Dropout(0.3),
            tf.keras.layers.Dense(self.num_classes, activation="softmax"),
        ])
        model.compile(
            optimizer="adam",
            loss="sparse_categorical_crossentropy",
            metrics=["accuracy"],
        )
        return model
