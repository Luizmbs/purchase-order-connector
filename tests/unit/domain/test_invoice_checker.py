from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from domain.models.conference import DivergenceType
from domain.models.invoice import Invoice, InvoiceItem
from domain.models.purchase_order import OrderStatus, PurchaseOrder, PurchaseOrderItem
from domain.services.invoice_checker import InvoiceChecker


def make_item(
    material: str = "MAT-1001",
    line: int = 10,
    quantity_ordered: str = "100",
    quantity_received: str = "60",
    unit_price: str = "45.90",
    order_id=None,
) -> PurchaseOrderItem:
    return PurchaseOrderItem(
        id=uuid4(),
        purchase_order_id=order_id or uuid4(),
        line=line,
        material=material,
        description="Chapa de aço 2mm",
        uom="UN",
        quantity_ordered=Decimal(quantity_ordered),
        quantity_received=Decimal(quantity_received),
        unit_price=Decimal(unit_price),
        item_created_at=None,
    )


@pytest.fixture
def base_order() -> PurchaseOrder:
    order_id = uuid4()
    return PurchaseOrder(
        id=order_id,
        client_id="alfa",
        po_number="PO-001",
        created_at=date(2026, 8, 5),
        status=OrderStatus.OPEN,
        currency="BRL",
        vendor_tax_id="23456789000101",
        vendor_name="Metalúrgica São Jorge S.A.",
        loaded_at=datetime.now(timezone.utc),
        items=[make_item(order_id=order_id)],
    )


@pytest.fixture
def valid_invoice() -> Invoice:
    return Invoice(
        client_id="alfa",
        po_number="PO-001",
        invoice_number="NF-999",
        vendor_tax_id="23456789000101",
        items=[
            InvoiceItem(
                material="MAT-1001",
                quantity=Decimal("40"),
                total_value=Decimal("1836.00"),  # 40 × 45.90
            )
        ],
    )


@pytest.fixture
def checker() -> InvoiceChecker:
    return InvoiceChecker()


# ── Aprovação ─────────────────────────────────────────────────────────────────

def test_valid_invoice_returns_approved(checker, base_order, valid_invoice):
    divergences = checker.check(base_order, valid_invoice)
    assert divergences == []


# ── order_not_found ───────────────────────────────────────────────────────────

def test_order_not_found_returns_divergence(checker, valid_invoice):
    divergences = checker.check(None, valid_invoice)
    assert len(divergences) == 1
    assert divergences[0].type == DivergenceType.ORDER_NOT_FOUND


def test_order_not_found_stops_further_checks(checker, valid_invoice):
    divergences = checker.check(None, valid_invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.ORDER_NOT_FOUND in types
    assert DivergenceType.VENDOR_MISMATCH not in types
    assert DivergenceType.MATERIAL_NOT_FOUND not in types


# ── order_not_open ────────────────────────────────────────────────────────────

def test_order_not_open_closed_returns_divergence(checker, base_order, valid_invoice):
    base_order.status = OrderStatus.CLOSED
    divergences = checker.check(base_order, valid_invoice)
    assert len(divergences) == 1
    assert divergences[0].type == DivergenceType.ORDER_NOT_OPEN
    assert divergences[0].received == "closed"


def test_order_not_open_blocked_returns_divergence(checker, base_order, valid_invoice):
    base_order.status = OrderStatus.BLOCKED
    divergences = checker.check(base_order, valid_invoice)
    assert len(divergences) == 1
    assert divergences[0].type == DivergenceType.ORDER_NOT_OPEN
    assert divergences[0].received == "blocked"


def test_order_not_open_stops_further_checks(checker, base_order, valid_invoice):
    base_order.status = OrderStatus.CLOSED
    divergences = checker.check(base_order, valid_invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.ORDER_NOT_OPEN in types
    assert DivergenceType.VENDOR_MISMATCH not in types
    assert DivergenceType.PRICE_MISMATCH not in types


# ── vendor_mismatch ───────────────────────────────────────────────────────────

def test_vendor_mismatch_wrong_cnpj(checker, base_order, valid_invoice):
    valid_invoice.vendor_tax_id = "99999999000199"
    divergences = checker.check(base_order, valid_invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.VENDOR_MISMATCH in types


def test_vendor_mismatch_correct_cnpj_passes(checker, base_order, valid_invoice):
    divergences = checker.check(base_order, valid_invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.VENDOR_MISMATCH not in types


def test_vendor_mismatch_expected_and_received(checker, base_order, valid_invoice):
    valid_invoice.vendor_tax_id = "99999999000199"
    divergences = checker.check(base_order, valid_invoice)
    vm = next(d for d in divergences if d.type == DivergenceType.VENDOR_MISMATCH)
    assert vm.expected == "23456789000101"
    assert vm.received == "99999999000199"


# ── material_not_found ────────────────────────────────────────────────────────

def test_material_not_found_unknown_code(checker, base_order, valid_invoice):
    valid_invoice.items[0].material = "MAT-XXXX"
    divergences = checker.check(base_order, valid_invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.MATERIAL_NOT_FOUND in types


def test_material_not_found_does_not_block_valid_items(checker, base_order):
    order_id = base_order.id
    base_order.items.append(
        make_item(material="MAT-2002", line=20, order_id=order_id)
    )
    invoice = Invoice(
        client_id="alfa",
        po_number="PO-001",
        vendor_tax_id="23456789000101",
        items=[
            InvoiceItem(material="MAT-XXXX", quantity=Decimal("10"), total_value=Decimal("100")),
            InvoiceItem(material="MAT-2002", quantity=Decimal("10"), total_value=Decimal("459")),
        ],
    )
    divergences = checker.check(base_order, invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.MATERIAL_NOT_FOUND in types
    assert DivergenceType.QUANTITY_EXCEEDED not in types
    assert DivergenceType.PRICE_MISMATCH not in types


# ── quantity_exceeded ─────────────────────────────────────────────────────────

def test_quantity_exceeded_over_pending(checker, base_order, valid_invoice):
    # pending = 100 - 60 = 40; nota envia 999 → excede
    valid_invoice.items[0] = InvoiceItem(
        material="MAT-1001",
        quantity=Decimal("999"),
        total_value=Decimal("45855.10"),
    )
    divergences = checker.check(base_order, valid_invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.QUANTITY_EXCEEDED in types


def test_quantity_exactly_at_pending_passes(checker, base_order, valid_invoice):
    # pending = 40; nota envia exatamente 40
    valid_invoice.items[0] = InvoiceItem(
        material="MAT-1001",
        quantity=Decimal("40"),
        total_value=Decimal("1836.00"),
    )
    divergences = checker.check(base_order, valid_invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.QUANTITY_EXCEEDED not in types


def test_quantity_below_pending_passes(checker, base_order, valid_invoice):
    valid_invoice.items[0] = InvoiceItem(
        material="MAT-1001",
        quantity=Decimal("1"),
        total_value=Decimal("45.90"),
    )
    divergences = checker.check(base_order, valid_invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.QUANTITY_EXCEEDED not in types


def test_quantity_exceeded_skipped_for_missing_material(checker, base_order):
    invoice = Invoice(
        client_id="alfa",
        po_number="PO-001",
        vendor_tax_id="23456789000101",
        items=[
            InvoiceItem(material="MAT-XXXX", quantity=Decimal("9999"), total_value=Decimal("1")),
        ],
    )
    divergences = checker.check(base_order, invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.MATERIAL_NOT_FOUND in types
    assert DivergenceType.QUANTITY_EXCEEDED not in types


# ── price_mismatch ────────────────────────────────────────────────────────────

def test_price_mismatch_different_price(checker, base_order):
    # unit_price do pedido = 45.90; nota = 50.00/1 = 50.00
    invoice = Invoice(
        client_id="alfa",
        po_number="PO-001",
        vendor_tax_id="23456789000101",
        items=[
            InvoiceItem(material="MAT-1001", quantity=Decimal("1"), total_value=Decimal("50.00")),
        ],
    )
    divergences = checker.check(base_order, invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.PRICE_MISMATCH in types


def test_price_within_tolerance_passes(checker, base_order):
    # diferença de exatamente R$0.009 (< 0.01) → aprovado
    # unit_price do pedido = 45.90; total = 1 × 45.909 (diff = 0.009)
    invoice = Invoice(
        client_id="alfa",
        po_number="PO-001",
        vendor_tax_id="23456789000101",
        items=[
            InvoiceItem(
                material="MAT-1001",
                quantity=Decimal("1"),
                total_value=Decimal("45.909"),
            ),
        ],
    )
    divergences = checker.check(base_order, invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.PRICE_MISMATCH not in types


def test_price_exactly_at_tolerance_fails(checker, base_order):
    # diferença de exatamente R$0.01 → rejeitado (>= tolerância)
    invoice = Invoice(
        client_id="alfa",
        po_number="PO-001",
        vendor_tax_id="23456789000101",
        items=[
            InvoiceItem(
                material="MAT-1001",
                quantity=Decimal("1"),
                total_value=Decimal("45.91"),  # diff = 0.01 exato
            ),
        ],
    )
    divergences = checker.check(base_order, invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.PRICE_MISMATCH in types


def test_price_above_tolerance_fails(checker, base_order):
    # diferença de R$0.02 → rejeitado
    invoice = Invoice(
        client_id="alfa",
        po_number="PO-001",
        vendor_tax_id="23456789000101",
        items=[
            InvoiceItem(
                material="MAT-1001",
                quantity=Decimal("1"),
                total_value=Decimal("45.92"),
            ),
        ],
    )
    divergences = checker.check(base_order, invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.PRICE_MISMATCH in types


def test_price_mismatch_skipped_for_missing_material(checker, base_order):
    invoice = Invoice(
        client_id="alfa",
        po_number="PO-001",
        vendor_tax_id="23456789000101",
        items=[
            InvoiceItem(material="MAT-XXXX", quantity=Decimal("1"), total_value=Decimal("999.99")),
        ],
    )
    divergences = checker.check(base_order, invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.MATERIAL_NOT_FOUND in types
    assert DivergenceType.PRICE_MISMATCH not in types


# ── Múltiplas divergências ────────────────────────────────────────────────────

def test_multiple_divergences_all_returned(checker, base_order):
    invoice = Invoice(
        client_id="alfa",
        po_number="PO-001",
        vendor_tax_id="99999999000199",  # CNPJ errado
        items=[
            InvoiceItem(material="MAT-XXXX", quantity=Decimal("10"), total_value=Decimal("100")),  # material errado
        ],
    )
    divergences = checker.check(base_order, invoice)
    types = [d.type for d in divergences]
    assert DivergenceType.VENDOR_MISMATCH in types
    assert DivergenceType.MATERIAL_NOT_FOUND in types
    assert len(divergences) == 2
