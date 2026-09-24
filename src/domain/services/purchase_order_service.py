from domain.models.purchase_order import PurchaseOrder
from domain.ports.outbound.purchase_order_repository import OrderFilters, PurchaseOrderRepository


class PurchaseOrderService:
    def __init__(self, repository: PurchaseOrderRepository):
        self._repo = repository

    async def list_orders(
        self,
        filters: OrderFilters,
        page: int,
        page_size: int,
    ) -> tuple[list[PurchaseOrder], int]:
        offset = (page - 1) * page_size
        return await self._repo.find_many(filters, offset, page_size)

    async def get_order(
        self,
        client_id: str,
        po_number: str,
    ) -> PurchaseOrder | None:
        return await self._repo.find_by_client_and_number(client_id, po_number)
