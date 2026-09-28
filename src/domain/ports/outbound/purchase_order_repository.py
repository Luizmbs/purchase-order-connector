from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.models.purchase_order import OrderStatus, PurchaseOrder


@dataclass
class OrderFilters:
    client_id: str | None = None
    vendor_tax_id: str | None = None
    status: OrderStatus | None = None
    has_pending: bool | None = None


class PurchaseOrderRepository(ABC):
    @abstractmethod
    async def find_many(
        self, filters: OrderFilters, cursor: str | None, limit: int
    ) -> tuple[list[PurchaseOrder], str | None]: ...

    @abstractmethod
    async def find_by_client_and_number(
        self, client_id: str, po_number: str
    ) -> tuple[PurchaseOrder | None, bool]: ...

    @abstractmethod
    async def upsert(self, order: PurchaseOrder) -> None: ...
