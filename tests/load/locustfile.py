"""
Teste de carga — Purchase Order Connector
=========================================

Três perfis de usuário com pesos que refletem uso real:

  ReaderUser      (weight=6) — leitura dominante: listagem + detalhe com cache
  IngestUser      (weight=2) — ingestão de novos pedidos + reingestão (upsert)
  ConferenceUser  (weight=2) — conferência de NF + listagem de conferências

Como rodar
----------
  # Com interface web (recomendado para análise):
  locust -f tests/load/locustfile.py --host http://localhost:8000
  # Abre http://localhost:8089 → defina nº de usuários e spawn rate

  # Modo headless (CI / linha de comando):
  locust -f tests/load/locustfile.py --host http://localhost:8000 \\
         --headless -u 50 -r 5 --run-time 60s

Pré-requisito: servidor rodando em localhost:8000
  docker compose up -d
"""

import random

import httpx
from locust import HttpUser, between, events, task

# ── Configuração de seed ───────────────────────────────────────────────────────

SEED_PO_COUNT = 50
SEED_PO_NUMBERS = [f"SEED-{i:04d}" for i in range(1, SEED_PO_COUNT + 1)]
# Subconjunto pequeno para concentrar cache hits nos testes de detalhe
HOT_PO_NUMBERS = SEED_PO_NUMBERS[:10]

UNIT_PRICE = 45.90
VENDOR_TAX_ID = "23456789000101"
MATERIAL = "MAT-LOAD"


def _make_order(po_number: str, qty_received: int = 60) -> dict:
    return {
        "po_number": po_number,
        "created_at": "2026-01-15",
        "status": "open",
        "currency": "BRL",
        "vendor": {"tax_id": VENDOR_TAX_ID, "name": "Fornecedor Carga Ltda"},
        "items": [
            {
                "line": 10,
                "material": MATERIAL,
                "uom": "UN",
                "quantity_ordered": 100,
                "quantity_received": qty_received,
                "unit_price": UNIT_PRICE,
            }
        ],
    }


def _get_token(base_url: str) -> str:
    resp = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# ── Hook de seed (roda uma vez antes de qualquer usuário iniciar) ──────────────

@events.test_start.add_listener
def seed_database(environment, **kwargs):
    base_url = environment.host
    token = _get_token(base_url)
    headers = {"Authorization": f"Bearer {token}"}

    batch_size = 10
    seeded = 0
    for i in range(0, SEED_PO_COUNT, batch_size):
        batch = SEED_PO_NUMBERS[i : i + batch_size]
        resp = httpx.post(
            f"{base_url}/api/v1/ingest/alfa",
            json={"purchase_orders": [_make_order(po) for po in batch]},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            seeded += resp.json().get("ingested", 0) + resp.json().get("updated", 0)

    print(f"\n[seed] {seeded} pedidos prontos para o teste ({SEED_PO_COUNT} enviados).")


# ── Helpers de autenticação por usuário ───────────────────────────────────────

def _login(client) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── Perfil 1: ReaderUser — leitura dominante ──────────────────────────────────

class ReaderUser(HttpUser):
    """
    Simula usuários da plataforma consultando pedidos.
    weight=6 → 60% dos usuários virtuais.

    Tarefas com pesos:
      list_orders      (3) — listagem paginada sem filtro
      list_with_filter (3) — listagem filtrada por status + has_pending
      get_detail       (6) — detalhe concentrado em 10 pedidos → alto cache hit rate
    """

    weight = 6
    wait_time = between(0.3, 1.5)

    def on_start(self):
        self._h = _login(self.client)

    @task(3)
    def list_orders(self):
        self.client.get(
            "/api/v1/purchase-orders?page=1&page_size=20",
            headers=self._h,
            name="GET /purchase-orders [sem filtro]",
        )

    @task(3)
    def list_with_filter(self):
        self.client.get(
            "/api/v1/purchase-orders?status=open&has_pending=true&page=1&page_size=20",
            headers=self._h,
            name="GET /purchase-orders [status+pending]",
        )

    @task(6)
    def get_detail(self):
        # Concentra em 10 pedidos para que o Redis sirva hits após a primeira requisição
        po = random.choice(HOT_PO_NUMBERS)
        self.client.get(
            f"/api/v1/purchase-orders/alfa/{po}",
            headers=self._h,
            name="GET /purchase-orders/{po} [detalhe]",
        )


# ── Perfil 2: IngestUser — escrita via ingestão ───────────────────────────────

class IngestUser(HttpUser):
    """
    Simula sistemas de cliente enviando pedidos.
    weight=2 → 20% dos usuários virtuais.

    Tarefas com pesos:
      ingest_new    (3) — cria pedidos novos (INSERT)
      reingest      (1) — reingere pedido seed com qty_received aleatório (UPDATE/diff)
    """

    weight = 2
    wait_time = between(1, 3)

    def on_start(self):
        self._h = _login(self.client)
        self._counter = random.randint(100_000, 999_999)

    @task(3)
    def ingest_new(self):
        self._counter += 1
        self.client.post(
            "/api/v1/ingest/alfa",
            json={"purchase_orders": [_make_order(f"DYN-{self._counter}")]},
            headers=self._h,
            name="POST /ingest/alfa [novo]",
        )

    @task(1)
    def reingest(self):
        # Reingere pedido seed com quantidade diferente → exercita upsert + diff
        po = random.choice(SEED_PO_NUMBERS)
        qty = random.randint(0, 100)
        self.client.post(
            "/api/v1/ingest/alfa",
            json={"purchase_orders": [_make_order(po, qty_received=qty)]},
            headers=self._h,
            name="POST /ingest/alfa [upsert]",
        )


# ── Perfil 3: ConferenceUser — conferência de NF ──────────────────────────────

class ConferenceUser(HttpUser):
    """
    Simula a plataforma V360 conferindo notas fiscais.
    weight=2 → 20% dos usuários virtuais.

    Tarefas com pesos:
      conference_valid_cnpj    (4) — NF com CNPJ correto (pode aprovar ou rejeitar por qty)
      conference_invalid_cnpj  (2) — NF com CNPJ errado → sempre rejeita (vendor_mismatch)
      list_conferences         (1) — listagem paginada de conferências
    """

    weight = 2
    wait_time = between(0.5, 2)

    def on_start(self):
        self._h = _login(self.client)
        self._nf_counter = random.randint(10_000, 99_999)

    def _next_nf(self) -> str:
        self._nf_counter += 1
        return f"NF-{self._nf_counter}"

    @task(4)
    def conference_valid_cnpj(self):
        po = random.choice(SEED_PO_NUMBERS)
        qty = random.randint(1, 5)  # pequeno para evitar quantity_exceeded na maioria dos casos
        self.client.post(
            "/api/v1/conferences",
            json={
                "client_id": "alfa",
                "po_number": po,
                "invoice_number": self._next_nf(),
                "vendor_tax_id": VENDOR_TAX_ID,
                "items": [
                    {
                        "material": MATERIAL,
                        "quantity": qty,
                        "total_value": round(qty * UNIT_PRICE, 2),
                    }
                ],
            },
            headers=self._h,
            name="POST /conferences [cnpj correto]",
        )

    @task(2)
    def conference_invalid_cnpj(self):
        po = random.choice(SEED_PO_NUMBERS)
        self.client.post(
            "/api/v1/conferences",
            json={
                "client_id": "alfa",
                "po_number": po,
                "invoice_number": self._next_nf(),
                "vendor_tax_id": "99999999000199",
                "items": [
                    {
                        "material": MATERIAL,
                        "quantity": 5,
                        "total_value": round(5 * UNIT_PRICE, 2),
                    }
                ],
            },
            headers=self._h,
            name="POST /conferences [cnpj errado]",
        )

    @task(1)
    def list_conferences(self):
        self.client.get(
            "/api/v1/conferences?page=1&page_size=20",
            headers=self._h,
            name="GET /conferences [listagem]",
        )
