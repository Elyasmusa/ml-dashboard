from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import BackgroundTasks
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

from config import settings, VARIANT_NAMES
from schemas.training import (
    TrainingRequest,
    ProductTrainingResponse,
    ProductVariantResult,
    TrainingStatus,
)
from services.base_training_service import BaseTrainingService

logger = logging.getLogger(__name__)

_PREDICTIONS_DIR: Path = settings.cache_dir / "predictions"


def _load_product_matrix(variant: str) -> pd.DataFrame:
    """Load the product matrix for a specific data variant."""
    path = settings.cache_dir / f"franchise_product_matrix_{variant}" / "matrix.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Product matrix for variant '{variant}' not found at {path}. "
            "Fetch order data first so the matrix is built."
        )
    return pd.read_parquet(path)


def _prepare_product_dataset(
    df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], list[str], dict]:
    """Build feature matrix X and multi-output target Y from the product matrix.

    Returns (X, Y_raw, Y_normalized, feature_names, target_names, config).
    """
    # ── Identify target columns ──────────────────────────────────
    next_prod_cols = sorted([c for c in df.columns if c.startswith("next_prod_")])
    if not next_prod_cols:
        raise ValueError("No next_prod_* columns found in the product matrix")

    # Drop rows where next order has no products (all zeros)
    mask = df[next_prod_cols].sum(axis=1) > 0
    df = df[mask].copy()

    if df.empty:
        raise ValueError("No rows with next-order product data available for training")

    # ── Build targets ────────────────────────────────────────────
    Y_raw = df[next_prod_cols].fillna(0).astype(np.float32).values

    # Per-product normalization
    target_scaler = StandardScaler()
    Y_norm = target_scaler.fit_transform(Y_raw).astype(np.float32)

    # Guard against near-zero scales
    safe_stds = np.where(target_scaler.scale_ < 1e-8, 1.0, target_scaler.scale_)

    # ── Build features (same as order prediction) ────────────────
    feature_parts: list[np.ndarray] = []
    feature_names: list[str] = []

    # 1. Cyclical date encoding
    day_vals = df["orderDay"].fillna(15).astype(float).values
    month_vals = df["orderMonth"].fillna(6).astype(float).values

    month_sin_vals = np.sin(2 * np.pi * month_vals / 12).reshape(-1, 1)
    month_cos_vals = np.cos(2 * np.pi * month_vals / 12).reshape(-1, 1)

    feature_parts.append(np.sin(2 * np.pi * day_vals / 31).reshape(-1, 1))
    feature_names.append("day_sin")
    feature_parts.append(np.cos(2 * np.pi * day_vals / 31).reshape(-1, 1))
    feature_names.append("day_cos")
    feature_parts.append(month_sin_vals)
    feature_names.append("month_sin")
    feature_parts.append(month_cos_vals)
    feature_names.append("month_cos")

    # 2. Order size
    if "order_size" in df.columns:
        feature_parts.append(df["order_size"].fillna(0.5).astype(float).values.reshape(-1, 1))
        feature_names.append("order_size")

    # 3. Temporal features (StandardScaled)
    temporal_col_names = ["days_since_last", "avg_gap", "order_count", "prev_gap", "gap_trend"]
    available_temporal = [c for c in temporal_col_names if c in df.columns]
    if available_temporal:
        temporal_arr = df[available_temporal].fillna(0).astype(float).values
        temporal_scaler = StandardScaler()
        temporal_arr = temporal_scaler.fit_transform(temporal_arr)
        feature_parts.append(temporal_arr)
        feature_names.extend(available_temporal)
    else:
        temporal_scaler = None

    # 4. Year feature
    if "year_norm" in df.columns:
        feature_parts.append(df["year_norm"].fillna(0.5).astype(float).values.reshape(-1, 1))
        feature_names.append("year_norm")

    # 5. Location columns (one-hot)
    loc_cols = sorted([c for c in df.columns if c.startswith("loc_")])
    if loc_cols:
        loc_arr = df[loc_cols].fillna(0).astype(float).values
        feature_parts.append(loc_arr)
        feature_names.extend(loc_cols)

    # 6. Season-location interactions
    interaction_names: list[str] = []
    if loc_cols:
        interaction_parts: list[np.ndarray] = []
        for lc in loc_cols:
            loc_vec = df[lc].fillna(0).astype(float).values.reshape(-1, 1)
            interaction_parts.append(loc_vec * month_sin_vals)
            interaction_names.append(f"{lc}_month_sin")
            interaction_parts.append(loc_vec * month_cos_vals)
            interaction_names.append(f"{lc}_month_cos")
        if interaction_parts:
            feature_parts.append(np.hstack(interaction_parts))
            feature_names.extend(interaction_names)

    # 7. Product columns (normalised with StandardScaler)
    prod_cols = sorted([c for c in df.columns if c.startswith("prod_") and not c.startswith("prod_scaler")])
    if prod_cols:
        prod_arr = df[prod_cols].fillna(0).astype(float).values
        prod_scaler = StandardScaler()
        prod_arr = prod_scaler.fit_transform(prod_arr)
        feature_parts.append(prod_arr)
        feature_names.extend(prod_cols)
    else:
        prod_scaler = None

    X = np.hstack(feature_parts).astype(np.float32)

    # Build config for inference-time preprocessing
    config: dict[str, Any] = {
        "feature_names": feature_names,
        "loc_cols": loc_cols,
        "prod_cols": prod_cols,
        "interaction_cols": interaction_names,
        "model_type": "product_predictor",
        "target_names": next_prod_cols,
        "target_means": target_scaler.mean_.tolist(),
        "target_stds": safe_stds.tolist(),
        "output_dim": len(next_prod_cols),
    }
    if temporal_scaler is not None:
        config["temporal_cols"] = available_temporal
        config["temporal_scaler_mean"] = temporal_scaler.mean_.tolist()
        config["temporal_scaler_scale"] = temporal_scaler.scale_.tolist()
    if prod_scaler is not None:
        config["prod_scaler_mean"] = prod_scaler.mean_.tolist()
        config["prod_scaler_scale"] = prod_scaler.scale_.tolist()

    return X, Y_raw, Y_norm, feature_names, next_prod_cols, config


def _build_product_features_from_config(
    df: pd.DataFrame,
    config: dict,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Build feature matrix X and raw target Y using STORED scaler parameters.

    Returns (X, Y_raw).  X is None if features cannot be built.
    """
    next_prod_cols = config.get("target_names", [])
    if not next_prod_cols:
        return None, None

    available_targets = [c for c in next_prod_cols if c in df.columns]
    if not available_targets:
        return None, None

    # Drop rows where next order has no products
    mask = df[available_targets].sum(axis=1) > 0
    df = df[mask].copy()
    if df.empty:
        return None, None

    Y_raw = df[available_targets].fillna(0).astype(np.float32).values

    feature_parts: list[np.ndarray] = []

    # 1. Cyclical date encoding
    day_vals = df["orderDay"].fillna(15).astype(float).values
    month_vals = df["orderMonth"].fillna(6).astype(float).values
    month_sin_vals = np.sin(2 * np.pi * month_vals / 12).reshape(-1, 1)
    month_cos_vals = np.cos(2 * np.pi * month_vals / 12).reshape(-1, 1)
    feature_parts.append(np.sin(2 * np.pi * day_vals / 31).reshape(-1, 1))
    feature_parts.append(np.cos(2 * np.pi * day_vals / 31).reshape(-1, 1))
    feature_parts.append(month_sin_vals)
    feature_parts.append(month_cos_vals)

    # 2. Order size
    if "order_size" in df.columns:
        feature_parts.append(df["order_size"].fillna(0.5).astype(float).values.reshape(-1, 1))

    # 3. Temporal features (stored scaler)
    temporal_cols = config.get("temporal_cols", [])
    available_temporal = [c for c in temporal_cols if c in df.columns]
    if available_temporal and "temporal_scaler_mean" in config:
        temporal_arr = df[available_temporal].fillna(0).astype(float).values
        stored_mean = np.array(config["temporal_scaler_mean"])
        stored_scale = np.array(config["temporal_scaler_scale"])
        if len(stored_mean) == len(available_temporal):
            temporal_arr = (temporal_arr - stored_mean) / np.where(stored_scale < 1e-8, 1.0, stored_scale)
            feature_parts.append(temporal_arr)

    # 4. Year feature
    if "year_norm" in config.get("feature_names", []) and "year_norm" in df.columns:
        feature_parts.append(df["year_norm"].fillna(0.5).astype(float).values.reshape(-1, 1))

    # 5. Location columns
    loc_cols = config.get("loc_cols", [])
    for lc in loc_cols:
        if lc in df.columns:
            feature_parts.append(df[lc].fillna(0).astype(float).values.reshape(-1, 1))
        else:
            feature_parts.append(np.zeros((len(df), 1), dtype=np.float32))

    # 6. Season-location interactions
    if loc_cols:
        interaction_parts: list[np.ndarray] = []
        for lc in loc_cols:
            loc_vec = df[lc].fillna(0).astype(float).values.reshape(-1, 1) if lc in df.columns else np.zeros((len(df), 1), dtype=np.float32)
            interaction_parts.append(loc_vec * month_sin_vals)
            interaction_parts.append(loc_vec * month_cos_vals)
        if interaction_parts:
            feature_parts.append(np.hstack(interaction_parts))

    # 7. Product columns (stored scaler)
    prod_cols = config.get("prod_cols", [])
    if prod_cols and "prod_scaler_mean" in config:
        prod_arr_parts = []
        for pc in prod_cols:
            if pc in df.columns:
                prod_arr_parts.append(df[pc].fillna(0).astype(float).values.reshape(-1, 1))
            else:
                prod_arr_parts.append(np.zeros((len(df), 1), dtype=np.float32))
        prod_arr = np.hstack(prod_arr_parts)
        stored_mean = np.array(config["prod_scaler_mean"])
        stored_scale = np.array(config["prod_scaler_scale"])
        if len(stored_mean) == prod_arr.shape[1]:
            prod_arr = (prod_arr - stored_mean) / np.where(stored_scale < 1e-8, 1.0, stored_scale)
        feature_parts.append(prod_arr)

    X = np.hstack(feature_parts).astype(np.float32)
    return X, Y_raw


class ProductTrainingService(BaseTrainingService):

    def _create_job(self, job_id: str) -> ProductTrainingResponse:
        return ProductTrainingResponse(job_id=job_id, status=TrainingStatus.STARTED)

    # ── Multi-variant training loop ────────────────────────────────

    def _run_training(self, job_id: str, request: TrainingRequest) -> None:
        job = self._jobs[job_id]
        job.status = TrainingStatus.RUNNING

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            variant_results: dict[str, ProductVariantResult] = {}

            for variant in VARIANT_NAMES:
                logger.info("=== Training product variant: %s ===", variant)
                try:
                    vr = self._train_product_variant(variant, request, timestamp)
                    variant_results[variant] = vr
                except Exception as ve:
                    logger.exception("Product variant '%s' failed", variant)
                    variant_results[variant] = ProductVariantResult(
                        variant=variant, error=str(ve),
                    )

            job.variant_results = variant_results

            # Surface partial failures so the frontend can show a warning
            failed = [v for v, r in variant_results.items() if r.error]
            if failed:
                job.error = f"Partial failure: product variant(s) {', '.join(failed)} failed"
                logger.warning("Product training completed with partial failures: %s", failed)
            else:
                logger.info("All %d product variants trained successfully", len(VARIANT_NAMES))

            job.status = TrainingStatus.COMPLETED

        except Exception as exc:
            logger.exception("Product training failed")
            job.status = TrainingStatus.FAILED
            job.error = str(exc)

    # ── Single-variant training ────────────────────────────────────

    def _train_product_variant(
        self, variant: str, request: TrainingRequest, timestamp: str,
    ) -> ProductVariantResult:
        import torch
        import torch.nn as nn
        from torch.utils.data import TensorDataset, DataLoader
        from models.product_predictor import ProductPredictor

        # ── Load & prepare data ──────────────────────────────
        df = _load_product_matrix(variant)
        X, Y_raw, Y_norm, feature_names, target_names, config = _prepare_product_dataset(df)

        n_products = Y_raw.shape[1]

        logger.info(
            "[product/%s] Training data: %d samples, %d features, %d target products",
            variant, X.shape[0], X.shape[1], n_products,
        )

        # ── Load training hyperparams from AppSettings ───────
        from services.settings_service import get as _get_settings
        _cfg = _get_settings().training

        # ── Train/val split ──────────────────────────────────
        n_samples = len(X)
        indices = np.arange(n_samples)
        rng = np.random.default_rng(seed=42)
        rng.shuffle(indices)

        split_idx = int(n_samples * _cfg.trainValSplit)
        train_idx = indices[:split_idx]
        val_idx = indices[split_idx:]

        X_train, X_val = X[train_idx], X[val_idx]
        Y_train_norm, Y_val_norm = Y_norm[train_idx], Y_norm[val_idx]
        Y_train_raw, Y_val_raw = Y_raw[train_idx], Y_raw[val_idx]

        # Recency weights
        all_weights = np.linspace(
            _cfg.recencyWeightMin, _cfg.recencyWeightMax, n_samples,
        ).astype(np.float32)
        sample_weights = all_weights[train_idx]

        X_train_t = torch.tensor(X_train, dtype=torch.float32)
        Y_train_t = torch.tensor(Y_train_norm, dtype=torch.float32)
        w_train_t = torch.tensor(sample_weights, dtype=torch.float32)
        X_val_t = torch.tensor(X_val, dtype=torch.float32)
        Y_val_t = torch.tensor(Y_val_norm, dtype=torch.float32)

        train_ds = TensorDataset(X_train_t, Y_train_t, w_train_t)
        train_loader = DataLoader(train_ds, batch_size=request.batch_size, shuffle=True)

        # ── Build model ──────────────────────────────────────
        predictor = ProductPredictor(input_dim=X.shape[1], output_dim=n_products)
        model = predictor.build()

        optimizer = torch.optim.Adam(
            model.parameters(), lr=_cfg.learningRate, weight_decay=_cfg.weightDecay,
        )
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min",
            patience=_cfg.lrSchedulerPatience,
            factor=_cfg.lrSchedulerFactor,
        )
        val_criterion = nn.L1Loss()

        # ── Train with early stopping ────────────────────────
        best_val_loss = float("inf")
        best_state = None
        patience = _cfg.earlyStoppingPatience
        patience_counter = 0
        best_epoch = 0

        for epoch in range(1, request.epochs + 1):
            model.train()
            for xb, yb, wb in train_loader:
                optimizer.zero_grad()
                preds = model(xb)  # [batch, n_products]
                # Weighted L1 loss: broadcast weights [batch,1] across products
                loss = (torch.abs(preds - yb) * wb.unsqueeze(1)).mean()
                loss.backward()
                optimizer.step()

            model.eval()
            with torch.no_grad():
                val_preds_t = model(X_val_t)
                val_loss = val_criterion(val_preds_t, Y_val_t).item()

            scheduler.step(val_loss)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
                best_epoch = epoch
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info("[product/%s] Early stopping at epoch %d", variant, epoch)
                    break

        if best_state is not None:
            model.load_state_dict(best_state)

        # ── Save model ───────────────────────────────────────
        settings.model_dir.mkdir(parents=True, exist_ok=True)
        model_name = f"product_predictor_{variant}"
        config["input_dim"] = X.shape[1]

        torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}.pt"))
        (settings.model_dir / f"{model_name}_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8",
        )
        torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}_{timestamp}.pt"))
        (settings.model_dir / f"{model_name}_{timestamp}_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8",
        )

        logger.info("[product/%s] Saved model: %s", variant, model_name)

        # ── Evaluate (denormalize predictions back to quantities) ──
        target_means = np.array(config["target_means"])
        target_stds = np.array(config["target_stds"])

        model.eval()
        with torch.no_grad():
            train_preds_norm = model(X_train_t).numpy()
            val_preds_norm = model(X_val_t).numpy()

        train_preds = train_preds_norm * target_stds + target_means
        val_preds = val_preds_norm * target_stds + target_means

        # Per-product MAE, then average across products
        t_mae = float(np.mean([
            mean_absolute_error(Y_train_raw[:, i], train_preds[:, i])
            for i in range(n_products)
        ]))
        v_mae = float(np.mean([
            mean_absolute_error(Y_val_raw[:, i], val_preds[:, i])
            for i in range(n_products)
        ]))
        v_rmse = float(np.mean([
            np.sqrt(mean_squared_error(Y_val_raw[:, i], val_preds[:, i]))
            for i in range(n_products)
        ]))

        # Overall R2 (flattened)
        v_r2 = float(r2_score(Y_val_raw.flatten(), val_preds.flatten()))

        logger.info(
            "[product/%s] Epoch %d | Train MAE=%.2f | Val MAE=%.2f, RMSE=%.2f, R2=%.4f",
            variant, best_epoch, t_mae, v_mae, v_rmse, v_r2,
        )

        # ── Post-validation retraining on ALL data ────────────
        not_underfitted = v_r2 > _cfg.minR2ForRetraining
        not_overfitted = t_mae > 0 and (v_mae / t_mae) < _cfg.maxValTrainMaeRatio
        if not_underfitted and not_overfitted:
            logger.info(
                "[product/%s] Post-validation retraining on all %d samples",
                variant, n_samples,
            )
            X_full_t = torch.tensor(X, dtype=torch.float32)
            Y_full_t = torch.tensor(Y_norm, dtype=torch.float32)
            w_full = torch.tensor(all_weights, dtype=torch.float32)

            full_ds = TensorDataset(X_full_t, Y_full_t, w_full)
            full_loader = DataLoader(full_ds, batch_size=request.batch_size, shuffle=True)

            final_optimizer = torch.optim.Adam(
                model.parameters(), lr=_cfg.finalLearningRate, weight_decay=_cfg.weightDecay,
            )
            final_epochs = max(best_epoch // 2, 3)

            model.train()
            for ep in range(1, final_epochs + 1):
                for xb, yb, wb in full_loader:
                    final_optimizer.zero_grad()
                    preds = model(xb)
                    loss = (torch.abs(preds - yb) * wb.unsqueeze(1)).mean()
                    loss.backward()
                    final_optimizer.step()

            logger.info("[product/%s] Post-validation retraining done (%d epochs)", variant, final_epochs)

            torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}.pt"))
            torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}_{timestamp}.pt"))
        else:
            logger.info(
                "[product/%s] Skipping post-validation retraining (R2=%.4f, MAE ratio=%.2f)",
                variant, v_r2, v_mae / max(t_mae, 0.01),
            )

        # ── Run predictions ──────────────────────────────────
        pred_count = 0
        pred_file = None
        try:
            pred_count, pred_file = self._run_product_predictions(
                variant, timestamp, config,
            )
        except Exception as pe:
            logger.warning("[product/%s] Predictions failed: %s", variant, pe)

        return ProductVariantResult(
            variant=variant,
            train_mae=round(t_mae, 4),
            val_mae=round(v_mae, 4),
            val_rmse=round(v_rmse, 4),
            val_r2=round(v_r2, 4),
            epoch=best_epoch,
            samples_total=int(len(X)),
            samples_train=int(len(X_train)),
            samples_val=int(len(X_val)),
            num_features=int(X.shape[1]),
            num_products=n_products,
            predictions_count=pred_count,
            predictions_file=pred_file,
        )

    # ── Predictions for a single variant ───────────────────────────

    def _run_product_predictions(
        self, variant: str, timestamp: str, config: dict,
    ) -> tuple[int, str | None]:
        """Return (count, versioned_file_name)."""
        from services.inference_service import InferenceService
        from services.cache_service import inflow_cache

        cache_key = f"latest_franchise_product_orders_{variant}"
        cached = inflow_cache.get(cache_key)
        if cached is None or not cached.get("data"):
            latest_path = (
                settings.cache_dir / f"latest_franchise_product_orders_{variant}" / "latest.parquet"
            )
            if not latest_path.exists():
                logger.info("[product/%s] No latest data; skipping predictions", variant)
                return 0, None
            latest_df = pd.read_parquet(latest_path)
        else:
            latest_df = pd.DataFrame(cached["data"])

        if latest_df.empty:
            return 0, None

        model_name = f"product_predictor_{variant}"
        svc = InferenceService()
        svc.clear_model(model_name)

        loc_cols = [c for c in latest_df.columns if c.startswith("loc_")]
        prod_cols = [c for c in latest_df.columns if c.startswith("prod_") and not c.startswith("prod_scaler")]

        predictions: list[dict] = []
        for row in latest_df.to_dict(orient="records"):
            input_row: dict = {
                "orderDay": row.get("orderDay"),
                "orderMonth": row.get("orderMonth"),
                "order_size": row.get("order_size", 0.5),
                "days_since_last": row.get("days_since_last", 0),
                "avg_gap": row.get("avg_gap", 0),
                "order_count": row.get("order_count", 1),
                "prev_gap": row.get("prev_gap", 0),
                "gap_trend": row.get("gap_trend", 1),
            }
            if "year_norm" in row:
                input_row["year_norm"] = row.get("year_norm", 0.5)
            for lc in loc_cols:
                input_row[lc] = row.get(lc, 0)
            for pc in prod_cols:
                input_row[pc] = row.get(pc, 0)

            product_preds = svc.predict_next_products(input_row, model_name=model_name)

            # Round to integers and keep only positive predictions
            predicted_products = {}
            for name, qty in product_preds.items():
                rounded = max(round(qty), 0)
                if rounded > 0:
                    predicted_products[name] = rounded

            try:
                order_date = datetime(
                    int(row["orderYear"]), int(row["orderMonth"]), int(row["orderDay"]),
                )
                order_date_str = order_date.strftime("%Y-%m-%d")
            except (ValueError, TypeError, KeyError):
                order_date_str = None

            city = "unknown"
            for lc in loc_cols:
                if row.get(lc, 0) == 1:
                    city = lc[4:]
                    break

            predictions.append({
                "orderNumber": row.get("orderNumber", ""),
                "contactName": row.get("contactName", ""),
                "city": city,
                "orderDate": order_date_str,
                "predictedProducts": predicted_products,
            })

        predictions.sort(key=lambda p: p.get("orderDate") or "9999")

        _PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        versioned_file = _PREDICTIONS_DIR / f"predicted_next_products_{variant}_{timestamp}.json"
        versioned_file.write_text(json.dumps(predictions, indent=2), encoding="utf-8")

        pred_cache_key = f"predicted_next_products_{variant}"
        inflow_cache.put(pred_cache_key, predictions, len(predictions))

        logger.info("[product/%s] Predictions: %d rows -> %s", variant, len(predictions), versioned_file.name)

        # Attempt to build combined order+product predictions
        from services.training_service import build_combined_predictions
        build_combined_predictions(variant)

        return len(predictions), versioned_file.name


    # ── Incremental training (fine-tuning) on new orders ──────────

    def incremental_train(self, variant: str, new_matrix_df: pd.DataFrame) -> None:
        """Fine-tune the existing product model with new training data.

        Uses stored scaler parameters and a very low learning rate.
        """
        import torch
        from torch.utils.data import TensorDataset, DataLoader
        from models.product_predictor import ProductPredictor
        from services.inference_service import InferenceService

        model_path = settings.model_dir / f"product_predictor_{variant}.pt"
        config_path = settings.model_dir / f"product_predictor_{variant}_config.json"
        if not model_path.exists() or not config_path.exists():
            logger.info("[product/%s] No existing model; skipping fine-tuning", variant)
            return

        config = json.loads(config_path.read_text(encoding="utf-8"))
        old_input_dim = config.get("input_dim", len(config.get("feature_names", [])))
        output_dim = config.get("output_dim", 0)

        try:
            X, Y_raw = _build_product_features_from_config(new_matrix_df, config)
        except Exception as e:
            logger.warning("[product/%s] Failed to build features: %s", variant, e)
            return

        if X is None or Y_raw is None or X.shape[1] != old_input_dim:
            logger.info("[product/%s] Feature mismatch; skipping fine-tuning", variant)
            return

        if Y_raw.shape[1] != output_dim:
            logger.info("[product/%s] Output dim mismatch; skipping fine-tuning", variant)
            return

        # Normalize targets using stored parameters
        target_means = np.array(config["target_means"])
        target_stds = np.array(config["target_stds"])
        safe_stds = np.where(target_stds < 1e-8, 1.0, target_stds)
        Y_norm = ((Y_raw - target_means) / safe_stds).astype(np.float32)

        # Load existing model
        predictor = ProductPredictor(input_dim=old_input_dim, output_dim=output_dim)
        model = predictor.build()
        model.load_state_dict(torch.load(str(model_path), weights_only=True))

        # Fine-tune: lr=5e-5, 3 epochs
        X_t = torch.tensor(X, dtype=torch.float32)
        Y_t = torch.tensor(Y_norm, dtype=torch.float32)
        weights = torch.tensor(
            np.linspace(0.5, 1.0, len(X)).astype(np.float32),
            dtype=torch.float32,
        )

        ds = TensorDataset(X_t, Y_t, weights)
        loader = DataLoader(ds, batch_size=32, shuffle=True)

        optimizer = torch.optim.Adam(model.parameters(), lr=5e-5, weight_decay=1e-4)
        fine_tune_epochs = 3

        model.train()
        for ep in range(fine_tune_epochs):
            for xb, yb, wb in loader:
                optimizer.zero_grad()
                preds = model(xb)
                loss = (torch.abs(preds - yb) * wb.unsqueeze(1)).mean()
                loss.backward()
                optimizer.step()

        # Quick validation
        model.eval()
        with torch.no_grad():
            all_preds_norm = model(X_t).numpy()
        all_preds = all_preds_norm * safe_stds + target_means
        inc_mae = float(np.mean([
            mean_absolute_error(Y_raw[:, i], all_preds[:, i])
            for i in range(output_dim)
        ]))

        logger.info(
            "[product/%s] Fine-tuning done (%d epochs, lr=5e-5, %d samples, MAE=%.2f)",
            variant, fine_tune_epochs, len(X), inc_mae,
        )

        # Save updated model
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_name = f"product_predictor_{variant}"

        torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}.pt"))
        torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}_{timestamp}.pt"))
        (settings.model_dir / f"{model_name}_{timestamp}_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8",
        )

        # Clear inference cache and re-run predictions
        svc = InferenceService()
        svc.clear_model(model_name)

        try:
            self._run_product_predictions(variant, timestamp, config)
        except Exception as e:
            logger.warning("[product/%s] Predictions after fine-tuning failed: %s", variant, e)


product_training_service = ProductTrainingService()
