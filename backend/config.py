from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "protected_namespaces": ("settings_",)}

    app_name: str = "ML Dashboard API"
    debug: bool = True
    api_prefix: str = "/api"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:4200",
        "http://localhost",
    ]

    # Inflow Inventory API (optional - system works with cached data if not provided)
    inflow_api_url: str = "https://cloudapi.inflowinventory.com"
    inflow_api_key: str = ""
    inflow_company_id: str = ""

    @property
    def has_inflow_credentials(self) -> bool:
        """Check if valid Inflow API credentials are configured."""
        return bool(self.inflow_api_key and self.inflow_company_id)

    # Model storage
    model_dir: Path = Path(__file__).parent / "saved_models"

    # DataFrame cache storage
    cache_dir: Path = Path(__file__).parent / "cached_data"

    # Training defaults
    default_epochs: int = 10
    default_batch_size: int = 32

    # Background polling interval (seconds)
    poll_interval: int = 60

    # Dashboard
    recent_orders_limit: int = 50


settings = Settings()

# Canonical list of the 4 training/prediction data variants.
# Imported by training_service, product_training_service, todays_orders_service,
# and order_matrix_service to avoid four independent copies.
VARIANT_NAMES: list[str] = ["base", "min_orders", "year", "min_orders_year"]
