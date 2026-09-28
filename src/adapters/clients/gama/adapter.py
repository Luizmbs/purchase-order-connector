from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from adapters.clients.base import ClientAdapter, InputFormat, ParseResult
from adapters.clients.registry import ClientAdapterRegistry
from domain.models.purchase_order import OrderStatus, PurchaseOrder, PurchaseOrderItem

STATUS_MAP = {
    1: OrderStatus.OPEN,
    2: OrderStatus.CLOSED,
    3: OrderStatus.BLOCKED,
}


class GamaAdapter(ClientAdapter):
    CLIENT_ID = "gama"
    input_format = InputFormat.JSON

    def parse(self, raw_data: list) -> ParseResult:
        # Agrupa linhas por número de pedido
        rows_by_ped: dict[str, list[dict]] = defaultdict(list)
        for row in raw_data:
            ped = row.get("ped")
            if not ped:
                raise ValueError("Campo 'ped' ausente em linha Gama")
            rows_by_ped[str(ped)].append(row)

        orders = [self._build_order(ped, rows) for ped, rows in rows_by_ped.items()]
        return ParseResult(orders=orders)

    def _build_order(self, ped: str, rows: list[dict]) -> PurchaseOrder:
        # Cabeçalho vem da primeira linha (todos têm os mesmos dados de pedido)
        first = rows[0]

        status_raw = first.get("situacao")
        if status_raw not in STATUS_MAP:
            raise ValueError(f"Situação desconhecida no pedido Gama '{ped}': '{status_raw}'")

        cnpj = first.get("cnpj_fornecedor")
        if not cnpj:
            raise ValueError(f"Campo 'cnpj_fornecedor' ausente no pedido Gama '{ped}'")

        order_id = uuid4()
        items = [self._parse_item(row, order_id, ped) for row in rows]

        return PurchaseOrder(
            id=order_id,
            client_id=self.CLIENT_ID,
            po_number=ped,
            status=STATUS_MAP[status_raw],
            currency="BRL",
            vendor_tax_id=str(cnpj),
            vendor_name=first.get("nome_fornecedor"),
            created_at=self._parse_timestamp(first.get("dt_criacao"), ped),
            loaded_at=datetime.now(timezone.utc),
            items=items,
        )

    def _parse_item(self, row: dict, order_id: object, ped: str) -> PurchaseOrderItem:
        item_num = row.get("item")
        if item_num is None:
            raise ValueError(f"Campo 'item' ausente em linha do pedido Gama '{ped}'")

        material = row.get("cod_mat")
        if not material:
            raise ValueError(f"Campo 'cod_mat' ausente em item {item_num} do pedido Gama '{ped}'")

        fator_conv = Decimal(str(row.get("fator_conv", 1)))
        if fator_conv <= 0:
            raise ValueError(f"'fator_conv' inválido em item {item_num} do pedido Gama '{ped}'")

        qtd_ped = Decimal(str(row.get("qtd_ped", 0)))
        qtd_rec = Decimal(str(row.get("qtd_rec", 0)))
        preco_centavos = Decimal(str(row.get("preco_unit_centavos", 0)))

        # Normaliza para unidades individuais
        quantity_ordered = qtd_ped * fator_conv
        quantity_received = qtd_rec * fator_conv
        # preco_unit_centavos é por unidade de compra (caixa); converte para R$/unidade individual
        unit_price = preco_centavos / Decimal("100") / fator_conv

        return PurchaseOrderItem(
            id=uuid4(),
            purchase_order_id=order_id,
            line=int(item_num),
            material=str(material),
            description=row.get("desc_mat"),
            uom="UN",  # normalizado para unidades individuais
            quantity_ordered=quantity_ordered,
            quantity_received=quantity_received,
            unit_price=unit_price,
            item_created_at=None,
        )

    def _parse_timestamp(self, ts: int | None, ped: str) -> date | None:
        if ts is None:
            return None
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        except (ValueError, OSError):
            raise ValueError(f"Timestamp inválido no pedido Gama '{ped}': '{ts}'")


ClientAdapterRegistry.register("gama", GamaAdapter)
