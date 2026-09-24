# Purchase Order Connector — Visão Geral

## O problema

Quando uma empresa recebe uma nota fiscal de um fornecedor, alguém precisa conferir se ela bate com o pedido de compra que foi feito: o material é o mesmo? A quantidade cabe no que ainda falta receber? O preço é o acordado?

A plataforma V360 automatiza essa conferência — mas para isso precisa consultar os pedidos de compra de cada cliente. O problema é que cada cliente usa um sistema diferente, exporta os dados de um jeito diferente.

**Este serviço é a camada do meio:** recebe os dados de cada cliente no formato dele, normaliza tudo para um modelo único e expõe uma API padronizada para a plataforma V360 consumir.

---

## Os 4 clientes (formatos de entrada)

| Cliente | Formato | Particularidades |
|---|---|---|
| **Alfa Energia** | JSON com itens aninhados | Formato mais simples |
| **Beta Alimentos** | Dois CSVs separados por `;` | Formato brasileiro (datas, números, CNPJ com máscara, status em PT) |
| **Gama Logística** | JSON flat (uma linha por item) | Timestamp Unix, preços em centavos, quantidades em caixas com fator de conversão |
| **Delta Distribuição** | Dois JSONs separados (pedidos + itens) | Join feito pelo serviço; cada item tem sua própria data de criação |

---

## Arquitetura

O projeto usa **arquitetura hexagonal**: o domínio (regras de negócio) fica isolado no centro, sem depender de banco, HTTP ou qualquer lib externa. As dependências sempre apontam para dentro.

```
┌─────────────────────────────────────────────┐
│  Adapters de entrada                        │
│  (FastAPI — endpoints HTTP)                 │
│  ┌───────────────────────────────────────┐  │
│  │  Domínio                              │  │
│  │  (regras de conferência, serviços)    │  │
│  └───────────────────────────────────────┘  │
│  Adapters de saída                          │
│  (PostgreSQL, Redis, parsers de cliente)    │
└─────────────────────────────────────────────┘
```

Os parsers de cada cliente seguem o **Strategy Pattern**: todos implementam a mesma interface (`parse(dados) → lista de pedidos`) e se registram num registry. Adicionar um cliente novo = criar um arquivo, registrar — sem tocar no código existente.

### Camadas

```
src/purchase_order_connector/
│
├── domain/                        # Núcleo — zero dependências externas
│   ├── models/                    # Entidades: PurchaseOrder, Invoice, Conference...
│   ├── ports/
│   │   ├── inbound/               # Interfaces dos casos de uso (o que a API pode chamar)
│   │   └── outbound/              # Interfaces dos repositórios (o que o domínio precisa do banco)
│   └── services/                  # Lógica de negócio: InvoiceChecker, PurchaseOrderService...
│
├── adapters/
│   ├── inbound/
│   │   └── api/
│   │       ├── routers/           # Endpoints FastAPI
│   │       ├── schemas/           # Schemas Pydantic de request/response
│   │       └── middleware/        # Logging, correlation ID
│   └── outbound/
│       ├── persistence/           # Repositórios PostgreSQL (implementam os ports)
│       └── clients/               # Parsers por cliente (Strategy Pattern)
│           ├── alfa/adapter.py
│           ├── beta/adapter.py
│           ├── gama/adapter.py
│           └── delta/adapter.py
│
└── infrastructure/                # Config, conexão com banco/Redis, injeção de dependência
```

### Stack

- **Python 3.12 + FastAPI** — API REST com OpenAPI automático
- **PostgreSQL 16** — banco principal
- **Redis** — cache de pedidos individuais (TTL 10min) e lista de clientes (TTL 1h)
- **Alembic** — migrações versionadas
- **structlog** — logs estruturados em JSON (produção) ou console colorido (dev)
- **Docker Compose** — sobe tudo com um comando (`docker compose up`)

---

## Banco de dados

7 tabelas. O diagrama de relacionamento:

```
users
  └── refresh_tokens

clients
  ├── purchase_orders
  │     └── purchase_order_items
  └── conferences
        └── conference_divergences
              (também FK em purchase_orders)
```

### Tabelas principais

**`clients`** — cadastro dos clientes integrados
```
id (PK, slug)  |  name  |  format_type  |  active
"alfa"         |  "Alfa Energia"  |  "json_nested"  |  true
```

**`purchase_orders`** — pedidos normalizados de todos os clientes
```
id (UUID)  |  client_id (FK)  |  po_number  |  status  |  vendor_tax_id  |  ...
```
Chave de negócio: `(client_id, po_number)` — o mesmo número de pedido pode existir em clientes diferentes.

**`purchase_order_items`** — itens dos pedidos
```
id  |  purchase_order_id (FK)  |  line  |  material  |  quantity_ordered  |  quantity_received  |  unit_price
```
Todos os valores em **unidades individuais** e **BRL** — a conversão de caixas/centavos acontece no adapter do cliente.

**`conferences`** — histórico de conferências de NF
```
id  |  purchase_order_id (FK, nullable)  |  client_id  |  po_number  |  result (approved/rejected)  |  checked_at
```
Salva **toda** conferência, inclusive quando o pedido não foi encontrado.

**`conference_divergences`** — o que não bateu em cada conferência
```
id  |  conference_id (FK)  |  type  |  material  |  expected  |  received  |  detail
```

### Tipos de divergência

| Tipo | Quando ocorre |
|---|---|
| `order_not_found` | Pedido não existe no banco |
| `vendor_mismatch` | CNPJ da NF ≠ CNPJ do pedido |
| `material_not_found` | Material da NF não existe no pedido |
| `quantity_exceeded` | Quantidade da NF > saldo pendente do item |
| `price_mismatch` | Preço unitário da NF difere do acordado (tolerância: R$ 0,01) |

### Upsert (pedido reenviado)

Quando o mesmo pedido é carregado novamente: cabeçalho é atualizado, itens são substituídos por completo ("last write wins"). Conferências anteriores não são afetadas.

---

## Endpoints da API

```
# Autenticação
POST  /api/v1/auth/login       → access_token + refresh_token
POST  /api/v1/auth/refresh     → novo access_token
POST  /api/v1/auth/logout      → revoga refresh_token

# Ingestão (operadores e admins)
POST  /api/v1/ingest/{client_id}

# Pedidos
GET   /api/v1/purchase-orders                          → lista paginada com filtros
GET   /api/v1/purchase-orders/{client_id}/{po_number}  → detalhe com saldo por item

# Conferências
POST  /api/v1/conferences      → confere NF, salva e retorna resultado
GET   /api/v1/conferences      → relatório paginado

# Admin (apenas role = admin)
POST/GET/PATCH  /api/v1/admin/clients
POST/GET/PATCH  /api/v1/admin/users
```

### Paginação

Offset-based em todas as listagens. Padrão: `page_size=20`, máximo: `page_size=100`. Resposta sempre inclui `total`, `total_pages`, `has_next`, `has_prev`.

### Autenticação

JWT com dois tokens: **access token** (curta duração, stateless) para autenticar cada requisição, e **refresh token** (longa duração, armazenado no banco) para renovar o access token sem novo login. Dois roles: `admin` e `operator`.


