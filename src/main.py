from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.middleware.logging import LoggingMiddleware
from api.routers.auth import router as auth_router
from api.routers.health import router as health_router
from api.routers.admin_clients import router as admin_clients_router
from api.routers.conferences import router as conferences_router
from api.routers.ingest import router as ingest_router
from api.routers.purchase_orders import router as purchase_orders_router
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
app.include_router(auth_router)
app.include_router(ingest_router)
app.include_router(purchase_orders_router)
app.include_router(conferences_router)
app.include_router(admin_clients_router)
