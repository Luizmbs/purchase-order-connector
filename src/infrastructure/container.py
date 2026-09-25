from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.cache_service import CacheService
from adapters.persistence.conference_repository import PostgresConferenceRepository
from adapters.persistence.purchase_order_repository import PostgresPurchaseOrderRepository
from domain.services.conference_service import ConferenceService
from domain.services.invoice_checker import InvoiceChecker
from domain.services.purchase_order_service import PurchaseOrderService
from infrastructure.database import get_redis, get_session


async def get_purchase_order_service(
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> PurchaseOrderService:
    cache = CacheService(redis)
    return PurchaseOrderService(PostgresPurchaseOrderRepository(session, cache))


async def get_conference_service(
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> ConferenceService:
    cache = CacheService(redis)
    return ConferenceService(
        order_repo=PostgresPurchaseOrderRepository(session, cache),
        conference_repo=PostgresConferenceRepository(session),
        checker=InvoiceChecker(),
    )
