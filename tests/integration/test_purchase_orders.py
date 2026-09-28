import pytest
import pytest_asyncio


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_alfa(
    po_number: str = "PO-001",
    status: str = "open",
    vendor_tax_id: str = "23456789000101",
    qty_ordered: int = 100,
    qty_received: int = 60,
    unit_price: float = 45.9,
    material: str = "MAT-1001",
    line: int = 10,
) -> dict:
    return {
        "po_number": po_number,
        "created_at": "2026-08-05",
        "status": status,
        "currency": "BRL",
        "vendor": {"tax_id": vendor_tax_id, "name": "Fornecedor Ltda"},
        "items": [
            {
                "line": line,
                "material": material,
                "uom": "UN",
                "quantity_ordered": qty_ordered,
                "quantity_received": qty_received,
                "unit_price": unit_price,
            }
        ],
    }


async def ingest_alfa(client, auth_headers, *orders) -> dict:
    r = await client.post(
        "/api/v1/ingest/alfa",
        json={"purchase_orders": list(orders)},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


BETA_CABECALHO = (
    "NUMERO_PEDIDO;FORNECEDOR_CNPJ;FORNECEDOR_RAZAO_SOCIAL;EMISSAO;SITUACAO;MOEDA\n"
    "BETA-001;12345678000190;Distribuidora Beta Ltda;01/08/2026;EM ABERTO;BRL"
)
BETA_ITENS = (
    "NUMERO_PEDIDO;ITEM;CODIGO_MATERIAL;DESCRICAO;UNIDADE;QTD_PEDIDA;QTD_RECEBIDA;PRECO_UNITARIO\n"
    "BETA-001;1;MAT-99;Produto Beta;UN;50,000;0,000;10,00"
)


async def ingest_beta(client, auth_headers) -> dict:
    r = await client.post(
        "/api/v1/ingest/beta",
        data={"cabecalho": BETA_CABECALHO, "itens": BETA_ITENS},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ── Listagem ──────────────────────────────────────────────────────────────────

async def test_list_returns_empty_when_no_orders(client, auth_headers):
    r = await client.get("/api/v1/purchase-orders", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["pagination"]["total"] == 0


async def test_list_returns_ingested_orders(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa("PO-001"), make_alfa("PO-002"))
    r = await client.get("/api/v1/purchase-orders", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["pagination"]["total"] == 2


async def test_filter_by_client_id(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa("PO-001"))
    await ingest_beta(client, auth_headers)

    r = await client.get("/api/v1/purchase-orders?client_id=alfa", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["client_id"] == "alfa"


async def test_filter_by_status_open(client, auth_headers):
    await ingest_alfa(
        client, auth_headers,
        make_alfa("PO-001", status="open"),
        make_alfa("PO-002", status="closed"),
    )
    r = await client.get("/api/v1/purchase-orders?status=open", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["status"] == "open"


async def test_filter_by_vendor_tax_id(client, auth_headers):
    await ingest_alfa(
        client, auth_headers,
        make_alfa("PO-001", vendor_tax_id="23456789000101"),
        make_alfa("PO-002", vendor_tax_id="99999999000199"),
    )
    r = await client.get(
        "/api/v1/purchase-orders?vendor_tax_id=99999999000199",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["vendor_tax_id"] == "99999999000199"


async def test_filter_has_pending_true(client, auth_headers):
    # PO-001: 100 pedidos, 60 recebidos → 40 pendentes → has_pending=True
    # PO-002: 100 pedidos, 100 recebidos → 0 pendentes → has_pending=False
    await ingest_alfa(
        client, auth_headers,
        make_alfa("PO-001", qty_ordered=100, qty_received=60),
        make_alfa("PO-002", qty_ordered=100, qty_received=100),
    )
    r = await client.get("/api/v1/purchase-orders?has_pending=true", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["po_number"] == "PO-001"


async def test_filter_has_pending_false(client, auth_headers):
    await ingest_alfa(
        client, auth_headers,
        make_alfa("PO-001", qty_ordered=100, qty_received=60),
        make_alfa("PO-002", qty_ordered=100, qty_received=100),
    )
    r = await client.get("/api/v1/purchase-orders?has_pending=false", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["po_number"] == "PO-002"


async def test_pagination_page_size(client, auth_headers):
    orders = [make_alfa(f"PO-{i:03d}") for i in range(1, 6)]
    await ingest_alfa(client, auth_headers, *orders)

    r = await client.get("/api/v1/purchase-orders?page=1&page_size=2", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["total"] == 5
    assert body["pagination"]["total_pages"] == 3
    assert body["pagination"]["has_next"] is True
    assert body["pagination"]["has_prev"] is False


async def test_pagination_last_page(client, auth_headers):
    orders = [make_alfa(f"PO-{i:03d}") for i in range(1, 6)]
    await ingest_alfa(client, auth_headers, *orders)

    r = await client.get("/api/v1/purchase-orders?page=3&page_size=2", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["has_next"] is False
    assert body["pagination"]["has_prev"] is True


async def test_filters_combined_with_pagination(client, auth_headers):
    await ingest_alfa(
        client, auth_headers,
        make_alfa("PO-001", status="open"),
        make_alfa("PO-002", status="open"),
        make_alfa("PO-003", status="closed"),
    )
    r = await client.get(
        "/api/v1/purchase-orders?status=open&page=1&page_size=1",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["total"] == 2
    assert body["pagination"]["total_pages"] == 2


async def test_page_size_above_max_returns_422(client, auth_headers):
    r = await client.get("/api/v1/purchase-orders?page_size=200", headers=auth_headers)
    assert r.status_code == 422


async def test_invalid_status_returns_422(client, auth_headers):
    r = await client.get("/api/v1/purchase-orders?status=invalido", headers=auth_headers)
    assert r.status_code == 422


async def test_unauthenticated_returns_401(client):
    r = await client.get("/api/v1/purchase-orders")
    assert r.status_code == 401


# ── Detalhe ───────────────────────────────────────────────────────────────────

async def test_get_existing_order_returns_detail(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa("PO-001"))
    r = await client.get("/api/v1/purchase-orders/alfa/PO-001", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["po_number"] == "PO-001"
    assert body["client_id"] == "alfa"
    assert len(body["items"]) == 1


async def test_get_nonexistent_order_returns_404(client, auth_headers):
    r = await client.get("/api/v1/purchase-orders/alfa/PO-INEXISTENTE", headers=auth_headers)
    assert r.status_code == 404


async def test_quantity_pending_calculated_correctly(client, auth_headers):
    await ingest_alfa(
        client, auth_headers,
        make_alfa("PO-001", qty_ordered=100, qty_received=60),
    )
    r = await client.get("/api/v1/purchase-orders/alfa/PO-001", headers=auth_headers)
    assert r.status_code == 200
    item = r.json()["items"][0]
    # DB armazena NUMERIC(15,3), portanto compara via Decimal para ignorar zeros finais
    from decimal import Decimal
    assert Decimal(item["quantity_ordered"]) == Decimal("100")
    assert Decimal(item["quantity_received"]) == Decimal("60")
    assert Decimal(item["quantity_pending"]) == Decimal("40")


async def test_x_cache_header_miss_on_first_request(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa("PO-001"))
    r = await client.get("/api/v1/purchase-orders/alfa/PO-001", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers.get("x-cache") == "MISS"


async def test_x_cache_header_hit_on_second_request(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa("PO-001"))
    await client.get("/api/v1/purchase-orders/alfa/PO-001", headers=auth_headers)
    r = await client.get("/api/v1/purchase-orders/alfa/PO-001", headers=auth_headers)
    assert r.headers.get("x-cache") == "HIT"


# ── Reingestão (upsert) ───────────────────────────────────────────────────────

async def test_reingest_counts_as_updated(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa("PO-001"))
    result = await ingest_alfa(client, auth_headers, make_alfa("PO-001"))
    assert result["ingested"] == 0
    assert result["updated"] == 1


async def test_reingest_with_changes_shows_diff(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa("PO-001", qty_received=60))
    result = await ingest_alfa(client, auth_headers, make_alfa("PO-001", qty_received=80))
    assert result["updated"] == 1
    changes = result["updates"][0]["changes"]
    field_names = [c["field"] for c in changes]
    assert "item.linha_10.quantity_received" in field_names
    change = next(c for c in changes if c["field"] == "item.linha_10.quantity_received")
    # before vem do DB (NUMERIC(15,3) → "60.000"), after vem do adapter ("80")
    from decimal import Decimal
    assert Decimal(change["before"]) == Decimal("60")
    assert Decimal(change["after"]) == Decimal("80")


async def test_reingest_without_changes_shows_empty_diff(client, auth_headers):
    order = make_alfa("PO-001")
    await ingest_alfa(client, auth_headers, order)
    result = await ingest_alfa(client, auth_headers, order)
    assert result["updates"][0]["changes"] == []
