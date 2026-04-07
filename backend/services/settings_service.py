from __future__ import annotations

import logging
from pathlib import Path

from schemas.settings import AppSettings

logger = logging.getLogger(__name__)

_SETTINGS_FILE = Path(__file__).parent.parent / "settings.json"

_settings: AppSettings | None = None


def get() -> AppSettings:
    """Return the current settings, loading from disk if needed."""
    global _settings
    if _settings is not None:
        return _settings
    return _load()


def save(new_settings: AppSettings) -> AppSettings:
    """Persist settings to disk and update the in-memory cache."""
    global _settings
    _settings = new_settings
    try:
        _SETTINGS_FILE.write_text(
            new_settings.model_dump_json(indent=2), encoding="utf-8"
        )
        logger.info("Settings saved to %s", _SETTINGS_FILE)
    except Exception:
        logger.exception("Failed to save settings to %s", _SETTINGS_FILE)
    return _settings


def _load() -> AppSettings:
    global _settings
    if _SETTINGS_FILE.exists():
        try:
            data = _SETTINGS_FILE.read_text(encoding="utf-8")
            _settings = AppSettings.model_validate_json(data)
            logger.info("Settings loaded from %s", _SETTINGS_FILE)
            return _settings
        except Exception:
            logger.exception(
                "Failed to parse %s — falling back to defaults", _SETTINGS_FILE
            )
    _settings = AppSettings()
    return _settings
