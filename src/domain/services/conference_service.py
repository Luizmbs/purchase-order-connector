from datetime import UTC, datetime
from uuid import uuid4

import structlog

from domain.models.conference import Conference, ConferenceResult
from domain.models.invoice import Invoice
from domain.ports.outbound.conference_repository import ConferenceFilters, ConferenceRepository
from domain.ports.outbound.purchase_order_repository import PurchaseOrderRepository
from domain.services.invoice_checker import InvoiceChecker

log = structlog.get_logger()


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
        log.info(
            "conference.start",
            client_id=invoice.client_id,
            po_number=invoice.po_number,
            invoice_number=invoice.invoice_number,
            items_count=len(invoice.items),
        )

        order, _ = await self._order_repo.find_by_client_and_number(
            invoice.client_id, invoice.po_number
        )

        divergences = self._checker.check(order, invoice)
        result = ConferenceResult.APPROVED if not divergences else ConferenceResult.REJECTED

        conference = Conference(
            id=uuid4(),
            purchase_order_id=order.id if order else None,
            client_id=invoice.client_id,
            po_number=invoice.po_number,
            invoice_number=invoice.invoice_number,
            vendor_tax_id=invoice.vendor_tax_id,
            result=result,
            checked_at=datetime.now(UTC),
            divergences=divergences,
        )

        await self._conference_repo.save(conference)

        divergence_types = [d.type.value for d in divergences]
        if result == ConferenceResult.APPROVED:
            log.info(
                "conference.approved",
                client_id=invoice.client_id,
                po_number=invoice.po_number,
                invoice_number=invoice.invoice_number,
            )
        else:
            log.warning(
                "conference.rejected",
                client_id=invoice.client_id,
                po_number=invoice.po_number,
                invoice_number=invoice.invoice_number,
                divergences_count=len(divergences),
                divergence_types=divergence_types,
            )

        return conference

    async def list_conferences(
        self,
        filters: ConferenceFilters,
        cursor: str | None,
        page_size: int,
    ) -> tuple[list[Conference], str | None]:
        conferences, next_cursor = await self._conference_repo.find_many(filters, cursor, page_size)
        log.info(
            "conference.list",
            count=len(conferences),
            has_next=next_cursor is not None,
            has_prev=cursor is not None,
            page_size=page_size,
            filter_result=filters.result,
            filter_client_id=filters.client_id,
        )
        return conferences, next_cursor
