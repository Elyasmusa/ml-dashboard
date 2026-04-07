from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import torch
from config import settings

logger = logging.getLogger(__name__)


class InferenceService:
    _loaded_models: dict[str, torch.nn.Module] = {}
    _loaded_configs: dict[str, dict] = {}

    def predict(self, model_name: str, input_data: list[list[float]]) -> list[float]:
        model = self._get_model(model_name)
        data = torch.tensor(input_data, dtype=torch.float32)
        model.eval()
        with torch.no_grad():
            predictions = model(data).numpy()
        return predictions.flatten().tolist()

    def predict_next_order(
        self, input_row: dict[str, Any], model_name: str = "order_predictor",
    ) -> float:
        """Predict days until next order from a raw feature dict."""
        model = self._get_model(model_name)
        config = self._get_config(model_name)

        vec = self._build_feature_vector(input_row, config)

        data = torch.tensor([vec], dtype=torch.float32)
        model.eval()
        with torch.no_grad():
            prediction = model(data).numpy()

        raw_pred = float(prediction.flatten()[0])

        # Denormalize from target normalization
        target_mean = config.get("target_mean", 0.0)
        target_std = config.get("target_std", 1.0)
        return raw_pred * target_std + target_mean

    def predict_next_products(
        self, input_row: dict[str, Any], model_name: str = "product_predictor",
    ) -> dict[str, float]:
        """Predict next-order product quantities from a raw feature dict.

        Returns {target_col_name: predicted_qty} after denormalization.
        """
        model = self._get_model(model_name)
        config = self._get_config(model_name)

        vec = self._build_feature_vector(input_row, config)

        data = torch.tensor([vec], dtype=torch.float32)
        model.eval()
        with torch.no_grad():
            prediction = model(data).numpy()  # shape [1, n_products]

        raw_preds = prediction[0]  # shape [n_products]

        target_names = config.get("target_names", [])
        target_means = np.array(config.get("target_means", []))
        target_stds = np.array(config.get("target_stds", []))

        # Denormalize
        denorm = raw_preds * target_stds + target_means

        return {name: float(val) for name, val in zip(target_names, denorm)}

    def _build_feature_vector(
        self, input_row: dict[str, Any], config: dict,
    ) -> list[float]:
        """Build a feature vector in the same order as training."""
        feature_names: list[str] = config["feature_names"]
        loc_cols: list[str] = config.get("loc_cols", [])
        prod_cols: list[str] = config.get("prod_cols", [])
        temporal_cols: list[str] = config.get("temporal_cols", [])

        month = float(input_row.get("orderMonth", 6))
        month_sin = float(np.sin(2 * np.pi * month / 12))
        month_cos = float(np.cos(2 * np.pi * month / 12))

        vec: list[float] = []
        for name in feature_names:
            if name == "day_sin":
                day = float(input_row.get("orderDay", 15))
                vec.append(float(np.sin(2 * np.pi * day / 31)))
            elif name == "day_cos":
                day = float(input_row.get("orderDay", 15))
                vec.append(float(np.cos(2 * np.pi * day / 31)))
            elif name == "month_sin":
                vec.append(month_sin)
            elif name == "month_cos":
                vec.append(month_cos)
            elif name == "order_size":
                vec.append(float(input_row.get("order_size", 0.5)))
            elif name in temporal_cols:
                raw = float(input_row.get(name, 0))
                idx = temporal_cols.index(name)
                means = config.get("temporal_scaler_mean", [])
                scales = config.get("temporal_scaler_scale", [])
                if means and scales and idx < len(means):
                    raw = (raw - means[idx]) / max(scales[idx], 1e-8)
                vec.append(raw)
            elif name == "year_norm":
                vec.append(float(input_row.get("year_norm", 0.5)))
            elif name.endswith("_month_sin"):
                loc_name = name.removesuffix("_month_sin")
                loc_val = float(input_row.get(loc_name, 0))
                vec.append(loc_val * month_sin)
            elif name.endswith("_month_cos"):
                loc_name = name.removesuffix("_month_cos")
                loc_val = float(input_row.get(loc_name, 0))
                vec.append(loc_val * month_cos)
            elif name in loc_cols:
                vec.append(float(input_row.get(name, 0)))
            elif name in prod_cols:
                raw = float(input_row.get(name, 0))
                idx = prod_cols.index(name)
                means = config.get("prod_scaler_mean", [])
                scales = config.get("prod_scaler_scale", [])
                if means and scales and idx < len(means):
                    raw = (raw - means[idx]) / max(scales[idx], 1e-8)
                vec.append(raw)
            else:
                vec.append(0.0)

        return vec

    def _get_model(self, model_name: str) -> torch.nn.Module:
        if model_name not in self._loaded_models:
            config = self._get_config(model_name)
            input_dim = config.get("input_dim")
            if input_dim is None:
                raise ValueError(
                    f"Config for '{model_name}' missing 'input_dim'. Retrain the model."
                )

            model_type = config.get("model_type", "order_predictor")

            if model_type == "product_predictor":
                from models.product_predictor import ProductPredictorNet
                output_dim = config.get("output_dim")
                if output_dim is None:
                    raise ValueError(
                        f"Config for '{model_name}' missing 'output_dim'. Retrain the model."
                    )
                model = ProductPredictorNet(input_dim, output_dim)
            else:
                from models.order_predictor import OrderPredictorNet
                model = OrderPredictorNet(input_dim)

            model_path = settings.model_dir / f"{model_name}.pt"
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Model '{model_name}' not found at {model_path}"
                )
            _MAX_MODEL_BYTES = 500 * 1024 * 1024  # 500 MB guard
            model_size = model_path.stat().st_size
            if model_size > _MAX_MODEL_BYTES:
                raise ValueError(
                    f"Model file '{model_path.name}' ({model_size // 1024 // 1024} MB) "
                    f"exceeds the {_MAX_MODEL_BYTES // 1024 // 1024} MB safety limit"
                )
            model.load_state_dict(torch.load(str(model_path), weights_only=True))
            model.eval()
            self._loaded_models[model_name] = model
        return self._loaded_models[model_name]

    def clear_model(self, model_name: str) -> None:
        """Remove cached model and config so the next call loads fresh files."""
        self._loaded_models.pop(model_name, None)
        self._loaded_configs.pop(model_name, None)

    def _get_config(self, model_name: str) -> dict:
        if model_name not in self._loaded_configs:
            config_path = settings.model_dir / f"{model_name}_config.json"
            if not config_path.exists():
                raise FileNotFoundError(
                    f"Config for '{model_name}' not found at {config_path}"
                )
            self._loaded_configs[model_name] = json.loads(
                config_path.read_text(encoding="utf-8")
            )
        return self._loaded_configs[model_name]
