from decimal import Decimal

from domain.models.conference import ConferenceDivergence, DivergenceType
from domain.models.invoice import Invoice
from domain.models.purchase_order import PurchaseOrder


class InvoiceChecker:
    PRICE_TOLERANCE = Decimal("0.01")

    def check(
        self,
        order: PurchaseOrder | None,
        invoice: Invoice,
    ) -> list[ConferenceDivergence]:
        if order is None:
            return [
                ConferenceDivergence(
                    type=DivergenceType.ORDER_NOT_FOUND,
                    detail=f"Pedido {invoice.po_number} não encontrado para o cliente {invoice.client_id}",
                )
            ]

        divergences: list[ConferenceDivergence] = []

        if invoice.vendor_tax_id != order.vendor_tax_id:
            # O fluxo continua quando os CNPJs são diferentes para casos em que houve mudança de CNPJ do fornecedor
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

            if abs(invoice_item.unit_price - order_item.unit_price) > self.PRICE_TOLERANCE:
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
