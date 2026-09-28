import structlog

from domain.models.purchase_order import PurchaseOrder
from domain.ports.outbound.purchase_order_repository import OrderFilters, PurchaseOrderRepository

log = structlog.get_logger()


class PurchaseOrderService:
    def __init__(self, repository: PurchaseOrderRepository):
        self._repo = repository

    async def list_orders(
        self,
        filters: OrderFilters,
        cursor: str | None,
        page_size: int,
    ) -> tuple[list[PurchaseOrder], str | None]:
        orders, next_cursor = await self._repo.find_many(filters, cursor, page_size)
        log.info(
            "order.list",
            count=len(orders),
            has_next=next_cursor is not None,
            has_prev=cursor is not None,
            page_size=page_size,
            filter_client_id=filters.client_id,
            filter_status=filters.status,
            filter_vendor_tax_id=filters.vendor_tax_id,
            filter_has_pending=filters.has_pending,
        )
        return orders, next_cursor

    async def get_order(
        self,
        client_id: str,
        po_number: str,
    ) -> tuple[PurchaseOrder | None, bool]:
        order, from_cache = await self._repo.find_by_client_and_number(client_id, po_number)

        if order:
            log.info(
                "order.get",
                client_id=client_id,
                po_number=po_number,
                from_cache=from_cache,
            )
        else:
            log.warning(
                "order.not_found",
                client_id=client_id,
                po_number=po_number,
            )

        return order, from_cache
