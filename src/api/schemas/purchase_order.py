from datetime import date, datetime
from math import ceil
from uuid import UUID

from pydantic import BaseModel


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


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PurchaseOrderListResponse(BaseModel):
    data: list[PurchaseOrderSummary]
    pagination: PaginationMeta


def build_pagination(total: int, page: int, page_size: int) -> PaginationMeta:
    total_pages = ceil(total / page_size) if page_size else 0
    return PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
