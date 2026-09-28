from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PurchaseOrderSummary(BaseModel):
    id: UUID
    client_id: str
    po_number: str
    created_at: date | None
    status: str
    currency: str
    vendor_tax_id: str
    vendor_name: str | None
    loaded_at: datetime
    items_count: int
    has_pending: bool


class CursorPaginationMeta(BaseModel):
    page_size: int
    has_next: bool
    has_prev: bool
    next_cursor: str | None


class PurchaseOrderListResponse(BaseModel):
    data: list[PurchaseOrderSummary]
    pagination: CursorPaginationMeta


class PurchaseOrderItemDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line: int
    material: str
    description: str | None
    uom: str
    quantity_ordered: Decimal
    quantity_received: Decimal
    quantity_pending: Decimal
    unit_price: Decimal
    item_created_at: date | None


class PurchaseOrderDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: str
    po_number: str
    created_at: date | None
    status: str
    currency: str
    vendor_tax_id: str
    vendor_name: str | None
    loaded_at: datetime
    items: list[PurchaseOrderItemDetail]
