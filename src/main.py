from contextlib import asynccontextmanager

from fastapi import FastAPI

from adapters.inbound.api.middleware.logging import LoggingMiddleware
from adapters.inbound.api.routers.health import router as health_router
from infrastructure.logging_config import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    yield


app = FastAPI(
    title="Purchase Order Connector",
    description="Camada de integração entre a plataforma V360 e os sistemas dos clientes.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(LoggingMiddleware)
app.include_router(health_router)
