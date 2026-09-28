from decimal import Decimal

import structlog

from domain.models.conference import ConferenceDivergence, DivergenceType
from domain.models.invoice import Invoice
from domain.models.purchase_order import PurchaseOrder

log = structlog.get_logger()


class InvoiceChecker:
    PRICE_TOLERANCE = Decimal("0.01")

    def check(
        self,
        order: PurchaseOrder | None,
        invoice: Invoice,
    ) -> list[ConferenceDivergence]:
        if order is None:
            log.warning(
                "checker.order_not_found",
                client_id=invoice.client_id,
                po_number=invoice.po_number,
            )
            return [
                ConferenceDivergence(
                    type=DivergenceType.ORDER_NOT_FOUND,
                    detail=f"Pedido {invoice.po_number} não encontrado para o cliente {invoice.client_id}",
                )
            ]

        if order.status.value != "open":
            log.warning(
                "checker.order_not_open",
                client_id=invoice.client_id,
                po_number=invoice.po_number,
                status=order.status.value,
            )
            return [
                ConferenceDivergence(
                    type=DivergenceType.ORDER_NOT_OPEN,
                    expected="open",
                    received=order.status.value,
                    detail=f"Pedido {invoice.po_number} não está em aberto (situação atual: {order.status.value})",
                )
            ]

        divergences: list[ConferenceDivergence] = []

        if invoice.vendor_tax_id != order.vendor_tax_id:
            log.warning(
                "checker.vendor_mismatch",
                client_id=invoice.client_id,
                po_number=invoice.po_number,
                expected=order.vendor_tax_id,
                received=invoice.vendor_tax_id,
            )
            divergences.append(
                ConferenceDivergence(
                    type=DivergenceType.VENDOR_MISMATCH,
                    expected=order.vendor_tax_id,
                    received=invoice.vendor_tax_id,
                    detail="CNPJ do fornecedor não corresponde ao pedido",
                )
            )

        order_items_by_material = {item.material: item for item in order.items}

        for invoice_item in invoice.items:
            order_item = order_items_by_material.get(invoice_item.material)

            if order_item is None:
                log.warning(
                    "checker.material_not_found",
                    client_id=invoice.client_id,
                    po_number=invoice.po_number,
                    material=invoice_item.material,
                )
                divergences.append(
                    ConferenceDivergence(
                        type=DivergenceType.MATERIAL_NOT_FOUND,
                        material=invoice_item.material,
                        received=invoice_item.material,
                        detail=f"Material {invoice_item.material} não encontrado no pedido",
                    )
                )
                continue

            if invoice_item.quantity > order_item.quantity_pending:
                log.warning(
                    "checker.quantity_exceeded",
                    client_id=invoice.client_id,
                    po_number=invoice.po_number,
                    material=order_item.material,
                    line=order_item.line,
                    pending=str(order_item.quantity_pending),
                    received=str(invoice_item.quantity),
                )
                divergences.append(
                    ConferenceDivergence(
                        type=DivergenceType.QUANTITY_EXCEEDED,
                        item_line=order_item.line,
                        material=order_item.material,
                        expected=str(order_item.quantity_pending),
                        received=str(invoice_item.quantity),
                        detail=(
                            f"Saldo disponível é {order_item.quantity_pending} {order_item.uom};"
                            f" nota apresenta {invoice_item.quantity}"
                        ),
                    )
                )

            if abs(invoice_item.unit_price - order_item.unit_price) >= self.PRICE_TOLERANCE:
                log.warning(
                    "checker.price_mismatch",
                    client_id=invoice.client_id,
                    po_number=invoice.po_number,
                    material=order_item.material,
                    line=order_item.line,
                    expected=str(order_item.unit_price),
                    received=str(invoice_item.unit_price),
                )
                divergences.append(
                    ConferenceDivergence(
                        type=DivergenceType.PRICE_MISMATCH,
                        item_line=order_item.line,
                        material=order_item.material,
                        expected=str(order_item.unit_price),
                        received=str(invoice_item.unit_price),
                        detail=(
                            f"Preço unitário esperado R$ {order_item.unit_price};"
                            f" nota apresenta R$ {invoice_item.unit_price}"
                        ),
                    )
                )

        return divergences
