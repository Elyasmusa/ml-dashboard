import numpy as np
import tensorflow as tf
from config import settings


class InferenceService:
    _loaded_models: dict[str, tf.keras.Model] = {}

    def predict(self, model_name: str, input_data: list[list[float]]) -> list[float]:
        model = self._get_model(model_name)
        data = np.array(input_data)
        predictions = model.predict(data, verbose=0)
        return predictions.flatten().tolist()

    def _get_model(self, model_name: str) -> tf.keras.Model:
        if model_name not in self._loaded_models:
            model_path = settings.model_dir / f"{model_name}.keras"
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Model '{model_name}' not found at {model_path}"
                )
            self._loaded_models[model_name] = tf.keras.models.load_model(
                str(model_path)
            )
        return self._loaded_models[model_name]
