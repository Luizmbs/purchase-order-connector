from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from api.schemas.purchase_order import PaginationMeta, build_pagination


class InvoiceItemRequest(BaseModel):
    material: str
    quantity: Decimal = Field(gt=0)
    total_value: Decimal = Field(gt=0)


class ConferenceRequest(BaseModel):
    client_id: str
    po_number: str
    invoice_number: str | None = None
    vendor_tax_id: str
    items: list[InvoiceItemRequest] = Field(min_length=1)


class DivergenceResponse(BaseModel):
    type: str
    item_line: int | None
    material: str | None
    expected: str | None
    received: str | None
    detail: str


class ConferenceResponse(BaseModel):
    conference_id: UUID
    result: str
    divergences: list[DivergenceResponse]


class ConferenceSummary(BaseModel):
    id: UUID
    client_id: str
    po_number: str
    invoice_number: str | None
    vendor_tax_id: str
    result: str
    checked_at: datetime
    divergences_count: int
    divergence_types: list[str]


class ConferenceListResponse(BaseModel):
    data: list[ConferenceSummary]
    pagination: PaginationMeta
