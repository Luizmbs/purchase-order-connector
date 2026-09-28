from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.models.purchase_order import OrderStatus, PurchaseOrder, PurchaseOrderItem
from domain.services.ingestion_service import _diff_orders


def make_order(
    status: OrderStatus = OrderStatus.OPEN,
    vendor_tax_id: str = "23456789000101",
    vendor_name: str = "Fornecedor Ltda",
    currency: str = "BRL",
    items: list[PurchaseOrderItem] | None = None,
) -> PurchaseOrder:
    order_id = uuid4()
    return PurchaseOrder(
        id=order_id,
        client_id="alfa",
        po_number="PO-001",
        status=status,
        currency=currency,
        vendor_tax_id=vendor_tax_id,
        vendor_name=vendor_name,
        loaded_at=datetime.now(timezone.utc),
        items=items or [],
    )


def make_item(
    line: int = 10,
    material: str = "MAT-1001",
    quantity_ordered: str = "100",
    quantity_received: str = "60",
    unit_price: str = "45.90",
) -> PurchaseOrderItem:
    return PurchaseOrderItem(
        id=uuid4(),
        purchase_order_id=uuid4(),
        line=line,
        material=material,
        uom="UN",
        quantity_ordered=Decimal(quantity_ordered),
        quantity_received=Decimal(quantity_received),
        unit_price=Decimal(unit_price),
    )


# ── Sem mudanças ──────────────────────────────────────────────────────────────

def test_identical_orders_return_no_changes():
    item = make_item()
    order = make_order(items=[item])
    assert _diff_orders(order, order) == []


def test_identical_header_no_items_returns_no_changes():
    order = make_order()
    assert _diff_orders(order, order) == []


# ── Mudanças no cabeçalho ─────────────────────────────────────────────────────

def test_status_change_detected():
    old = make_order(status=OrderStatus.OPEN)
    new = make_order(status=OrderStatus.CLOSED)
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "status" in fields
    status_change = next(c for c in changes if c.field == "status")
    assert status_change.before == "open"
    assert status_change.after == "closed"


def test_vendor_tax_id_change_detected():
    old = make_order(vendor_tax_id="11111111000111")
    new = make_order(vendor_tax_id="22222222000122")
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "vendor_tax_id" in fields


def test_vendor_name_change_detected():
    old = make_order(vendor_name="Empresa Antiga")
    new = make_order(vendor_name="Empresa Nova")
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "vendor_name" in fields


def test_currency_change_detected():
    old = make_order(currency="BRL")
    new = make_order(currency="USD")
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "currency" in fields


def test_unchanged_header_generates_no_changes():
    order = make_order(
        status=OrderStatus.OPEN,
        vendor_tax_id="23456789000101",
        vendor_name="Fornecedor Ltda",
        currency="BRL",
    )
    changes = _diff_orders(order, order)
    assert changes == []


# ── Mudanças em itens ─────────────────────────────────────────────────────────

def test_quantity_received_change_detected():
    old = make_order(items=[make_item(quantity_received="60")])
    new = make_order(items=[make_item(quantity_received="80")])
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "item.linha_10.quantity_received" in fields
    change = next(c for c in changes if c.field == "item.linha_10.quantity_received")
    assert change.before == "60"
    assert change.after == "80"


def test_quantity_ordered_change_detected():
    old = make_order(items=[make_item(quantity_ordered="100")])
    new = make_order(items=[make_item(quantity_ordered="150")])
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "item.linha_10.quantity_ordered" in fields


def test_unit_price_change_detected():
    old = make_order(items=[make_item(unit_price="45.90")])
    new = make_order(items=[make_item(unit_price="50.00")])
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "item.linha_10.unit_price" in fields


def test_unchanged_item_generates_no_changes():
    item = make_item()
    old = make_order(items=[item])
    new = make_order(items=[make_item()])  # mesmos valores
    assert _diff_orders(old, new) == []


# ── Adição e remoção de itens ─────────────────────────────────────────────────

def test_new_item_detected_as_added():
    old = make_order(items=[make_item(line=10)])
    new = make_order(items=[make_item(line=10), make_item(line=20, material="MAT-2002")])
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "item.linha_20" in fields
    added = next(c for c in changes if c.field == "item.linha_20")
    assert added.before == "ausente"
    assert "MAT-2002" in added.after


def test_removed_item_detected():
    old = make_order(items=[make_item(line=10), make_item(line=20, material="MAT-2002")])
    new = make_order(items=[make_item(line=10)])
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "item.linha_20" in fields
    removed = next(c for c in changes if c.field == "item.linha_20")
    assert removed.after == "removido"
    assert "MAT-2002" in removed.before


# ── Múltiplas mudanças simultâneas ───────────────────────────────────────────

def test_multiple_changes_all_returned():
    old = make_order(
        status=OrderStatus.OPEN,
        items=[make_item(quantity_received="60")],
    )
    new = make_order(
        status=OrderStatus.CLOSED,
        items=[make_item(quantity_received="100")],
    )
    changes = _diff_orders(old, new)
    fields = [c.field for c in changes]
    assert "status" in fields
    assert "item.linha_10.quantity_received" in fields
