from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from adapters.clients.base import ClientAdapter, InputFormat, ParseResult
from adapters.clients.registry import ClientAdapterRegistry
from domain.models.purchase_order import OrderStatus, PurchaseOrder, PurchaseOrderItem

STATUS_MAP = {
    "open": OrderStatus.OPEN,
    "closed": OrderStatus.CLOSED,
    "blocked": OrderStatus.BLOCKED,
}


class DeltaAdapter(ClientAdapter):
    CLIENT_ID = "delta"
    input_format = InputFormat.JSON

    def parse(self, raw_data: dict) -> ParseResult:
        order_rows = raw_data.get("orders", [])
        item_rows = raw_data.get("items", [])

        known_po_numbers = {row.get("po_number") for row in order_rows if row.get("po_number")}

        items_by_po: dict[str, list[dict]] = defaultdict(list)
        orphan_rows: dict[str, list[dict]] = defaultdict(list)
        for row in item_rows:
            po_number = row.get("purchase_order")
            if po_number not in known_po_numbers:
                orphan_rows[po_number].append(row)
            else:
                items_by_po[po_number].append(row)

        orders = [self._parse_order(row, items_by_po) for row in order_rows]

        # Parseia itens órfãos com UUID temporário — o service corrige o purchase_order_id
        orphan_items: dict[str, list] = {}
        for po_number, rows in orphan_rows.items():
            temp_order_id = uuid4()
            orphan_items[po_number] = [
                self._parse_item(row, temp_order_id, po_number) for row in rows
            ]

        return ParseResult(orders=orders, orphan_items=orphan_items)

    def _parse_order(self, data: dict, items_by_po: dict) -> PurchaseOrder:
        po_number = data.get("po_number")
        if not po_number:
            raise ValueError("Campo 'po_number' ausente no pedido Delta")

        status_raw = data.get("status")
        if status_raw not in STATUS_MAP:
            raise ValueError(f"Status desconhecido no pedido Delta '{po_number}': '{status_raw}'")

        vendor = data.get("vendor", {})
        if not vendor.get("tax_id"):
            raise ValueError(f"Campo 'vendor.tax_id' ausente no pedido Delta '{po_number}'")

        order_id = uuid4()
        created_at_raw = data.get("created_at")

        items = [
            self._parse_item(row, order_id, po_number)
            for row in items_by_po.get(po_number, [])
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

    def _parse_item(self, data: dict, order_id: object, po_number: str) -> PurchaseOrderItem:
        material = data.get("material")
        if not material:
            raise ValueError(f"Campo 'material' ausente em item do pedido Delta '{po_number}'")
        if "line" not in data:
            raise ValueError(f"Campo 'line' ausente em item do pedido Delta '{po_number}'")
        if "quantity_ordered" not in data:
            raise ValueError(f"Campo 'quantity_ordered' ausente em item linha {data['line']} do pedido Delta '{po_number}'")
        if "unit_price" not in data:
            raise ValueError(f"Campo 'unit_price' ausente em item linha {data['line']} do pedido Delta '{po_number}'")

        item_created_at_raw = data.get("created_at")

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
            item_created_at=date.fromisoformat(item_created_at_raw) if item_created_at_raw else None,
        )


ClientAdapterRegistry.register("delta", DeltaAdapter)
