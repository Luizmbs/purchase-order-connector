# Purchase Order Connector

Serviço backend que conecta a plataforma V360 aos sistemas de pedidos de compra de clientes corporativos. Cada cliente expõe seus dados em um formato diferente; este serviço normaliza tudo para um contrato único e confiável, atende às consultas da plataforma e confere notas fiscais contra pedidos.

---

## Como rodar

### Pré-requisitos

- Docker e Docker Compose instalados
- Porta `8000` (API) e `5433` (PostgreSQL) livres na máquina

### Subindo o projeto

```bash
git clone <url-do-repositorio>
cd purchase-order-connector

cp .env.example .env   # ajuste se necessário

docker compose up --build
```

A API estará disponível em `http://localhost:8000`.  
As migrações do banco rodam automaticamente no startup via Alembic.

### Verificando que está no ar

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### Rodando os testes

```bash
# Unitários
docker exec purchase-order-connector_api_1 python -m pytest tests/unit/ -v

# Integração (cria banco v360_test automaticamente)
docker exec purchase-order-connector_api_1 python -m pytest tests/integration/ -v

# Todos
docker exec purchase-order-connector_api_1 python -m pytest tests/ -v
```

### Teste de carga (Locust)

```bash
# Com interface web em http://localhost:8089
docker compose --profile load up locust

# Headless (60s, 50 usuários)
docker compose --profile load run --rm locust \
  locust -f tests/load/locustfile.py --host http://api:8000 \
         --headless -u 50 -r 5 --run-time 60s --only-summary
```

### Credenciais padrão

```
Usuário: admin
Senha:   admin123
```

---

## Endpoints

A documentação interativa completa está em `http://localhost:8000/docs` (Swagger UI).  
Uma coleção `.http` com exemplos de todas as chamadas está em `requests/v360.http`.

### Autenticação

```
POST /api/v1/auth/login          Login — retorna access_token (JWT) e refresh_token
POST /api/v1/auth/refresh        Renova o access_token usando o refresh_token
POST /api/v1/auth/logout         Revoga o refresh_token
```

Todos os endpoints abaixo exigem o header `Authorization: Bearer <token>`.

### Ingestão

```
POST /api/v1/ingest/alfa         JSON com pedidos aninhados (Alfa Energia)
POST /api/v1/ingest/beta         Multipart com dois campos: cabecalho e itens (Beta Alimentos)
```

Resposta de ingestão:

```json
{
  "ingested": 2,
  "updated": 1,
  "errors": [],
  "warnings": [],
  "updates": [
    {
      "po_number": "PO-001",
      "client_id": "alfa",
      "changes": [
        { "field": "item.linha_10.quantity_received", "before": "60.000", "after": "80" }
      ]
    }
  ]
}
```

Quando um pedido já existe (`updated > 0`), o campo `updates` detalha campo a campo o que mudou, facilitando auditoria de reingestões.

### Pedidos de compra

```
GET /api/v1/purchase-orders
    ?client_id=alfa
    &vendor_tax_id=23456789000101
    &status=open
    &has_pending=true
    &page_size=20
    &cursor=<token-da-página-anterior>

GET /api/v1/purchase-orders/{client_id}/{po_number}
```

### Conferências

```
POST /api/v1/conferences         Confere uma NF contra um pedido
GET  /api/v1/conferences
     ?result=rejected
     &client_id=alfa
     &page_size=20
     &cursor=<token-da-página-anterior>
```

### Administração

```
GET/POST   /api/v1/admin/users      Gerencia usuários (role: admin)
GET/POST   /api/v1/admin/clients    Gerencia clientes cadastrados
```

---

## Arquitetura

### Hexagonal + Strategy + Registry/Factory Method

O projeto adota arquitetura hexagonal para separar completamente o domínio das dependências externas:

```
src/
├── domain/           # Núcleo — zero dependências externas
│   ├── models/       # Entidades (PurchaseOrder, Invoice, Conference)
│   ├── ports/        # Interfaces de repositório (ABCs)
│   └── services/     # Regras de negócio (InvoiceChecker, IngestionService…)
├── adapters/
│   ├── clients/      # Adapters por cliente (Alfa, Beta) — Strategy + Registry
│   └── persistence/  # Repositórios SQLAlchemy, cache Redis
├── api/              # Routers FastAPI, schemas Pydantic, middleware
└── infrastructure/   # Config (pydantic-settings), engine do banco, DI
```

Para os adapters de cliente usei **Strategy + Registry/Factory Method**: cada adapter (`AlfaAdapter`, `BetaAdapter`) implementa a interface `ClientAdapter` (Strategy) e se auto-registra num dicionário central ao ser importado (Registry). O endpoint de ingestão solicita o adapter pelo `client_id` e o Registry devolve a instância correta (Factory Method) — sem conhecer nenhum adapter concreto.

```python
# Cada adapter se registra ao ser importado:
ClientAdapterFactory.register("alfa", AlfaAdapter)

# O endpoint só conhece a interface:
adapter = ClientAdapterFactory.create(client_id)  # Factory Method
orders  = adapter.parse(raw_data)                  # Strategy
```

Adicionar um cliente novo = criar um arquivo e registrá-lo. Nenhum código existente precisa ser alterado.

### Stack

| Componente    | Escolha             | Motivo                                                           |
|---------------|---------------------|------------------------------------------------------------------|
| Framework     | FastAPI             | Async nativo, Pydantic v2 integrado, OpenAPI automático         |
| Banco         | PostgreSQL 16       | Constraints, índices compostos, NUMERIC para valores monetários |
| ORM           | SQLAlchemy 2 async  | Async-first, integra com Alembic, tipagem com `Mapped`          |
| Cache         | Redis               | TTL nativo, `flushdb` simples nos testes                        |
| Migrações     | Alembic             | Versionadas, rollback, autogenerate                             |
| Auth          | JWT + refresh token | Stateless para a API; refresh revogável no banco                |

---

## Modelo de dados

### `purchase_orders`

| Coluna         | Tipo            | Observação                                       |
|----------------|-----------------|--------------------------------------------------|
| id             | UUID PK         | Gerado pelo serviço                              |
| client_id      | VARCHAR(50) FK  | `alfa`, `beta`…                                  |
| po_number      | VARCHAR(100)    | Número original do cliente                       |
| status         | VARCHAR(10)     | `open`, `closed`, `blocked`                      |
| vendor_tax_id  | VARCHAR(14)     | CNPJ somente dígitos                             |
| loaded_at      | TIMESTAMPTZ     | Momento da última ingestão                       |
| **UNIQUE**     | (client_id, po_number) | Mesmo número pode existir em clientes diferentes |

**Índices:** `client_id`, `vendor_tax_id`, `status`, `loaded_at`.

### `purchase_order_items`

| Coluna            | Tipo          | Observação                                    |
|-------------------|---------------|-----------------------------------------------|
| quantity_ordered  | NUMERIC(15,3) | Sempre em unidades individuais                |
| quantity_received | NUMERIC(15,3) | Sempre em unidades individuais                |
| unit_price        | NUMERIC(15,4) | BRL por unidade individual                    |
| item_created_at   | DATE nullable | Data da linha — usado pelo Delta (Parte 2)    |

**Índice composto** `(purchase_order_id, material)` serve a busca da conferência de NF: dado um material da nota, encontra o item do pedido em uma única leitura de índice.

### `conferences` e `conference_divergences`

`purchase_order_id` é **nullable** — quando o pedido não é encontrado, a conferência é salva mesmo assim com `result=rejected` e `type=order_not_found`, garantindo histórico completo.

---

## Reingestão — o que acontece quando um pedido muda

Quando o mesmo `(client_id, po_number)` chega novamente:

1. O cabeçalho é atualizado (`UPDATE`)
2. Os itens são substituídos integralmente: DELETE dos anteriores + INSERT dos novos
3. O cache Redis daquele cliente é invalidado
4. A resposta retorna `updated: 1` e o campo `updates` com o diff campo a campo

**Por que substituição total dos itens em vez de merge?** Garante consistência com o estado atual do sistema do cliente — a carga sempre representa o snapshot mais recente. Conferências já realizadas não são afetadas porque a FK em `conferences` aponta para `purchase_orders.id`, não para itens.

---

## Regras de conferência

O `InvoiceChecker` aplica as regras na seguinte ordem:

| Verificação        | Regra                                                                 | Nível        |
|--------------------|-----------------------------------------------------------------------|--------------|
| `order_not_found`  | Combinação `(client_id, po_number)` não existe                        | Bloqueia tudo|
| `order_not_open`   | Status do pedido ≠ `open`                                             | Bloqueia tudo|
| `vendor_mismatch`  | CNPJ da NF ≠ CNPJ do pedido                                           | Continua     |
| `material_not_found`| Código de material da NF não existe nos itens do pedido              | Por item     |
| `quantity_exceeded`| Quantidade da NF > saldo pendente (`quantity_ordered - quantity_received`) | Por item |
| `price_mismatch`   | `|preço_unitário_NF - preço_pedido| >= R$ 0,01`                      | Por item     |

**Por que R$ 0,01 de tolerância no preço?** Notas fiscais e pedidos frequentemente têm diferenças de arredondamento de centavo em cálculos de rateio. Diferenças menores que R$ 0,01 por unidade são ruído contábil; iguais ou maiores indicam discordância real. O limite usa `>=`, ou seja, R$ 0,01 exato já rejeita.

**Por que `order_not_found` e `order_not_open` bloqueiam sem checar itens?** Sem pedido válido não há base de comparação para as regras subsequentes — checar itens geraria falsos positivos.

---

## Paginação

Adotei paginação **cursor-based** com keyset em `(loaded_at DESC, id DESC)` para pedidos e `(checked_at DESC, id DESC)` para conferências:

- Padrão: `page_size=20`, teto: `page_size=100`
- Cursor: token opaco em Base64 que codifica `{t: ISO datetime, id: UUID}` do último item retornado
- Resposta inclui `has_next`, `has_prev`, `next_cursor` — sem `COUNT(*)`, sem `total_pages`
- `has_next` determinado pelo truque `LIMIT N+1`: busca um registro a mais; se vier, há próxima página
- `has_prev = cursor is not None` (se chegou por cursor, há página anterior)

```json
{
  "data": [...],
  "pagination": {
    "page_size": 20,
    "has_next": true,
    "has_prev": false,
    "next_cursor": "eyJ0IjogIjIwMjYtMDgtMDVUMDM6MDA6MDAiLCAiaWQiOiAiYWJjMTIzIn0="
  }
}
```

**Por que cursor-based?** O enunciado descreve que a plataforma varre os pedidos em lote de madrugada *enquanto novas cargas dos clientes continuam entrando*. Esse é exatamente o cenário que causa page-drift no offset: um pedido inserido durante a varredura desloca os offsets e faz a plataforma pular ou duplicar registros. Com cursor-based, novos pedidos chegam com `loaded_at` mais recente (maior) e não interferem na varredura que caminha de trás para frente — nenhum registro é perdido ou repetido independentemente do volume de ingestões concorrentes.

---

## Normalização dos clientes

### Alfa Energia

JSON com itens aninhados — parse direto. Status já vem em inglês (`open`, `closed`, `blocked`).

### Beta Alimentos

Dois CSVs com separador `;` no padrão brasileiro:

- Números: `1.200,000` → `Decimal("1200.000")` (troca ponto/vírgula)
- Datas: `15/08/2026` → `2026-08-15`
- CNPJ: `12.345.678/0001-90` → `12345678000190` (remove máscara)
- Status: `EM ABERTO` → `open`, `BLOQUEADO` → `blocked`, `ENCERRADO` → `closed`

Itens cujo `NUMERO_PEDIDO` não corresponde a nenhum cabeçalho são descartados com um aviso explícito no campo `warnings` da resposta (em vez de falha silenciosa).

---

## Logs estruturados

Todos os logs usam [structlog](https://www.structlog.org/) no formato chave=valor (desenvolvimento) ou JSON (produção), controlado pela variável `LOG_FORMAT`.

Cada requisição recebe um `request_id` propagado em todos os logs daquele ciclo, permitindo rastrear o caminho completo de uma chamada. O nível do log HTTP varia com o status: `info` para 2xx/3xx, `warning` para 4xx, `error` para 5xx.

Pontos de log relevantes por fluxo:

- **Ingestão:** `ingest.start` → `ingest.order_created/updated` por pedido → `ingest.completed`
- **Conferência:** `conference.start` → cada `checker.*` que dispara → `conference.approved/rejected`
- **Consulta:** `order.get` (com `from_cache=true/false`) e `order.not_found`

---

## Cache

Pedidos individuais (`GET /purchase-orders/{client_id}/{po_number}`) são cacheados no Redis com TTL de 5 minutos. O header `X-Cache: HIT/MISS` indica a origem da resposta. O cache de um cliente é invalidado integralmente a cada ingestão, garantindo consistência.

