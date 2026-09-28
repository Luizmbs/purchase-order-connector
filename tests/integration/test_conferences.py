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


def make_invoice(
    po_number: str = "PO-001",
    invoice_number: str = "NF-001",
    vendor_tax_id: str = "23456789000101",
    material: str = "MAT-1001",
    quantity: float = 40,
    total_value: float = 1836.0,  # 40 × 45.90
    client_id: str = "alfa",
) -> dict:
    return {
        "client_id": client_id,
        "po_number": po_number,
        "invoice_number": invoice_number,
        "vendor_tax_id": vendor_tax_id,
        "items": [{"material": material, "quantity": quantity, "total_value": total_value}],
    }


async def post_conference(client, auth_headers, body: dict) -> dict:
    r = await client.post("/api/v1/conferences", json=body, headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


# ── POST /conferences — aprovação ─────────────────────────────────────────────

async def test_valid_invoice_approved(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa())
    result = await post_conference(client, auth_headers, make_invoice())
    assert result["result"] == "approved"
    assert result["divergences"] == []
    assert "conference_id" in result


# ── POST /conferences — order_not_found ───────────────────────────────────────

async def test_order_not_found_rejected(client, auth_headers):
    result = await post_conference(
        client, auth_headers,
        make_invoice(po_number="PO-INEXISTENTE"),
    )
    assert result["result"] == "rejected"
    types = [d["type"] for d in result["divergences"]]
    assert "order_not_found" in types


# ── POST /conferences — order_not_open ────────────────────────────────────────

async def test_order_not_open_rejected(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa(status="closed"))
    result = await post_conference(client, auth_headers, make_invoice())
    assert result["result"] == "rejected"
    types = [d["type"] for d in result["divergences"]]
    assert "order_not_open" in types


# ── POST /conferences — vendor_mismatch ───────────────────────────────────────

async def test_vendor_mismatch_rejected(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa())
    result = await post_conference(
        client, auth_headers,
        make_invoice(vendor_tax_id="99999999000199"),
    )
    assert result["result"] == "rejected"
    types = [d["type"] for d in result["divergences"]]
    assert "vendor_mismatch" in types


# ── POST /conferences — material_not_found ────────────────────────────────────

async def test_material_not_found_rejected(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa())
    result = await post_conference(
        client, auth_headers,
        make_invoice(material="MAT-INEXISTENTE", total_value=100.0),
    )
    assert result["result"] == "rejected"
    types = [d["type"] for d in result["divergences"]]
    assert "material_not_found" in types


# ── POST /conferences — quantity_exceeded ─────────────────────────────────────

async def test_quantity_exceeded_rejected(client, auth_headers):
    # saldo pendente = 100 - 60 = 40; nota envia 999
    await ingest_alfa(client, auth_headers, make_alfa(qty_ordered=100, qty_received=60))
    result = await post_conference(
        client, auth_headers,
        make_invoice(quantity=999, total_value=45900.0),
    )
    assert result["result"] == "rejected"
    types = [d["type"] for d in result["divergences"]]
    assert "quantity_exceeded" in types


async def test_quantity_exactly_at_pending_approved(client, auth_headers):
    # saldo = 40; nota envia exatamente 40 → aprovado
    await ingest_alfa(client, auth_headers, make_alfa(qty_ordered=100, qty_received=60))
    result = await post_conference(
        client, auth_headers,
        make_invoice(quantity=40, total_value=1836.0),
    )
    assert result["result"] == "approved"


# ── POST /conferences — price_mismatch ───────────────────────────────────────

async def test_price_mismatch_rejected(client, auth_headers):
    # preço do pedido = 45.90; nota envia 1 unidade por 50.00
    await ingest_alfa(client, auth_headers, make_alfa(unit_price=45.9))
    result = await post_conference(
        client, auth_headers,
        make_invoice(quantity=1, total_value=50.0),
    )
    assert result["result"] == "rejected"
    types = [d["type"] for d in result["divergences"]]
    assert "price_mismatch" in types


async def test_price_exactly_at_tolerance_rejected(client, auth_headers):
    # diferença de R$0.01 exato → rejeitado (>= tolerância)
    await ingest_alfa(client, auth_headers, make_alfa(unit_price=45.9))
    result = await post_conference(
        client, auth_headers,
        make_invoice(quantity=1, total_value=45.91),
    )
    assert result["result"] == "rejected"
    types = [d["type"] for d in result["divergences"]]
    assert "price_mismatch" in types


async def test_price_within_tolerance_approved(client, auth_headers):
    # diferença de R$0.009 → aprovado (< tolerância)
    await ingest_alfa(client, auth_headers, make_alfa(unit_price=45.9))
    result = await post_conference(
        client, auth_headers,
        make_invoice(quantity=1, total_value=45.909),
    )
    assert result["result"] == "approved"


# ── POST /conferences — múltiplas divergências ────────────────────────────────

async def test_multiple_divergences_all_listed(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa())
    result = await post_conference(
        client, auth_headers,
        make_invoice(
            vendor_tax_id="99999999000199",   # vendor errado
            quantity=999,                      # quantidade excedida
            total_value=45900.0,
        ),
    )
    assert result["result"] == "rejected"
    types = [d["type"] for d in result["divergences"]]
    assert "vendor_mismatch" in types
    assert "quantity_exceeded" in types


# ── Persistência ─────────────────────────────────────────────────────────────

async def test_conference_saved_to_db(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa())
    await post_conference(client, auth_headers, make_invoice())

    r = await client.get("/api/v1/conferences", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["has_next"] is False


async def test_rejected_conference_saved_with_divergences(client, auth_headers):
    result = await post_conference(
        client, auth_headers,
        make_invoice(po_number="PO-INEXISTENTE"),
    )
    conference_id = result["conference_id"]

    r = await client.get("/api/v1/conferences?result=rejected", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["divergences_count"] == 1


# ── GET /conferences ──────────────────────────────────────────────────────────

async def test_list_all_conferences(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa())
    await post_conference(client, auth_headers, make_invoice(invoice_number="NF-001"))
    await post_conference(client, auth_headers, make_invoice(invoice_number="NF-002"))

    r = await client.get("/api/v1/conferences", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["has_next"] is False


async def test_filter_by_result_rejected(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa())
    await post_conference(client, auth_headers, make_invoice(invoice_number="NF-OK"))
    await post_conference(
        client, auth_headers,
        make_invoice(invoice_number="NF-FAIL", po_number="PO-INEXISTENTE"),
    )

    r = await client.get("/api/v1/conferences?result=rejected", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["result"] == "rejected"


async def test_filter_by_client_id(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa("PO-001"))
    await post_conference(
        client, auth_headers,
        make_invoice(po_number="PO-001", client_id="alfa"),
    )
    # conferência sem pedido correspondente para client "beta"
    await post_conference(
        client, auth_headers,
        {**make_invoice(po_number="PO-BETA"), "client_id": "beta"},
    )

    r = await client.get("/api/v1/conferences?client_id=alfa", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["client_id"] == "alfa"


async def test_pagination_works(client, auth_headers):
    # 3 conferências, page_size=2
    await ingest_alfa(client, auth_headers, make_alfa())
    for i in range(3):
        await post_conference(
            client, auth_headers,
            make_invoice(invoice_number=f"NF-{i:03d}"),
        )

    r = await client.get("/api/v1/conferences?page_size=2", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["has_next"] is True
    assert body["pagination"]["has_prev"] is False
    assert body["pagination"]["next_cursor"] is not None


async def test_divergence_types_in_summary(client, auth_headers):
    await ingest_alfa(client, auth_headers, make_alfa())
    # 999 × 45.90 = 45845.10 → preço correto para evitar price_mismatch
    # vendor errado + quantidade excedida → exatamente 2 divergências
    await post_conference(
        client, auth_headers,
        make_invoice(
            vendor_tax_id="99999999000199",
            quantity=999,
            total_value=45845.10,
        ),
    )

    r = await client.get("/api/v1/conferences?result=rejected", headers=auth_headers)
    assert r.status_code == 200
    summary = r.json()["data"][0]
    assert summary["divergences_count"] == 2
    assert "vendor_mismatch" in summary["divergence_types"]
    assert "quantity_exceeded" in summary["divergence_types"]
