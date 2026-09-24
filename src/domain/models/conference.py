from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class DivergenceType(str, Enum):
    ORDER_NOT_FOUND = "order_not_found"
    VENDOR_MISMATCH = "vendor_mismatch"
    MATERIAL_NOT_FOUND = "material_not_found"
    QUANTITY_EXCEEDED = "quantity_exceeded"
    PRICE_MISMATCH = "price_mismatch"


class ConferenceResult(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ConferenceDivergence:
    type: DivergenceType
    detail: str
    item_line: int | None = None
    material: str | None = None
    expected: str | None = None
    received: str | None = None


@dataclass
class Conference:
    id: UUID
    client_id: str
    po_number: str
    vendor_tax_id: str
    result: ConferenceResult
    checked_at: datetime
    divergences: list[ConferenceDivergence] = field(default_factory=list)
    purchase_order_id: UUID | None = None
    invoice_number: str | None = None
