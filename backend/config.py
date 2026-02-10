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

    # Inflow Inventory API
    inflow_api_url: str = "https://cloudapi.inflowinventory.com"
    inflow_api_key: str = ""
    inflow_company_id: str = ""

    # Model storage
    model_dir: Path = Path(__file__).parent / "saved_models"

    # Training defaults
    default_epochs: int = 10
    default_batch_size: int = 32

    # Dashboard
    recent_orders_limit: int = 50


settings = Settings()
