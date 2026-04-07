from enum import Enum
from pydantic import BaseModel, ConfigDict


class TrainingStatus(str, Enum):
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrainingRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    epochs: int = 10
    batch_size: int = 32
    dataset_name: str | None = None


class VariantResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    variant: str
    train_mae: float | None = None
    val_mae: float | None = None
    val_rmse: float | None = None
    val_r2: float | None = None
    accuracy: float | None = None
    epoch: int | None = None
    samples_total: int | None = None
    samples_train: int | None = None
    samples_val: int | None = None
    num_features: int | None = None
    num_locations: int | None = None
    num_products: int | None = None
    predictions_count: int | None = None
    predictions_file: str | None = None
    error: str | None = None


class TrainingResponse(BaseModel):
    job_id: str
    status: TrainingStatus
    epoch: int | None = None

    # Training metrics
    train_mae: float | None = None
    train_mse: float | None = None
    train_rmse: float | None = None

    # Validation metrics
    val_mae: float | None = None
    val_mse: float | None = None
    val_rmse: float | None = None
    val_r2: float | None = None
    val_mape: float | None = None

    # Legacy / summary
    loss: float | None = None
    val_loss: float | None = None
    mae: float | None = None
    accuracy: float | None = None

    # Dataset info
    samples_total: int | None = None
    samples_train: int | None = None
    samples_val: int | None = None
    num_features: int | None = None
    num_locations: int | None = None
    num_products: int | None = None

    # Target distribution
    target_mean: float | None = None
    target_std: float | None = None
    target_min: float | None = None
    target_max: float | None = None
    target_median: float | None = None

    # Prediction distribution (on validation set)
    pred_mean: float | None = None
    pred_std: float | None = None
    pred_min: float | None = None
    pred_max: float | None = None

    # Predictions run after training
    predictions_count: int | None = None
    predictions_file: str | None = None

    # Per-variant results (multi-model training)
    variant_results: dict[str, VariantResult] | None = None

    error: str | None = None


class ProductVariantResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    variant: str
    train_mae: float | None = None
    val_mae: float | None = None
    val_rmse: float | None = None
    val_r2: float | None = None
    epoch: int | None = None
    samples_total: int | None = None
    samples_train: int | None = None
    samples_val: int | None = None
    num_features: int | None = None
    num_products: int | None = None
    predictions_count: int | None = None
    predictions_file: str | None = None
    error: str | None = None


class ProductTrainingResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    job_id: str
    status: TrainingStatus
    variant_results: dict[str, ProductVariantResult] | None = None
    error: str | None = None
