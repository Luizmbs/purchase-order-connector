from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID


class OrderStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    BLOCKED = "blocked"


@dataclass
class PurchaseOrderItem:
    id: UUID
    purchase_order_id: UUID
    line: int
    material: str
    uom: str
    quantity_ordered: Decimal
    quantity_received: Decimal
    unit_price: Decimal
    description: str | None = None
    item_created_at: date | None = None

    @property
    def quantity_pending(self) -> Decimal:
        return self.quantity_ordered - self.quantity_received


@dataclass
class PurchaseOrder:
    id: UUID
    client_id: str
    po_number: str
    status: OrderStatus
    currency: str
    vendor_tax_id: str
    loaded_at: datetime
    items: list[PurchaseOrderItem] = field(default_factory=list)
    created_at: date | None = None
    vendor_name: str | None = None

    @property
    def has_pending_items(self) -> bool:
        return any(item.quantity_pending > 0 for item in self.items)
