from datetime import date
from decimal import Decimal

import pytest

from adapters.clients.alfa.adapter import AlfaAdapter
from domain.models.purchase_order import OrderStatus


VALID_ORDER = {
    "po_number": "4500001234",
    "created_at": "2026-08-05",
    "status": "open",
    "currency": "BRL",
    "vendor": {"tax_id": "23456789000101", "name": "Metalúrgica São Jorge S.A."},
    "items": [
        {
            "line": 10,
            "material": "MAT-1001",
            "description": "Chapa de aço 2mm",
            "uom": "UN",
            "quantity_ordered": 100,
            "quantity_received": 60,
            "unit_price": 45.9,
        },
        {
            "line": 20,
            "material": "MAT-1002",
            "description": "Perfil U 3m",
            "uom": "UN",
            "quantity_ordered": 50,
            "quantity_received": 0,
            "unit_price": 128.75,
        },
    ],
}


@pytest.fixture
def adapter() -> AlfaAdapter:
    return AlfaAdapter()


# ── Parse correto ─────────────────────────────────────────────────────────────

def test_parse_single_order_with_two_items(adapter):
    orders = adapter.parse({"purchase_orders": [VALID_ORDER]})
    assert len(orders) == 1
    assert len(orders[0].items) == 2


def test_parse_multiple_orders(adapter):
    second = {**VALID_ORDER, "po_number": "4500001235"}
    orders = adapter.parse({"purchase_orders": [VALID_ORDER, second]})
    assert len(orders) == 2


def test_parse_empty_list(adapter):
    orders = adapter.parse({"purchase_orders": []})
    assert orders == []


# ── Normalização de campos ────────────────────────────────────────────────────

def test_created_at_parsed_as_date(adapter):
    orders = adapter.parse({"purchase_orders": [VALID_ORDER]})
    assert orders[0].created_at == date(2026, 8, 5)


def test_quantities_as_decimal(adapter):
    orders = adapter.parse({"purchase_orders": [VALID_ORDER]})
    item = orders[0].items[0]
    assert item.quantity_ordered == Decimal("100")
    assert item.quantity_received == Decimal("60")


def test_unit_price_as_decimal(adapter):
    orders = adapter.parse({"purchase_orders": [VALID_ORDER]})
    item = orders[0].items[0]
    assert item.unit_price == Decimal("45.9")


def test_vendor_tax_id_preserved(adapter):
    orders = adapter.parse({"purchase_orders": [VALID_ORDER]})
    assert orders[0].vendor_tax_id == "23456789000101"


def test_item_created_at_is_none(adapter):
    orders = adapter.parse({"purchase_orders": [VALID_ORDER]})
    for item in orders[0].items:
        assert item.item_created_at is None


# ── Mapeamento de status ──────────────────────────────────────────────────────

def test_status_open_mapped(adapter):
    order = {**VALID_ORDER, "status": "open"}
    orders = adapter.parse({"purchase_orders": [order]})
    assert orders[0].status == OrderStatus.OPEN


def test_status_closed_mapped(adapter):
    order = {**VALID_ORDER, "status": "closed"}
    orders = adapter.parse({"purchase_orders": [order]})
    assert orders[0].status == OrderStatus.CLOSED


def test_status_blocked_mapped(adapter):
    order = {**VALID_ORDER, "status": "blocked"}
    orders = adapter.parse({"purchase_orders": [order]})
    assert orders[0].status == OrderStatus.BLOCKED


# ── Erros ─────────────────────────────────────────────────────────────────────

def test_unknown_status_raises_value_error(adapter):
    order = {**VALID_ORDER, "status": "pending"}
    with pytest.raises(ValueError, match="Status desconhecido"):
        adapter.parse({"purchase_orders": [order]})


def test_missing_po_number_raises_value_error(adapter):
    order = {k: v for k, v in VALID_ORDER.items() if k != "po_number"}
    with pytest.raises(ValueError, match="po_number"):
        adapter.parse({"purchase_orders": [order]})


def test_invalid_date_format_raises_error(adapter):
    order = {**VALID_ORDER, "created_at": "05-08-2026"}
    with pytest.raises((ValueError, Exception)):
        adapter.parse({"purchase_orders": [order]})


def test_missing_line_raises_value_error(adapter):
    item_without_line = {k: v for k, v in VALID_ORDER["items"][0].items() if k != "line"}
    order = {**VALID_ORDER, "items": [item_without_line]}
    with pytest.raises(ValueError, match="line"):
        adapter.parse({"purchase_orders": [order]})


def test_missing_quantity_ordered_raises_value_error(adapter):
    item = {k: v for k, v in VALID_ORDER["items"][0].items() if k != "quantity_ordered"}
    order = {**VALID_ORDER, "items": [item]}
    with pytest.raises(ValueError, match="quantity_ordered"):
        adapter.parse({"purchase_orders": [order]})


def test_missing_unit_price_raises_value_error(adapter):
    item = {k: v for k, v in VALID_ORDER["items"][0].items() if k != "unit_price"}
    order = {**VALID_ORDER, "items": [item]}
    with pytest.raises(ValueError, match="unit_price"):
        adapter.parse({"purchase_orders": [order]})


# ── client_id ─────────────────────────────────────────────────────────────────

def test_client_id_is_alfa(adapter):
    second = {**VALID_ORDER, "po_number": "4500001235"}
    orders = adapter.parse({"purchase_orders": [VALID_ORDER, second]})
    for order in orders:
        assert order.client_id == "alfa"
