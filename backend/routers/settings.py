from __future__ import annotations

from fastapi import APIRouter

from schemas.settings import AppSettings
import services.settings_service as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def get_settings():
    """Return the current application settings."""
    return settings_service.get()


@router.put("", response_model=AppSettings)
async def update_settings(body: AppSettings):
    """Replace all application settings and persist to disk."""
    return settings_service.save(body)
