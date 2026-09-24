from dataclasses import dataclass
from decimal import Decimal


@dataclass
class InvoiceItem:
    material: str
    quantity: Decimal
    total_value: Decimal

    @property
    def unit_price(self) -> Decimal:
        return self.total_value / self.quantity


@dataclass
class Invoice:
    client_id: str
    po_number: str
    vendor_tax_id: str
    items: list[InvoiceItem]
    invoice_number: str | None = None
