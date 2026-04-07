from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import BackgroundTasks
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

from config import settings, VARIANT_NAMES
from schemas.training import TrainingRequest, TrainingResponse, TrainingStatus, VariantResult
from services.base_training_service import BaseTrainingService

logger = logging.getLogger(__name__)

_PREDICTIONS_DIR: Path = settings.cache_dir / "predictions"


def _load_variant_matrix(variant: str) -> pd.DataFrame:
    """Load the order matrix for a specific data variant."""
    path = settings.cache_dir / f"franchise_order_matrix_{variant}" / "matrix.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Variant '{variant}' matrix not found at {path}. "
            "Fetch order data first so the matrix is built."
        )
    return pd.read_parquet(path)


def build_combined_predictions(variant: str) -> int:
    """Merge order-date and product predictions into a single cached DataFrame.

    Reads both prediction caches, joins on orderNumber, and stores the result
    as ``predicted_orderdate_with_products_{variant}``.  Returns the number of
    combined rows, or 0 if either side is missing.
    """
    from services.cache_service import inflow_cache

    order_cache_key = f"predicted_next_order_date_{variant}"
    product_cache_key = f"predicted_next_products_{variant}"

    order_data = inflow_cache.get(order_cache_key)
    product_data = inflow_cache.get(product_cache_key)

    if order_data is None or product_data is None:
        logger.info(
            "build_combined_predictions(%s): skipping — order=%s, product=%s",
            variant,
            "present" if order_data else "missing",
            "present" if product_data else "missing",
        )
        return 0

    order_rows: list[dict] = order_data.get("data") or []
    product_rows: list[dict] = product_data.get("data") or []

    if not order_rows or not product_rows:
        return 0

    # Index product predictions by orderNumber for fast lookup
    product_by_order: dict[str, dict] = {}
    for pr in product_rows:
        on = pr.get("orderNumber", "")
        if on:
            product_by_order[on] = pr

    combined: list[dict] = []
    for row in order_rows:
        on = row.get("orderNumber", "")
        merged = {
            "orderNumber": on,
            "contactName": row.get("contactName", ""),
            "customerName": row.get("customerName", ""),
            "city": row.get("city", ""),
            "orderDate": row.get("orderDate"),
            "predictedDaysToNext": row.get("predictedDaysToNext"),
            "predictedNextOrderDate": row.get("predictedNextOrderDate"),
            "predictedEarliestDate": row.get("predictedEarliestDate"),
            "predictedLatestDate": row.get("predictedLatestDate"),
            "predictedProducts": product_by_order.get(on, {}).get("predictedProducts", {}),
        }
        combined.append(merged)

    # Sort by predicted next order date
    combined.sort(key=lambda r: r.get("predictedNextOrderDate") or "9999")

    # Save versioned JSON
    _PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    versioned = _PREDICTIONS_DIR / f"predicted_orderdate_with_products_{variant}_{timestamp}.json"
    versioned.write_text(json.dumps(combined, indent=2), encoding="utf-8")

    # Cache
    cache_key = f"predicted_orderdate_with_products_{variant}"
    inflow_cache.put(cache_key, combined, len(combined))

    logger.info(
        "build_combined_predictions(%s): %d rows -> %s",
        variant, len(combined), versioned.name,
    )
    return len(combined)


def _prepare_dataset(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str], dict]:
    """Build feature matrix X and target vector y from the order matrix DataFrame.

    Returns (X, y, feature_names, preprocessing_config).
    """
    # ── Compute target: days until next order ────────────────────
    required = ["orderDay", "orderMonth", "orderYear",
                "nextOrderDay", "nextOrderMonth", "nextOrderYear"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    # Drop rows without a next order
    mask = df["nextOrderDay"].notna() & df["nextOrderMonth"].notna() & df["nextOrderYear"].notna()
    df = df[mask].copy()

    if df.empty:
        raise ValueError("No rows with next-order dates available for training")

    def _to_date(row: dict, prefix: str) -> datetime | None:
        try:
            return datetime(
                int(row[f"{prefix}Year"]),
                int(row[f"{prefix}Month"]),
                int(row[f"{prefix}Day"]),
            )
        except (ValueError, TypeError):
            return None

    records = df.to_dict(orient="records")
    days_list: list[float] = []
    valid_indices: list[int] = []

    for i, row in enumerate(records):
        order_date = _to_date(row, "order")
        next_date = _to_date(row, "nextOrder")
        if order_date and next_date:
            delta = (next_date - order_date).days
            if delta > 0:
                days_list.append(float(delta))
                valid_indices.append(i)

    if not days_list:
        raise ValueError("Could not compute any valid days-until-next-order targets")

    df = df.iloc[valid_indices].reset_index(drop=True)
    y = np.array(days_list, dtype=np.float32)

    # ── Target normalization ──────────────────────────────────────
    y_mean = float(np.mean(y))
    y_std = float(np.std(y))
    if y_std < 1e-8:
        y_std = 1.0
    y_normalized = ((y - y_mean) / y_std).astype(np.float32)

    # ── Build features ───────────────────────────────────────────
    feature_parts: list[np.ndarray] = []
    feature_names: list[str] = []

    # 1. Cyclical date encoding (day and month)
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

    # 2. Order size (already 0.0-1.0, kept as-is)
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

    # 4. Year feature (if present in this variant's data)
    if "year_norm" in df.columns:
        feature_parts.append(df["year_norm"].fillna(0.5).astype(float).values.reshape(-1, 1))
        feature_names.append("year_norm")

    # 5. Location columns (one-hot, kept as-is)
    loc_cols = sorted([c for c in df.columns if c.startswith("loc_")])
    if loc_cols:
        loc_arr = df[loc_cols].fillna(0).astype(float).values
        feature_parts.append(loc_arr)
        feature_names.extend(loc_cols)

    # 6. Season-location interaction features
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
    prod_cols = sorted([c for c in df.columns if c.startswith("prod_")])
    if prod_cols:
        prod_arr = df[prod_cols].fillna(0).astype(float).values
        scaler = StandardScaler()
        prod_arr = scaler.fit_transform(prod_arr)
        feature_parts.append(prod_arr)
        feature_names.extend(prod_cols)
    else:
        scaler = None

    X = np.hstack(feature_parts).astype(np.float32)

    # Build config for inference-time preprocessing
    config: dict[str, Any] = {
        "feature_names": feature_names,
        "loc_cols": loc_cols,
        "prod_cols": prod_cols,
        "interaction_cols": interaction_names,
        "target_mean": y_mean,
        "target_std": y_std,
    }
    if temporal_scaler is not None:
        config["temporal_cols"] = available_temporal
        config["temporal_scaler_mean"] = temporal_scaler.mean_.tolist()
        config["temporal_scaler_scale"] = temporal_scaler.scale_.tolist()
    if scaler is not None:
        config["prod_scaler_mean"] = scaler.mean_.tolist()
        config["prod_scaler_scale"] = scaler.scale_.tolist()

    return X, y, y_normalized, feature_names, config


def _build_features_from_config(
    df: pd.DataFrame,
    config: dict,
) -> tuple[np.ndarray | None, np.ndarray]:
    """Build feature matrix X and raw target y using STORED scaler parameters.

    Unlike ``_prepare_dataset`` which fits new scalers, this function applies
    the scaler parameters already saved in *config* so that new data is
    projected into the same feature space the model was trained on.

    Returns (X, y_raw).  X is None if the DataFrame is empty or features
    cannot be built.
    """
    required = ["orderDay", "orderMonth", "orderYear",
                "nextOrderDay", "nextOrderMonth", "nextOrderYear"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    mask = df["nextOrderDay"].notna() & df["nextOrderMonth"].notna() & df["nextOrderYear"].notna()
    df = df[mask].copy()

    if df.empty:
        return None, np.array([], dtype=np.float32)

    # Compute target: days until next order
    records = df.to_dict(orient="records")
    days_list: list[float] = []
    valid_indices: list[int] = []

    for i, row in enumerate(records):
        try:
            order_date = datetime(int(row["orderYear"]), int(row["orderMonth"]), int(row["orderDay"]))
            next_date = datetime(int(row["nextOrderYear"]), int(row["nextOrderMonth"]), int(row["nextOrderDay"]))
            delta = (next_date - order_date).days
            if delta > 0:
                days_list.append(float(delta))
                valid_indices.append(i)
        except (ValueError, TypeError):
            continue

    if not days_list:
        return None, np.array([], dtype=np.float32)

    df = df.iloc[valid_indices].reset_index(drop=True)
    y_raw = np.array(days_list, dtype=np.float32)

    # Build features using stored config
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

    # 3. Temporal features (use STORED scaler params)
    temporal_cols = config.get("temporal_cols", [])
    available_temporal = [c for c in temporal_cols if c in df.columns]
    if available_temporal and "temporal_scaler_mean" in config:
        temporal_arr = df[available_temporal].fillna(0).astype(float).values
        stored_mean = np.array(config["temporal_scaler_mean"])
        stored_scale = np.array(config["temporal_scaler_scale"])
        # Match lengths (in case some columns are missing)
        if len(stored_mean) == len(available_temporal):
            temporal_arr = (temporal_arr - stored_mean) / np.where(stored_scale < 1e-8, 1.0, stored_scale)
            feature_parts.append(temporal_arr)
        else:
            # Fallback: zero-fill
            feature_parts.append(np.zeros((len(df), len(temporal_cols)), dtype=np.float32))

    # 4. Year feature
    if "year_norm" in config.get("feature_names", []) and "year_norm" in df.columns:
        feature_parts.append(df["year_norm"].fillna(0.5).astype(float).values.reshape(-1, 1))

    # 5. Location columns (one-hot, using stored column list)
    loc_cols = config.get("loc_cols", [])
    for lc in loc_cols:
        if lc in df.columns:
            feature_parts.append(df[lc].fillna(0).astype(float).values.reshape(-1, 1))
        else:
            feature_parts.append(np.zeros((len(df), 1), dtype=np.float32))

    # 6. Season-location interactions
    interaction_cols = config.get("interaction_cols", [])
    if interaction_cols and loc_cols:
        interaction_parts: list[np.ndarray] = []
        for lc in loc_cols:
            if lc in df.columns:
                loc_vec = df[lc].fillna(0).astype(float).values.reshape(-1, 1)
            else:
                loc_vec = np.zeros((len(df), 1), dtype=np.float32)
            interaction_parts.append(loc_vec * month_sin_vals)
            interaction_parts.append(loc_vec * month_cos_vals)
        if interaction_parts:
            feature_parts.append(np.hstack(interaction_parts))

    # 7. Product columns (use STORED scaler params)
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
    return X, y_raw


class TrainingService(BaseTrainingService):

    def _create_job(self, job_id: str) -> TrainingResponse:
        return TrainingResponse(job_id=job_id, status=TrainingStatus.STARTED)

    # ── Multi-variant training loop ────────────────────────────────

    def _run_training(self, job_id: str, request: TrainingRequest) -> None:
        job = self._jobs[job_id]
        job.status = TrainingStatus.RUNNING

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            variant_results: dict[str, VariantResult] = {}

            for variant in VARIANT_NAMES:
                logger.info("=== Training variant: %s ===", variant)
                try:
                    vr = self._train_variant(variant, request, timestamp)
                    variant_results[variant] = vr
                except Exception as ve:
                    logger.exception("Variant '%s' failed", variant)
                    variant_results[variant] = VariantResult(
                        variant=variant, error=str(ve),
                    )

            # Populate top-level job fields from the base variant
            base = variant_results.get("base")
            if base and not base.error:
                job.epoch = base.epoch
                job.train_mae = base.train_mae
                job.val_mae = base.val_mae
                job.val_rmse = base.val_rmse
                job.val_r2 = base.val_r2
                job.accuracy = base.accuracy
                job.samples_total = base.samples_total
                job.samples_train = base.samples_train
                job.samples_val = base.samples_val
                job.num_features = base.num_features
                job.num_locations = base.num_locations
                job.num_products = base.num_products
                job.predictions_count = base.predictions_count
                job.predictions_file = base.predictions_file
                job.loss = base.train_mae
                job.val_loss = base.val_mae
                job.mae = base.val_mae

            job.variant_results = variant_results
            failed = [v for v, vr in variant_results.items() if vr.error]
            if failed:
                job.error = f"Partial failure: variant(s) {', '.join(failed)} failed"
                logger.warning("Training completed with partial failures: %s", failed)
            else:
                logger.info("All %d variants trained successfully", len(VARIANT_NAMES))
            job.status = TrainingStatus.COMPLETED

        except Exception as exc:
            logger.exception("Training failed")
            job.status = TrainingStatus.FAILED
            job.error = str(exc)

    # ── Single-variant training ────────────────────────────────────

    def _train_variant(
        self, variant: str, request: TrainingRequest, timestamp: str,
    ) -> VariantResult:
        import torch
        import torch.nn as nn
        from torch.utils.data import TensorDataset, DataLoader
        from models.order_predictor import OrderPredictor

        # ── Load & prepare data ──────────────────────────────
        df = _load_variant_matrix(variant)
        X, y_raw, y_norm, feature_names, config = _prepare_dataset(df)
        y_mean = config["target_mean"]
        y_std = config["target_std"]

        logger.info(
            "[%s] Training data: %d samples, %d features, target range [%.0f, %.0f] days",
            variant, X.shape[0], X.shape[1], y_raw.min(), y_raw.max(),
        )

        # ── Train/val split (random 80/20, sampling from throughout the dataset) ──
        n_samples = len(X)
        indices = np.arange(n_samples)
        rng = np.random.default_rng(seed=42)
        rng.shuffle(indices)

        import services.settings_service as _ss
        _cfg = _ss.get().training

        split_idx = int(n_samples * _cfg.trainValSplit)
        train_idx = indices[:split_idx]
        val_idx = indices[split_idx:]

        X_train, X_val = X[train_idx], X[val_idx]
        y_train_norm, y_val_norm = y_norm[train_idx], y_norm[val_idx]
        y_train_raw, y_val_raw = y_raw[train_idx], y_raw[val_idx]

        # Recency weights based on original position
        all_weights = np.linspace(
            _cfg.recencyWeightMin, _cfg.recencyWeightMax, n_samples
        ).astype(np.float32)
        sample_weights = all_weights[train_idx]

        X_train_t = torch.tensor(X_train, dtype=torch.float32)
        y_train_t = torch.tensor(y_train_norm, dtype=torch.float32)
        w_train_t = torch.tensor(sample_weights, dtype=torch.float32)
        X_val_t = torch.tensor(X_val, dtype=torch.float32)
        y_val_t = torch.tensor(y_val_norm, dtype=torch.float32)

        train_ds = TensorDataset(X_train_t, y_train_t, w_train_t)
        train_loader = DataLoader(train_ds, batch_size=request.batch_size, shuffle=True)

        # ── Build model ──────────────────────────────────────
        predictor = OrderPredictor(input_dim=X.shape[1])
        model = predictor.build()

        optimizer = torch.optim.Adam(
            model.parameters(), lr=_cfg.learningRate, weight_decay=_cfg.weightDecay
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
                preds = model(xb)
                loss = (torch.abs(preds - yb) * wb).mean()
                loss.backward()
                optimizer.step()

            model.eval()
            with torch.no_grad():
                val_preds_t = model(X_val_t)
                val_loss = val_criterion(val_preds_t, y_val_t).item()

            scheduler.step(val_loss)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.clone() for k, v in model.state_dict().items()}
                best_epoch = epoch
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info("[%s] Early stopping at epoch %d", variant, epoch)
                    break

        if best_state is not None:
            model.load_state_dict(best_state)

        # ── Save model (variant-named + versioned) ───────────
        settings.model_dir.mkdir(parents=True, exist_ok=True)
        model_name = f"order_predictor_{variant}"
        config["input_dim"] = X.shape[1]

        # Canonical copy for this variant
        torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}.pt"))
        (settings.model_dir / f"{model_name}_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8",
        )
        # Versioned copy
        torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}_{timestamp}.pt"))
        (settings.model_dir / f"{model_name}_{timestamp}_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8",
        )
        # Base variant also saves to canonical "order_predictor" for compat
        if variant == "base":
            torch.save(model.state_dict(), str(settings.model_dir / "order_predictor.pt"))
            (settings.model_dir / "order_predictor_config.json").write_text(
                json.dumps(config, indent=2), encoding="utf-8",
            )

        logger.info("[%s] Saved model: %s", variant, model_name)

        # ── Evaluate (denormalize predictions back to days) ──
        model.eval()
        with torch.no_grad():
            train_preds_norm = model(X_train_t).numpy().flatten()
            val_preds_norm = model(X_val_t).numpy().flatten()

        train_preds = train_preds_norm * y_std + y_mean
        val_preds = val_preds_norm * y_std + y_mean

        t_mae = float(mean_absolute_error(y_train_raw, train_preds))
        v_mae = float(mean_absolute_error(y_val_raw, val_preds))
        v_mse = float(mean_squared_error(y_val_raw, val_preds))
        v_r2 = float(r2_score(y_val_raw, val_preds))

        tolerance = _cfg.predictionTolerance
        within_tol = np.abs(val_preds - y_val_raw) <= tolerance
        accuracy = float(np.mean(within_tol) * 100)

        logger.info(
            "[%s] Epoch %d | Train MAE=%.2f | Val MAE=%.2f, RMSE=%.2f, R2=%.4f, Acc=%.1f%%",
            variant, best_epoch, t_mae, v_mae, np.sqrt(v_mse), v_r2, accuracy,
        )

        # ── Post-validation retraining on ALL data ────────────
        # If the model passed validation (not over/underfitted), retrain
        # on the full dataset so it learns from every available pattern.
        not_underfitted = v_r2 > _cfg.minR2ForRetraining and accuracy > _cfg.minAccuracyForRetraining
        not_overfitted = t_mae > 0 and (v_mae / t_mae) < _cfg.maxValTrainMaeRatio
        if not_underfitted and not_overfitted:
            logger.info(
                "[%s] Post-validation retraining on all %d samples (validated OK: R2=%.4f, Acc=%.1f%%)",
                variant, n_samples, v_r2, accuracy,
            )
            # Use full dataset with recency weights
            X_full_t = torch.tensor(X, dtype=torch.float32)
            y_full_t = torch.tensor(y_norm, dtype=torch.float32)
            w_full = torch.tensor(all_weights, dtype=torch.float32)

            full_ds = TensorDataset(X_full_t, y_full_t, w_full)
            full_loader = DataLoader(full_ds, batch_size=request.batch_size, shuffle=True)

            # Lower learning rate for final pass
            final_optimizer = torch.optim.Adam(
                model.parameters(), lr=_cfg.finalLearningRate, weight_decay=_cfg.weightDecay
            )
            final_epochs = max(best_epoch // 2, 3)

            model.train()
            for ep in range(1, final_epochs + 1):
                for xb, yb, wb in full_loader:
                    final_optimizer.zero_grad()
                    preds = model(xb)
                    loss = (torch.abs(preds - yb) * wb).mean()
                    loss.backward()
                    final_optimizer.step()

            logger.info("[%s] Post-validation retraining done (%d epochs on full data)", variant, final_epochs)

            # Save the final model (overwrite the validated copy)
            torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}.pt"))
            torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}_{timestamp}.pt"))
            if variant == "base":
                torch.save(model.state_dict(), str(settings.model_dir / "order_predictor.pt"))
        else:
            logger.info(
                "[%s] Skipping post-validation retraining (R2=%.4f, Acc=%.1f%%, train/val MAE ratio=%.2f)",
                variant, v_r2, accuracy, v_mae / max(t_mae, 0.01),
            )

        # ── Run predictions ──────────────────────────────────
        pred_count = 0
        pred_file = None
        try:
            pred_count, pred_file = self._run_predictions(
                variant, timestamp, config,
                val_mae=v_mae, val_rmse=float(np.sqrt(v_mse)),
            )
        except Exception as pe:
            logger.warning("[%s] Predictions failed: %s", variant, pe)

        return VariantResult(
            variant=variant,
            train_mae=round(t_mae, 4),
            val_mae=round(v_mae, 4),
            val_rmse=round(float(np.sqrt(v_mse)), 4),
            val_r2=round(v_r2, 4),
            accuracy=round(accuracy, 2),
            epoch=best_epoch,
            samples_total=int(len(X)),
            samples_train=int(len(X_train)),
            samples_val=int(len(X_val)),
            num_features=int(X.shape[1]),
            num_locations=len([c for c in feature_names if c.startswith("loc_")]),
            num_products=len([c for c in feature_names if c.startswith("prod_")]),
            predictions_count=pred_count,
            predictions_file=pred_file,
        )

    # ── Predictions for a single variant ───────────────────────────

    def _run_predictions(
        self, variant: str, timestamp: str, config: dict,
        val_mae: float = 0.0, val_rmse: float = 0.0,
    ) -> tuple[int, str | None]:
        """Return (count, versioned_file_name)."""
        from services.inference_service import InferenceService
        from services.cache_service import inflow_cache

        # Read latest franchise orders from the live cache
        cache_key = f"latest_franchise_orders_{variant}"
        cached = inflow_cache.get(cache_key)
        if cached is None or not cached.get("data"):
            # Fall back to parquet file if cache is empty
            latest_path = (
                settings.cache_dir / f"latest_franchise_orders_{variant}" / "latest.parquet"
            )
            if not latest_path.exists():
                logger.info("[%s] No latest data in cache or on disk; skipping predictions", variant)
                return 0, None
            latest_df = pd.read_parquet(latest_path)
        else:
            latest_df = pd.DataFrame(cached["data"])

        if latest_df.empty:
            return 0, None

        model_name = f"order_predictor_{variant}"
        svc = InferenceService()
        svc.clear_model(model_name)

        loc_cols = [c for c in latest_df.columns if c.startswith("loc_")]
        prod_cols = [c for c in latest_df.columns if c.startswith("prod_")]

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

            predicted_days = svc.predict_next_order(input_row, model_name=model_name)
            predicted_days = max(round(predicted_days, 1), 0)

            try:
                order_date = datetime(
                    int(row["orderYear"]), int(row["orderMonth"]), int(row["orderDay"]),
                )
                predicted_date = order_date + timedelta(days=round(predicted_days))
                predicted_date_str = predicted_date.strftime("%Y-%m-%d")
                order_date_str = order_date.strftime("%Y-%m-%d")

                # Compute date range using MAE (average error) and RMSE (worst-case)
                earliest_days = max(0, predicted_days - val_mae)
                latest_days = predicted_days + val_mae
                earliest_date = order_date + timedelta(days=round(earliest_days))
                latest_date = order_date + timedelta(days=round(latest_days))
                earliest_date_str = earliest_date.strftime("%Y-%m-%d")
                latest_date_str = latest_date.strftime("%Y-%m-%d")
            except (ValueError, TypeError, KeyError):
                predicted_date_str = None
                order_date_str = None
                earliest_date_str = None
                latest_date_str = None

            city = "unknown"
            for lc in loc_cols:
                if row.get(lc, 0) == 1:
                    city = lc[4:]
                    break

            # Build customer name from city slug: "fremont_ca" -> "Qamaria - Fremont, Ca"
            if city and city != "unknown":
                customer_name = "Qamaria - " + city.replace("_", " ").title()
            else:
                customer_name = ""

            predictions.append({
                "orderNumber": row.get("orderNumber", ""),
                "contactName": row.get("contactName", ""),
                "customerName": customer_name,
                "city": city,
                "orderDate": order_date_str,
                "predictedDaysToNext": predicted_days,
                "predictedNextOrderDate": predicted_date_str,
                "predictedEarliestDate": earliest_date_str,
                "predictedLatestDate": latest_date_str,
            })

        predictions.sort(key=lambda p: p.get("predictedNextOrderDate") or "9999")

        _PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        versioned_file = _PREDICTIONS_DIR / f"predicted_next_order_date_{variant}_{timestamp}.json"
        versioned_file.write_text(json.dumps(predictions, indent=2), encoding="utf-8")

        cache_key = f"predicted_next_order_date_{variant}"
        inflow_cache.put(cache_key, predictions, len(predictions))
        if variant == "base":
            inflow_cache.put("predicted_next_order_date", predictions, len(predictions))

        logger.info("[%s] Predictions: %d rows -> %s", variant, len(predictions), versioned_file.name)

        # Attempt to build combined order+product predictions
        build_combined_predictions(variant)

        # Refresh today's predicted orders for this variant
        from services.todays_orders_service import build_todays_predicted_orders
        build_todays_predicted_orders(variant)

        return len(predictions), versioned_file.name

    # ── Incremental training (fine-tuning) on new orders ──────────

    def incremental_train(self, variant: str, new_matrix_df: pd.DataFrame) -> None:
        """Fine-tune the existing model with new training data.

        Called automatically when the order matrix is updated and new completed
        orders are detected.  Uses stored scaler parameters from the existing
        config (no re-fitting) and a very low learning rate to prevent
        catastrophic forgetting.
        """
        import torch
        from torch.utils.data import TensorDataset, DataLoader
        from models.order_predictor import OrderPredictor
        from services.inference_service import InferenceService

        model_path = settings.model_dir / f"order_predictor_{variant}.pt"
        config_path = settings.model_dir / f"order_predictor_{variant}_config.json"
        if not model_path.exists() or not config_path.exists():
            logger.info("[%s] No existing model found; skipping fine-tuning", variant)
            return

        # Load existing config with stored scaler parameters
        config = json.loads(config_path.read_text(encoding="utf-8"))
        old_input_dim = config.get("input_dim", len(config.get("feature_names", [])))

        # Build features using STORED scaler params (no re-fitting)
        try:
            X, y_raw = _build_features_from_config(new_matrix_df, config)
        except Exception as e:
            logger.warning("[%s] Failed to build features from config: %s", variant, e)
            return

        if X is None or X.shape[1] != old_input_dim:
            saved_names = config.get("feature_names", [])
            logger.warning(
                "[%s] Feature dimension mismatch (new=%s, saved=%d, saved_features=%d); "
                "skipping fine-tuning — full retrain required to pick up new features",
                variant,
                X.shape[1] if X is not None else "None",
                old_input_dim,
                len(saved_names),
            )
            return

        # Normalize targets using stored parameters
        y_mean = config["target_mean"]
        y_std = config["target_std"]
        y_norm = ((y_raw - y_mean) / y_std).astype(np.float32)

        # Load existing model
        predictor = OrderPredictor(input_dim=old_input_dim)
        model = predictor.build()
        model.load_state_dict(torch.load(str(model_path), weights_only=True))

        # Fine-tune with very low learning rate (5e-5) to prevent catastrophic forgetting
        X_t = torch.tensor(X, dtype=torch.float32)
        y_t = torch.tensor(y_norm, dtype=torch.float32)
        weights = torch.tensor(
            np.linspace(0.5, 1.0, len(X)).astype(np.float32),
            dtype=torch.float32,
        )

        ds = TensorDataset(X_t, y_t, weights)
        loader = DataLoader(ds, batch_size=32, shuffle=True)

        optimizer = torch.optim.Adam(model.parameters(), lr=5e-5, weight_decay=1e-4)
        fine_tune_epochs = 3

        model.train()
        for ep in range(fine_tune_epochs):
            epoch_loss = 0.0
            batches = 0
            for xb, yb, wb in loader:
                optimizer.zero_grad()
                preds = model(xb)
                loss = (torch.abs(preds - yb) * wb).mean()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                batches += 1

        # Quick validation
        model.eval()
        with torch.no_grad():
            all_preds_norm = model(X_t).numpy().flatten()
        all_preds = all_preds_norm * y_std + y_mean
        inc_mae = float(mean_absolute_error(y_raw, all_preds))

        logger.info(
            "[%s] Fine-tuning done (%d epochs, lr=5e-5, %d samples, MAE=%.2f)",
            variant, fine_tune_epochs, len(X), inc_mae,
        )

        # Save updated model (same config — scalers unchanged)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_name = f"order_predictor_{variant}"

        torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}.pt"))
        torch.save(model.state_dict(), str(settings.model_dir / f"{model_name}_{timestamp}.pt"))
        (settings.model_dir / f"{model_name}_{timestamp}_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8",
        )
        if variant == "base":
            torch.save(model.state_dict(), str(settings.model_dir / "order_predictor.pt"))

        # Clear inference cache and re-run predictions
        svc = InferenceService()
        svc.clear_model(model_name)

        try:
            self._run_predictions(variant, timestamp, config, val_mae=inc_mae, val_rmse=inc_mae * 1.2)
        except Exception as e:
            logger.warning("[%s] Predictions after fine-tuning failed: %s", variant, e)


def refresh_all_predictions() -> dict[str, int]:
    """Re-run order predictions for all variants using the existing trained models.

    Does not retrain — only runs inference on the current
    ``latest_franchise_orders_{variant}`` data and refreshes the combined
    and today's-orders caches.  Called by the daily 5pm ET background task.

    Returns a dict mapping variant name → number of predictions generated.
    """
    svc = training_service  # use the module-level singleton; avoids creating an extra instance
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results: dict[str, int] = {}
    for variant in VARIANT_NAMES:
        try:
            count, _ = svc._run_predictions(variant, timestamp, {})
            results[variant] = count
        except Exception:
            logger.exception("refresh_all_predictions: variant '%s' failed", variant)
            results[variant] = 0
    return results


# Module-level singleton for incremental training calls
training_service = TrainingService()
