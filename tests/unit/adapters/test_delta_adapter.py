from datetime import date
from decimal import Decimal

import pytest

from adapters.clients.delta.adapter import DeltaAdapter
from adapters.clients.base import ParseResult
from domain.models.purchase_order import OrderStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def adapter() -> DeltaAdapter:
    return DeltaAdapter()


def order_row(
    po_number: str = "DL-2026-0044",
    created_at: str = "2026-09-02",
    status: str = "open",
    currency: str = "BRL",
    tax_id: str = "67890123000145",
    vendor_name: str = "Embalagens Norte Sul Ltda",
) -> dict:
    return {
        "po_number": po_number,
        "created_at": created_at,
        "status": status,
        "currency": currency,
        "vendor": {"tax_id": tax_id, "name": vendor_name},
    }


def item_row(
    purchase_order: str = "DL-2026-0044",
    created_at: str = "2026-09-02",
    line: int = 10,
    material: str = "EMB-500",
    description: str = "Caixa papelão 40x30",
    uom: str = "UN",
    quantity_ordered: int = 800,
    quantity_received: int = 300,
    unit_price: float = 3.75,
) -> dict:
    return {
        "purchase_order": purchase_order,
        "created_at": created_at,
        "line": line,
        "material": material,
        "description": description,
        "uom": uom,
        "quantity_ordered": quantity_ordered,
        "quantity_received": quantity_received,
        "unit_price": unit_price,
    }


def make_payload(orders=None, items=None) -> dict:
    return {
        "orders": orders or [],
        "items": items or [],
    }


# ── ParseResult ───────────────────────────────────────────────────────────────

def test_parse_returns_parse_result(adapter):
    result = adapter.parse(make_payload([order_row()], [item_row()]))
    assert isinstance(result, ParseResult)


def test_parse_no_warnings_when_all_items_match(adapter):
    result = adapter.parse(make_payload([order_row()], [item_row()]))
    assert result.warnings == []


# ── Join orders + items ───────────────────────────────────────────────────────

def test_item_attached_to_correct_order(adapter):
    result = adapter.parse(make_payload([order_row()], [item_row()]))
    assert len(result.orders) == 1
    assert len(result.orders[0].items) == 1


def test_two_items_same_order(adapter):
    items = [item_row(line=10), item_row(line=20, material="EMB-720")]
    result = adapter.parse(make_payload([order_row()], items))
    assert len(result.orders[0].items) == 2


def test_two_orders_items_distributed_correctly(adapter):
    orders = [order_row("DL-001"), order_row("DL-002")]
    items = [
        item_row(purchase_order="DL-001", line=10),
        item_row(purchase_order="DL-002", line=10),
        item_row(purchase_order="DL-002", line=20),
    ]
    result = adapter.parse(make_payload(orders, items))
    by_po = {o.po_number: o for o in result.orders}
    assert len(by_po["DL-001"].items) == 1
    assert len(by_po["DL-002"].items) == 2


def test_order_without_items_is_kept(adapter):
    # Pedido sem itens é um estado válido
    result = adapter.parse(make_payload([order_row()], []))
    assert len(result.orders) == 1
    assert result.orders[0].items == []


def test_empty_payload_returns_empty(adapter):
    result = adapter.parse(make_payload([], []))
    assert result.orders == []
    assert result.orphan_items == {}


# ── Itens órfãos ──────────────────────────────────────────────────────────────

def test_orphan_item_goes_to_orphan_items_not_warnings(adapter):
    orphan = item_row(purchase_order="DL-INEXISTENTE")
    result = adapter.parse(make_payload([order_row()], [orphan]))
    assert "DL-INEXISTENTE" in result.orphan_items
    assert result.warnings == []


def test_orphan_item_not_attached_to_any_order(adapter):
    orphan = item_row(purchase_order="DL-INEXISTENTE")
    result = adapter.parse(make_payload([order_row()], [orphan]))
    assert all(len(o.items) == 0 for o in result.orders)


def test_multiple_orphan_items_grouped_by_po_number(adapter):
    orphans = [
        item_row(purchase_order="DL-X", line=10),
        item_row(purchase_order="DL-X", line=20),
        item_row(purchase_order="DL-Y", line=10),
    ]
    result = adapter.parse(make_payload([order_row()], orphans))
    assert len(result.orphan_items["DL-X"]) == 2
    assert len(result.orphan_items["DL-Y"]) == 1


def test_valid_and_orphan_items_coexist(adapter):
    valid_item = item_row(purchase_order="DL-2026-0044", line=10)
    orphan = item_row(purchase_order="DL-INEXISTENTE", line=10)
    result = adapter.parse(make_payload([order_row()], [valid_item, orphan]))
    assert len(result.orders[0].items) == 1
    assert "DL-INEXISTENTE" in result.orphan_items


# ── item_created_at ───────────────────────────────────────────────────────────

def test_item_created_at_populated_from_item_row(adapter):
    item = item_row(created_at="2026-09-08")
    result = adapter.parse(make_payload([order_row()], [item]))
    assert result.orders[0].items[0].item_created_at == date(2026, 9, 8)


def test_item_created_at_can_differ_from_order_created_at(adapter):
    # Item criado depois do cabeçalho do pedido
    item = item_row(created_at="2026-09-15")
    result = adapter.parse(make_payload([order_row(created_at="2026-09-02")], [item]))
    assert result.orders[0].created_at == date(2026, 9, 2)
    assert result.orders[0].items[0].item_created_at == date(2026, 9, 15)


# ── Normalização de campos ────────────────────────────────────────────────────

def test_order_created_at_parsed_as_date(adapter):
    result = adapter.parse(make_payload([order_row(created_at="2026-09-02")], []))
    assert result.orders[0].created_at == date(2026, 9, 2)


def test_quantities_as_decimal(adapter):
    result = adapter.parse(make_payload([order_row()], [item_row()]))
    item = result.orders[0].items[0]
    assert item.quantity_ordered == Decimal("800")
    assert item.quantity_received == Decimal("300")


def test_unit_price_as_decimal(adapter):
    result = adapter.parse(make_payload([order_row()], [item_row()]))
    assert result.orders[0].items[0].unit_price == Decimal("3.75")


def test_vendor_tax_id_preserved(adapter):
    result = adapter.parse(make_payload([order_row(tax_id="67890123000145")], []))
    assert result.orders[0].vendor_tax_id == "67890123000145"


def test_client_id_is_delta(adapter):
    orders = [order_row("DL-001"), order_row("DL-002")]
    result = adapter.parse(make_payload(orders, []))
    for order in result.orders:
        assert order.client_id == "delta"


# ── Mapeamento de status ──────────────────────────────────────────────────────

def test_status_open_mapped(adapter):
    result = adapter.parse(make_payload([order_row(status="open")], []))
    assert result.orders[0].status == OrderStatus.OPEN


def test_status_closed_mapped(adapter):
    result = adapter.parse(make_payload([order_row(status="closed")], []))
    assert result.orders[0].status == OrderStatus.CLOSED


def test_status_blocked_mapped(adapter):
    result = adapter.parse(make_payload([order_row(status="blocked")], []))
    assert result.orders[0].status == OrderStatus.BLOCKED


# ── Erros ─────────────────────────────────────────────────────────────────────

def test_missing_po_number_raises_value_error(adapter):
    row = {k: v for k, v in order_row().items() if k != "po_number"}
    with pytest.raises(ValueError, match="po_number"):
        adapter.parse(make_payload([row], []))


def test_unknown_status_raises_value_error(adapter):
    with pytest.raises(ValueError, match="Status desconhecido"):
        adapter.parse(make_payload([order_row(status="pendente")], []))


def test_missing_vendor_tax_id_raises_value_error(adapter):
    row = order_row()
    row["vendor"] = {"name": "Sem CNPJ"}
    with pytest.raises(ValueError, match="vendor.tax_id"):
        adapter.parse(make_payload([row], []))


def test_missing_material_in_item_raises_value_error(adapter):
    row = {k: v for k, v in item_row().items() if k != "material"}
    with pytest.raises(ValueError, match="material"):
        adapter.parse(make_payload([order_row()], [row]))


def test_missing_line_in_item_raises_value_error(adapter):
    row = {k: v for k, v in item_row().items() if k != "line"}
    with pytest.raises(ValueError, match="line"):
        adapter.parse(make_payload([order_row()], [row]))
