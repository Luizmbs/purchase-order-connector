import csv
import io
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import structlog

from adapters.clients.base import ClientAdapter, InputFormat
from adapters.clients.registry import ClientAdapterRegistry
from domain.models.purchase_order import OrderStatus, PurchaseOrder, PurchaseOrderItem

log = structlog.get_logger()

STATUS_MAP = {
    "EM ABERTO": OrderStatus.OPEN,
    "BLOQUEADO": OrderStatus.BLOCKED,
    "ENCERRADO": OrderStatus.CLOSED,
}


class BetaAdapter(ClientAdapter):
    CLIENT_ID = "beta"
    input_format = InputFormat.MULTIPART

    def parse(self, raw_data: dict) -> list[PurchaseOrder]:
        cabecalho_csv = raw_data.get("cabecalho", "")
        itens_csv = raw_data.get("itens", "")

        headers = list(csv.DictReader(io.StringIO(cabecalho_csv), delimiter=";"))
        item_rows = list(csv.DictReader(io.StringIO(itens_csv), delimiter=";"))

        items_by_po: dict[str, list] = defaultdict(list)
        for row in item_rows:
            po_number = row.get("NUMERO_PEDIDO", "").strip()
            items_by_po[po_number].append(row)

        orders = []
        for row in headers:
            order = self._parse_order(row, items_by_po)
            orders.append(order)

        return orders

    def _parse_order(self, row: dict, items_by_po: dict) -> PurchaseOrder:
        po_number = row.get("NUMERO_PEDIDO", "").strip()
        if not po_number:
            raise ValueError("Campo 'NUMERO_PEDIDO' ausente no cabeçalho Beta")

        status_raw = row.get("SITUACAO", "").strip()
        if status_raw not in STATUS_MAP:
            raise ValueError(f"Status desconhecido no pedido Beta '{po_number}': '{status_raw}'")

        cnpj_raw = row.get("FORNECEDOR_CNPJ", "").strip()
        if not cnpj_raw:
            raise ValueError(f"Campo 'FORNECEDOR_CNPJ' ausente no pedido Beta '{po_number}'")

        emissao_raw = row.get("EMISSAO", "").strip()
        if not emissao_raw:
            raise ValueError(f"Campo 'EMISSAO' ausente no pedido Beta '{po_number}'")

        order_id = uuid4()

        item_rows = items_by_po.get(po_number, [])
        items = []
        for item_row in item_rows:
            item = self._parse_item(item_row, order_id, po_number)
            if item is not None:
                items.append(item)

        return PurchaseOrder(
            id=order_id,
            client_id=self.CLIENT_ID,
            po_number=po_number,
            status=STATUS_MAP[status_raw],
            currency=row.get("MOEDA", "BRL").strip(),
            vendor_tax_id=self._normalize_cnpj(cnpj_raw),
            vendor_name=row.get("FORNECEDOR_RAZAO_SOCIAL", "").strip() or None,
            created_at=self._parse_date(emissao_raw),
            loaded_at=datetime.now(timezone.utc),
            items=items,
        )

    def _parse_item(self, row: dict, order_id: object, po_number: str) -> PurchaseOrderItem | None:
        material = row.get("CODIGO_MATERIAL", "").strip()
        if not material:
            raise ValueError(f"Campo 'CODIGO_MATERIAL' ausente em item do pedido Beta '{po_number}'")

        line_raw = row.get("ITEM", "").strip()
        if not line_raw:
            raise ValueError(f"Campo 'ITEM' ausente em item do pedido Beta '{po_number}'")

        qty_ordered_raw = row.get("QTD_PEDIDA", "").strip()
        if not qty_ordered_raw:
            raise ValueError(f"Campo 'QTD_PEDIDA' ausente em item linha {line_raw} do pedido Beta '{po_number}'")

        price_raw = row.get("PRECO_UNITARIO", "").strip()
        if not price_raw:
            raise ValueError(f"Campo 'PRECO_UNITARIO' ausente em item linha {line_raw} do pedido Beta '{po_number}'")

        return PurchaseOrderItem(
            id=uuid4(),
            purchase_order_id=order_id,
            line=int(line_raw),
            material=material,
            description=row.get("DESCRICAO", "").strip() or None,
            uom=row.get("UNIDADE", "UN").strip(),
            quantity_ordered=self._parse_decimal(qty_ordered_raw),
            quantity_received=self._parse_decimal(row.get("QTD_RECEBIDA", "0").strip() or "0"),
            unit_price=self._parse_decimal(price_raw),
            item_created_at=None,
        )

    def _normalize_cnpj(self, cnpj: str) -> str:
        digits = re.sub(r"\D", "", cnpj)
        if not digits:
            raise ValueError(f"CNPJ inválido: '{cnpj}'")
        return digits

    def _parse_date(self, value: str) -> date:
        try:
            return datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError:
            raise ValueError(f"Data com formato inválido: '{value}' (esperado DD/MM/YYYY)")

    def _parse_decimal(self, value: str) -> Decimal:
        try:
            normalized = value.replace(".", "").replace(",", ".")
            return Decimal(normalized)
        except Exception:
            raise ValueError(f"Número com formato inválido: '{value}'")


ClientAdapterRegistry.register("beta", BetaAdapter)
