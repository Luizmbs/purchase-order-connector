from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.persistence.conference_repository import PostgresConferenceRepository
from adapters.persistence.purchase_order_repository import PostgresPurchaseOrderRepository
from domain.services.conference_service import ConferenceService
from domain.services.invoice_checker import InvoiceChecker
from domain.services.purchase_order_service import PurchaseOrderService
from infrastructure.database import get_session


async def get_purchase_order_service(
    session: AsyncSession = Depends(get_session),
) -> PurchaseOrderService:
    return PurchaseOrderService(PostgresPurchaseOrderRepository(session))


async def get_conference_service(
    session: AsyncSession = Depends(get_session),
) -> ConferenceService:
    return ConferenceService(
        order_repo=PostgresPurchaseOrderRepository(session),
        conference_repo=PostgresConferenceRepository(session),
        checker=InvoiceChecker(),
    )
