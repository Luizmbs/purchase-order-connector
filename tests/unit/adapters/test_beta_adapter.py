from datetime import date
from decimal import Decimal

import pytest

from adapters.clients.beta.adapter import BetaAdapter
from domain.models.purchase_order import OrderStatus


CABECALHO_CSV = (
    "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
    "20260088412;12.345.678/0001-90;Distribuidora Horizonte Ltda;15/08/2026;EM ABERTO;BRL\n"
    "20260088413;98.765.432/0001-55;Frigorífico Boa Mesa S.A.;01/08/2026;BLOQUEADO;BRL"
)

ITENS_CSV = (
    "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO\n"
    "20260088412;1;MAT-77;Óleo de soja 900ml;UN;1.200,000;400,000;6,49\n"
    "20260088412;2;MAT-78;Açúcar refinado 1kg;UN;500,000;0,000;4,15\n"
    "20260088413;1;MAT-91;Carne bovina dianteiro kg;KG;2.000,000;0,000;27,90"
)


@pytest.fixture
def adapter() -> BetaAdapter:
    return BetaAdapter()


@pytest.fixture
def parsed(adapter) -> list:
    return adapter.parse({"cabecalho": CABECALHO_CSV, "itens": ITENS_CSV})


# ── Parse correto ─────────────────────────────────────────────────────────────

def test_parse_returns_two_orders(parsed):
    assert len(parsed) == 2


def test_order_has_correct_item_count(parsed):
    order_412 = next(o for o in parsed if o.po_number == "20260088412")
    order_413 = next(o for o in parsed if o.po_number == "20260088413")
    assert len(order_412.items) == 2
    assert len(order_413.items) == 1


# ── Normalização de CNPJ ──────────────────────────────────────────────────────

def test_cnpj_mask_removed(adapter):
    cab = (
        "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
        "PO-X;12.345.678/0001-90;Empresa X;01/01/2026;EM ABERTO;BRL"
    )
    itens = "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO"
    orders = adapter.parse({"cabecalho": cab, "itens": itens})
    assert orders[0].vendor_tax_id == "12345678000190"


def test_cnpj_without_mask_preserved(adapter):
    cab = (
        "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
        "PO-X;12345678000190;Empresa X;01/01/2026;EM ABERTO;BRL"
    )
    itens = "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO"
    orders = adapter.parse({"cabecalho": cab, "itens": itens})
    assert orders[0].vendor_tax_id == "12345678000190"


# ── Normalização de data ──────────────────────────────────────────────────────

def test_date_br_format_parsed(parsed):
    order_412 = next(o for o in parsed if o.po_number == "20260088412")
    assert order_412.created_at == date(2026, 8, 15)


# ── Normalização de números brasileiros ───────────────────────────────────────

def test_quantity_with_thousand_separator(parsed):
    order_412 = next(o for o in parsed if o.po_number == "20260088412")
    item_77 = next(i for i in order_412.items if i.material == "MAT-77")
    assert item_77.quantity_ordered == Decimal("1200.000")


def test_quantity_without_separator(parsed):
    order_412 = next(o for o in parsed if o.po_number == "20260088412")
    item_78 = next(i for i in order_412.items if i.material == "MAT-78")
    assert item_78.quantity_ordered == Decimal("500.000")


def test_price_with_comma(parsed):
    order_412 = next(o for o in parsed if o.po_number == "20260088412")
    item_77 = next(i for i in order_412.items if i.material == "MAT-77")
    assert item_77.unit_price == Decimal("6.49")


# ── Mapeamento de status PT-BR ────────────────────────────────────────────────

def test_status_em_aberto_mapped(parsed):
    order_412 = next(o for o in parsed if o.po_number == "20260088412")
    assert order_412.status == OrderStatus.OPEN


def test_status_bloqueado_mapped(parsed):
    order_413 = next(o for o in parsed if o.po_number == "20260088413")
    assert order_413.status == OrderStatus.BLOCKED


def test_status_encerrado_mapped(adapter):
    cab = (
        "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
        "PO-ENC;12345678000190;Empresa X;01/01/2026;ENCERRADO;BRL"
    )
    itens = "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO"
    orders = adapter.parse({"cabecalho": cab, "itens": itens})
    assert orders[0].status == OrderStatus.CLOSED


# ── Comportamento com dados faltantes ─────────────────────────────────────────

def test_item_without_header_is_skipped(adapter):
    cab = (
        "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
        "PO-OK;12345678000190;Empresa X;01/01/2026;EM ABERTO;BRL"
    )
    itens = (
        "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO\n"
        "PO-OK;1;MAT-01;Item válido;UN;10,000;0,000;5,00\n"
        "PO-FANTASMA;1;MAT-02;Órfão;UN;5,000;0,000;3,00"  # sem cabeçalho
    )
    orders = adapter.parse({"cabecalho": cab, "itens": itens})
    assert len(orders) == 1
    assert len(orders[0].items) == 1


def test_header_without_items_returns_empty_items(adapter):
    cab = (
        "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
        "PO-SEM-ITENS;12345678000190;Empresa X;01/01/2026;EM ABERTO;BRL"
    )
    itens = "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO"
    orders = adapter.parse({"cabecalho": cab, "itens": itens})
    assert len(orders) == 1
    assert orders[0].items == []


# ── Erros ─────────────────────────────────────────────────────────────────────

def test_unknown_status_raises_value_error(adapter):
    cab = (
        "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
        "PO-X;12345678000190;Empresa X;01/01/2026;PENDENTE;BRL"
    )
    itens = "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO"
    with pytest.raises(ValueError, match="Status desconhecido"):
        adapter.parse({"cabecalho": cab, "itens": itens})


def test_invalid_date_raises_error(adapter):
    cab = (
        "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
        "PO-X;12345678000190;Empresa X;2026-01-01;EM ABERTO;BRL"
    )
    itens = "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO"
    with pytest.raises((ValueError, Exception)):
        adapter.parse({"cabecalho": cab, "itens": itens})


# ── client_id ─────────────────────────────────────────────────────────────────

def test_client_id_is_beta(parsed):
    for order in parsed:
        assert order.client_id == "beta"
