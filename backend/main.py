import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import health, training, product_training, inflow
from routers import settings as settings_router
from services.polling_service import (
    run_polling_loop,
    run_daily_product_refresh,
    run_daily_orders_refresh,
    run_daily_predictions_refresh,
    run_stale_products_check,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    poll_task        = asyncio.create_task(run_polling_loop())
    daily_task       = asyncio.create_task(run_daily_product_refresh())
    orders_task      = asyncio.create_task(run_daily_orders_refresh())
    predictions_task = asyncio.create_task(run_daily_predictions_refresh())
    stale_task       = asyncio.create_task(run_stale_products_check())
    yield
    named_tasks = [
        (poll_task,        "run_polling_loop"),
        (daily_task,       "run_daily_product_refresh"),
        (orders_task,      "run_daily_orders_refresh"),
        (predictions_task, "run_daily_predictions_refresh"),
        (stale_task,       "run_stale_products_check"),
    ]
    for task, name in named_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Background task '%s' cancelled on shutdown", name)


app = FastAPI(
    title=settings.app_name,
    docs_url=f"{settings.api_prefix}/docs",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(product_training.router, prefix=settings.api_prefix)
app.include_router(training.router, prefix=settings.api_prefix)
app.include_router(inflow.router, prefix=settings.api_prefix)
app.include_router(settings_router.router, prefix=settings.api_prefix)
