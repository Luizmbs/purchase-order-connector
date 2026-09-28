import pytest


# ── Helpers Gama ──────────────────────────────────────────────────────────────

def make_gama_row(
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
        "ped": ped, "item": item, "cnpj_fornecedor": cnpj,
        "nome_fornecedor": nome, "dt_criacao": dt_criacao,
        "cod_mat": cod_mat, "desc_mat": desc_mat, "um": um,
        "fator_conv": fator_conv, "qtd_ped": qtd_ped, "qtd_rec": qtd_rec,
        "preco_unit_centavos": preco_unit_centavos, "situacao": situacao,
    }


async def ingest_gama(client, auth_headers, *rows) -> dict:
    r = await client.post(
        "/api/v1/ingest/gama",
        json=list(rows),
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ── Helpers Delta ─────────────────────────────────────────────────────────────

def make_delta_order(
    po_number: str = "DL-001",
    status: str = "open",
    tax_id: str = "67890123000145",
    created_at: str = "2026-09-02",
) -> dict:
    return {
        "po_number": po_number,
        "created_at": created_at,
        "status": status,
        "currency": "BRL",
        "vendor": {"tax_id": tax_id, "name": "Fornecedor Delta Ltda"},
    }


def make_delta_item(
    purchase_order: str = "DL-001",
    line: int = 10,
    material: str = "EMB-500",
    qty_ordered: int = 800,
    qty_received: int = 300,
    unit_price: float = 3.75,
    created_at: str = "2026-09-02",
) -> dict:
    return {
        "purchase_order": purchase_order,
        "created_at": created_at,
        "line": line,
        "material": material,
        "description": "Item Delta",
        "uom": "UN",
        "quantity_ordered": qty_ordered,
        "quantity_received": qty_received,
        "unit_price": unit_price,
    }


async def ingest_delta(client, auth_headers, orders, items) -> dict:
    r = await client.post(
        "/api/v1/ingest/delta",
        json={"orders": orders, "items": items},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ── Gama: ingestão básica ─────────────────────────────────────────────────────

async def test_gama_ingest_returns_ingested_count(client, auth_headers):
    result = await ingest_gama(client, auth_headers, make_gama_row())
    assert result["ingested"] == 1
    assert result["updated"] == 0


async def test_gama_ingest_two_orders_flat(client, auth_headers):
    row1 = make_gama_row(ped="GL-778", item=1)
    row2 = make_gama_row(ped="GL-778", item=2, cod_mat="TRP-09", fator_conv=3, preco_unit_centavos=10000)
    row3 = make_gama_row(ped="GL-779", cnpj="56789012000134", cod_mat="ARM-10", fator_conv=1, situacao=2)
    result = await ingest_gama(client, auth_headers, row1, row2, row3)
    assert result["ingested"] == 2


async def test_gama_order_persisted_with_correct_values(client, auth_headers):
    # GL-778/TRP-01: 10 caixas × 12 = 120 UN; R$1200/cx ÷ 12 = R$100/UN
    await ingest_gama(client, auth_headers, make_gama_row())
    r = await client.get("/api/v1/purchase-orders/gama/GL-778", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["client_id"] == "gama"
    from decimal import Decimal
    item = body["items"][0]
    assert Decimal(item["quantity_ordered"]) == Decimal("120")
    assert Decimal(item["quantity_received"]) == Decimal("24")
    assert Decimal(item["unit_price"]) == Decimal("100")
    assert item["uom"] == "UN"


async def test_gama_status_open_persisted(client, auth_headers):
    await ingest_gama(client, auth_headers, make_gama_row(situacao=1))
    r = await client.get("/api/v1/purchase-orders/gama/GL-778", headers=auth_headers)
    assert r.json()["status"] == "open"


async def test_gama_status_closed_persisted(client, auth_headers):
    await ingest_gama(client, auth_headers, make_gama_row(situacao=2))
    r = await client.get("/api/v1/purchase-orders/gama/GL-778", headers=auth_headers)
    assert r.json()["status"] == "closed"


async def test_gama_reingest_updates_order(client, auth_headers):
    await ingest_gama(client, auth_headers, make_gama_row(qtd_rec=2))
    result = await ingest_gama(client, auth_headers, make_gama_row(qtd_rec=5))
    assert result["updated"] == 1
    assert result["ingested"] == 0


async def test_gama_appears_in_list(client, auth_headers):
    await ingest_gama(client, auth_headers, make_gama_row())
    r = await client.get("/api/v1/purchase-orders?client_id=gama", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1


# ── Gama: conferência ─────────────────────────────────────────────────────────

async def test_gama_conference_approved(client, auth_headers):
    # GL-778/TRP-01: saldo = 120 - 24 = 96 UN; NF envia 50 UN a R$100
    await ingest_gama(client, auth_headers, make_gama_row())
    r = await client.post(
        "/api/v1/conferences",
        json={
            "client_id": "gama",
            "po_number": "GL-778",
            "invoice_number": "NF-GAMA-001",
            "vendor_tax_id": "34567890000112",
            "items": [{"material": "TRP-01", "quantity": 50, "total_value": 5000.0}],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["result"] == "approved"


async def test_gama_conference_quantity_exceeded(client, auth_headers):
    # saldo = 96 UN; NF envia 999 UN
    await ingest_gama(client, auth_headers, make_gama_row())
    r = await client.post(
        "/api/v1/conferences",
        json={
            "client_id": "gama",
            "po_number": "GL-778",
            "invoice_number": "NF-GAMA-002",
            "vendor_tax_id": "34567890000112",
            "items": [{"material": "TRP-01", "quantity": 999, "total_value": 99900.0}],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["result"] == "rejected"
    assert any(d["type"] == "quantity_exceeded" for d in body["divergences"])


# ── Delta: ingestão básica ────────────────────────────────────────────────────

async def test_delta_ingest_returns_ingested_count(client, auth_headers):
    result = await ingest_delta(
        client, auth_headers,
        [make_delta_order()],
        [make_delta_item()],
    )
    assert result["ingested"] == 1
    assert result["updated"] == 0


async def test_delta_order_without_items_persisted(client, auth_headers):
    result = await ingest_delta(client, auth_headers, [make_delta_order("DL-046")], [])
    assert result["ingested"] == 1
    r = await client.get("/api/v1/purchase-orders/delta/DL-046", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["items"] == []


async def test_delta_item_created_at_persisted(client, auth_headers):
    item = make_delta_item(created_at="2026-09-08")
    await ingest_delta(client, auth_headers, [make_delta_order()], [item])
    r = await client.get("/api/v1/purchase-orders/delta/DL-001", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["items"][0]["item_created_at"] == "2026-09-08"


async def test_delta_orphan_item_discarded_with_warning(client, auth_headers):
    orphan = make_delta_item(purchase_order="DL-INEXISTENTE")
    result = await ingest_delta(client, auth_headers, [make_delta_order()], [orphan])
    assert any("DL-INEXISTENTE" in w for w in result["warnings"])


async def test_delta_orphan_item_resolved_from_db(client, auth_headers):
    # 1ª carga: pedido sem itens
    await ingest_delta(client, auth_headers, [make_delta_order("DL-001")], [])
    # 2ª carga: só itens (sem o cabeçalho) — devem ser anexados ao pedido existente
    orphan = make_delta_item(purchase_order="DL-001", line=10)
    result = await ingest_delta(client, auth_headers, [], [orphan])
    assert result["updated"] == 1
    r = await client.get("/api/v1/purchase-orders/delta/DL-001", headers=auth_headers)
    assert len(r.json()["items"]) == 1


async def test_delta_orphan_new_item_merged_with_existing(client, auth_headers):
    # 1ª carga: pedido com item linha 10
    await ingest_delta(
        client, auth_headers,
        [make_delta_order("DL-001")],
        [make_delta_item(purchase_order="DL-001", line=10)],
    )
    # 2ª carga: item órfão linha 20 (novo) — deve somar, não substituir
    orphan = make_delta_item(purchase_order="DL-001", line=20, material="EMB-720")
    await ingest_delta(client, auth_headers, [], [orphan])
    r = await client.get("/api/v1/purchase-orders/delta/DL-001", headers=auth_headers)
    assert len(r.json()["items"]) == 2


async def test_delta_reingest_updates_order(client, auth_headers):
    await ingest_delta(
        client, auth_headers,
        [make_delta_order()],
        [make_delta_item(qty_received=100)],
    )
    result = await ingest_delta(
        client, auth_headers,
        [make_delta_order()],
        [make_delta_item(qty_received=200)],
    )
    assert result["updated"] == 1


async def test_delta_appears_in_list(client, auth_headers):
    await ingest_delta(client, auth_headers, [make_delta_order()], [make_delta_item()])
    r = await client.get("/api/v1/purchase-orders?client_id=delta", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1


# ── Delta: conferência ────────────────────────────────────────────────────────

async def test_delta_conference_approved(client, auth_headers):
    # saldo = 800 - 300 = 500 UN; NF envia 100 UN a R$3.75
    await ingest_delta(client, auth_headers, [make_delta_order()], [make_delta_item()])
    r = await client.post(
        "/api/v1/conferences",
        json={
            "client_id": "delta",
            "po_number": "DL-001",
            "invoice_number": "NF-DELTA-001",
            "vendor_tax_id": "67890123000145",
            "items": [{"material": "EMB-500", "quantity": 100, "total_value": 375.0}],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    assert r.json()["result"] == "approved"


async def test_delta_conference_vendor_mismatch(client, auth_headers):
    await ingest_delta(client, auth_headers, [make_delta_order()], [make_delta_item()])
    r = await client.post(
        "/api/v1/conferences",
        json={
            "client_id": "delta",
            "po_number": "DL-001",
            "invoice_number": "NF-DELTA-002",
            "vendor_tax_id": "99999999000199",
            "items": [{"material": "EMB-500", "quantity": 10, "total_value": 37.5}],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["result"] == "rejected"
    assert any(d["type"] == "vendor_mismatch" for d in body["divergences"])


# ── Coexistência dos 4 clientes ───────────────────────────────────────────────

async def test_all_four_clients_listed_together(client, auth_headers):
    # Ingerir um pedido de cada cliente
    await client.post(
        "/api/v1/ingest/alfa",
        json={"purchase_orders": [{
            "po_number": "ALFA-001", "created_at": "2026-08-05", "status": "open",
            "currency": "BRL", "vendor": {"tax_id": "11111111000101", "name": "Alfa Vendor"},
            "items": [{"line": 10, "material": "M1", "uom": "UN",
                       "quantity_ordered": 10, "quantity_received": 0, "unit_price": 5.0}],
        }]},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/ingest/beta",
        data={
            "cabecalho": (
                "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
                "BETA-001;22222222000102;Beta Vendor;01/08/2026;EM ABERTO;BRL"
            ),
            "itens": (
                "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO\n"
                "BETA-001;1;M2;Produto Beta;UN;10,000;0,000;5,00"
            ),
        },
        headers=auth_headers,
    )
    await ingest_gama(client, auth_headers, make_gama_row())
    await ingest_delta(client, auth_headers, [make_delta_order()], [make_delta_item()])

    r = await client.get("/api/v1/purchase-orders", headers=auth_headers)
    assert r.status_code == 200
    client_ids = {o["client_id"] for o in r.json()["data"]}
    assert client_ids == {"alfa", "beta", "gama", "delta"}
