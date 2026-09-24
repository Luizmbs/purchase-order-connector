from datetime import UTC, datetime
from uuid import uuid4

from domain.models.conference import Conference, ConferenceResult
from domain.models.invoice import Invoice
from domain.ports.outbound.conference_repository import ConferenceFilters, ConferenceRepository
from domain.ports.outbound.purchase_order_repository import PurchaseOrderRepository
from domain.services.invoice_checker import InvoiceChecker


class ConferenceService:
    def __init__(
        self,
        order_repo: PurchaseOrderRepository,
        conference_repo: ConferenceRepository,
        checker: InvoiceChecker,
    ):
        self._order_repo = order_repo
        self._conference_repo = conference_repo
        self._checker = checker

    async def check_invoice(self, invoice: Invoice) -> Conference:
        order = await self._order_repo.find_by_client_and_number(
            invoice.client_id, invoice.po_number
        )

        divergences = self._checker.check(order, invoice)

        conference = Conference(
            id=uuid4(),
            purchase_order_id=order.id if order else None,
            client_id=invoice.client_id,
            po_number=invoice.po_number,
            invoice_number=invoice.invoice_number,
            vendor_tax_id=invoice.vendor_tax_id,
            result=ConferenceResult.APPROVED if not divergences else ConferenceResult.REJECTED,
            checked_at=datetime.now(UTC),
            divergences=divergences,
        )

        await self._conference_repo.save(conference)
        return conference

    async def list_conferences(
        self,
        filters: ConferenceFilters,
        page: int,
        page_size: int,
    ) -> tuple[list[Conference], int]:
        offset = (page - 1) * page_size
        return await self._conference_repo.find_many(filters, offset, page_size)
