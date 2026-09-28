from datetime import date
from decimal import Decimal

import pytest

from adapters.clients.gama.adapter import GamaAdapter
from adapters.clients.base import ParseResult
from domain.models.purchase_order import OrderStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def adapter() -> GamaAdapter:
    return GamaAdapter()


def item_row(
    ped: str = "GL-778",
    item: int = 1,
    cnpj: str = "34567890000112",
    nome: str = "Transportes Ideal ME",
    dt_criacao: int = 1786752000,
    cod_mat: str = "TRP-01",
    desc_mat: str = "Pallet de madeira",
    um: str = "CX",
    fator_conv: int = 12,
    qtd_ped: int = 10,
    qtd_rec: int = 2,
    preco_unit_centavos: int = 120000,
    situacao: int = 1,
) -> dict:
    return {
        "ped": ped,
        "item": item,
        "cnpj_fornecedor": cnpj,
        "nome_fornecedor": nome,
        "dt_criacao": dt_criacao,
        "cod_mat": cod_mat,
        "desc_mat": desc_mat,
        "um": um,
        "fator_conv": fator_conv,
        "qtd_ped": qtd_ped,
        "qtd_rec": qtd_rec,
        "preco_unit_centavos": preco_unit_centavos,
        "situacao": situacao,
    }


GL778_ITEM1 = item_row()
GL778_ITEM2 = item_row(
    item=2, cod_mat="TRP-09", desc_mat="Caixa organizadora",
    fator_conv=3, qtd_ped=4, qtd_rec=0, preco_unit_centavos=10000,
)
GL779_ITEM1 = item_row(
    ped="GL-779", cnpj="56789012000134", nome="Armazéns Rio Claro Ltda",
    dt_criacao=1784160000, cod_mat="ARM-10", desc_mat="Estrado metálico",
    um="UN", fator_conv=1, qtd_ped=100, qtd_rec=100,
    preco_unit_centavos=3500, situacao=2,
)


# ── ParseResult ───────────────────────────────────────────────────────────────

def test_parse_returns_parse_result(adapter):
    result = adapter.parse([GL778_ITEM1])
    assert isinstance(result, ParseResult)


def test_parse_never_has_warnings(adapter):
    result = adapter.parse([GL778_ITEM1, GL778_ITEM2, GL779_ITEM1])
    assert result.warnings == []


# ── Agrupamento por pedido ────────────────────────────────────────────────────

def test_two_rows_same_ped_become_one_order_two_items(adapter):
    result = adapter.parse([GL778_ITEM1, GL778_ITEM2])
    assert len(result.orders) == 1
    assert len(result.orders[0].items) == 2


def test_rows_from_different_peds_become_separate_orders(adapter):
    result = adapter.parse([GL778_ITEM1, GL778_ITEM2, GL779_ITEM1])
    assert len(result.orders) == 2


def test_single_item_order_parsed(adapter):
    result = adapter.parse([GL779_ITEM1])
    assert len(result.orders) == 1
    assert len(result.orders[0].items) == 1


# ── Conversão de timestamp ────────────────────────────────────────────────────

def test_dt_criacao_converted_to_date(adapter):
    # 1786752000 = 2026-08-15 UTC
    result = adapter.parse([GL778_ITEM1])
    assert isinstance(result.orders[0].created_at, date)


def test_dt_criacao_none_returns_none(adapter):
    row = {**GL778_ITEM1, "dt_criacao": None}
    result = adapter.parse([row])
    assert result.orders[0].created_at is None


# ── Conversão de quantidades (fator_conv) ─────────────────────────────────────

def test_quantity_ordered_multiplied_by_fator_conv(adapter):
    # qtd_ped=10, fator_conv=12 → 120 unidades
    result = adapter.parse([GL778_ITEM1])
    assert result.orders[0].items[0].quantity_ordered == Decimal("120")


def test_quantity_received_multiplied_by_fator_conv(adapter):
    # qtd_rec=2, fator_conv=12 → 24 unidades
    result = adapter.parse([GL778_ITEM1])
    assert result.orders[0].items[0].quantity_received == Decimal("24")


def test_fator_conv_1_passthrough(adapter):
    # fator_conv=1 → sem conversão
    result = adapter.parse([GL779_ITEM1])
    item = result.orders[0].items[0]
    assert item.quantity_ordered == Decimal("100")
    assert item.quantity_received == Decimal("100")


# ── Conversão de preço (centavos + fator_conv) ────────────────────────────────

def test_unit_price_converted_from_centavos_and_fator(adapter):
    # preco_unit_centavos=120000, fator_conv=12 → 120000/100/12 = R$100/UN
    result = adapter.parse([GL778_ITEM1])
    assert result.orders[0].items[0].unit_price == Decimal("100")


def test_unit_price_fator_conv_1(adapter):
    # preco_unit_centavos=3500, fator_conv=1 → R$35/UN
    result = adapter.parse([GL779_ITEM1])
    assert result.orders[0].items[0].unit_price == Decimal("35")


# ── UOM normalizado ───────────────────────────────────────────────────────────

def test_uom_normalized_to_UN_even_for_CX(adapter):
    # Gama envia "CX" mas normalizamos para "UN" pois convertemos as quantidades
    result = adapter.parse([GL778_ITEM1])
    assert result.orders[0].items[0].uom == "UN"


def test_uom_is_UN_when_original_is_UN(adapter):
    result = adapter.parse([GL779_ITEM1])
    assert result.orders[0].items[0].uom == "UN"


# ── Mapeamento de status ──────────────────────────────────────────────────────

def test_situacao_1_maps_to_open(adapter):
    result = adapter.parse([item_row(situacao=1)])
    assert result.orders[0].status == OrderStatus.OPEN


def test_situacao_2_maps_to_closed(adapter):
    result = adapter.parse([item_row(situacao=2)])
    assert result.orders[0].status == OrderStatus.CLOSED


def test_situacao_3_maps_to_blocked(adapter):
    result = adapter.parse([item_row(situacao=3)])
    assert result.orders[0].status == OrderStatus.BLOCKED


# ── Outros campos ─────────────────────────────────────────────────────────────

def test_vendor_tax_id_preserved(adapter):
    result = adapter.parse([GL778_ITEM1])
    assert result.orders[0].vendor_tax_id == "34567890000112"


def test_client_id_is_gama(adapter):
    result = adapter.parse([GL778_ITEM1, GL779_ITEM1])
    for order in result.orders:
        assert order.client_id == "gama"


def test_item_created_at_is_none(adapter):
    result = adapter.parse([GL778_ITEM1])
    for item in result.orders[0].items:
        assert item.item_created_at is None


def test_currency_is_BRL(adapter):
    result = adapter.parse([GL778_ITEM1])
    assert result.orders[0].currency == "BRL"


# ── Erros ─────────────────────────────────────────────────────────────────────

def test_missing_ped_raises_value_error(adapter):
    row = {k: v for k, v in GL778_ITEM1.items() if k != "ped"}
    with pytest.raises(ValueError, match="ped"):
        adapter.parse([row])


def test_unknown_situacao_raises_value_error(adapter):
    row = {**GL778_ITEM1, "situacao": 99}
    with pytest.raises(ValueError, match="Situação desconhecida"):
        adapter.parse([row])


def test_missing_cod_mat_raises_value_error(adapter):
    row = {k: v for k, v in GL778_ITEM1.items() if k != "cod_mat"}
    with pytest.raises(ValueError, match="cod_mat"):
        adapter.parse([row])


def test_invalid_fator_conv_raises_value_error(adapter):
    row = {**GL778_ITEM1, "fator_conv": 0}
    with pytest.raises(ValueError, match="fator_conv"):
        adapter.parse([row])


def test_missing_cnpj_raises_value_error(adapter):
    row = {k: v for k, v in GL778_ITEM1.items() if k != "cnpj_fornecedor"}
    with pytest.raises(ValueError, match="cnpj_fornecedor"):
        adapter.parse([row])
