from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from adapters.clients.base import ClientAdapter, InputFormat
from adapters.clients.registry import ClientAdapterRegistry
from domain.models.purchase_order import OrderStatus, PurchaseOrder, PurchaseOrderItem

STATUS_MAP = {
    "open": OrderStatus.OPEN,
    "closed": OrderStatus.CLOSED,
    "blocked": OrderStatus.BLOCKED,
}


class AlfaAdapter(ClientAdapter):
    CLIENT_ID = "alfa"
    input_format = InputFormat.JSON

    def parse(self, raw_data: dict) -> list[PurchaseOrder]:
        orders = raw_data.get("purchase_orders", [])
        return [self._parse_order(o) for o in orders]

    def _parse_order(self, data: dict) -> PurchaseOrder:
        po_number = data.get("po_number")
        if not po_number:
            raise ValueError("Campo 'po_number' ausente no pedido Alfa")

        status_raw = data.get("status")
        if status_raw not in STATUS_MAP:
            raise ValueError(f"Status desconhecido no pedido Alfa: '{status_raw}'")

        vendor = data.get("vendor", {})
        if not vendor.get("tax_id"):
            raise ValueError(f"Campo 'vendor.tax_id' ausente no pedido Alfa '{po_number}'")

        order_id = uuid4()
        created_at_raw = data.get("created_at")

        items = [
            self._parse_item(item, order_id)
            for item in data.get("items", [])
        ]

        return PurchaseOrder(
            id=order_id,
            client_id=self.CLIENT_ID,
            po_number=po_number,
            status=STATUS_MAP[status_raw],
            currency=data.get("currency", "BRL"),
            vendor_tax_id=vendor["tax_id"],
            vendor_name=vendor.get("name"),
            created_at=date.fromisoformat(created_at_raw) if created_at_raw else None,
            loaded_at=datetime.now(timezone.utc),
            items=items,
        )

    def _parse_item(self, data: dict, order_id: object) -> PurchaseOrderItem:
        material = data.get("material")
        if not material:
            raise ValueError("Campo 'material' ausente em item Alfa")
        if "line" not in data:
            raise ValueError(f"Campo 'line' ausente em item Alfa (material={material})")
        if "quantity_ordered" not in data:
            raise ValueError(f"Campo 'quantity_ordered' ausente em item Alfa linha {data['line']}")
        if "unit_price" not in data:
            raise ValueError(f"Campo 'unit_price' ausente em item Alfa linha {data['line']}")

        return PurchaseOrderItem(
            id=uuid4(),
            purchase_order_id=order_id,
            line=data["line"],
            material=material,
            description=data.get("description"),
            uom=data.get("uom", "UN"),
            quantity_ordered=Decimal(str(data["quantity_ordered"])),
            quantity_received=Decimal(str(data.get("quantity_received", 0))),
            unit_price=Decimal(str(data["unit_price"])),
            item_created_at=None,
        )


ClientAdapterRegistry.register("alfa", AlfaAdapter)
