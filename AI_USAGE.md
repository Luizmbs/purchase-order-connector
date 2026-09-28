# AI_USAGE.md

## Ferramentas utilizadas

Utilizei o Claude Code como principal ferramenta de IA ao longo de todo o desenvolvimento. O uso foi conversacional e iterativo.

---

## Onde a IA foi utilizada

| Área | Como foi usado |
|---|---|
| Arquitetura | Discussão e validação das escolhas (hexagonal, Strategy + Registry) |
| Modelagem do banco | Definição de tabelas, índices e decisões de normalização |
| Adapters (Alfa, Beta, Gama, Delta) | Implementação guiada, com decisões de conversão discutidas antes do código |
| Services e regras de negócio | InvoiceChecker, IngestionService, lógica de upsert e diff |
| Testes unitários e de integração | Geração dos arquivos de teste com cobertura dos cenários relevantes |
| Logs estruturados | Definição dos eventos de log e níveis por tipo de resposta HTTP |
| README e documentação | Rascunho e revisões iterativas |

---

## Exemplo que funcionou bem

**Contexto:** precisava decidir entre paginação offset-based e cursor-based.

**Como foi:** questionei a IA sobre o trade-off depois de notar que o enunciado descrevia explicitamente o cenário de "varredura noturna com ingestões concorrentes". A IA explicou o problema do page-drift com um exemplo visual claro e confirmou que cursor-based em `(loaded_at, id)` resolveria sem custo de `COUNT(*)`.

**O que pedi (resumo do prompt):**
> "Olhando para isso agora. Qual seria o esforço para alterar a paginação para cursor-based? Acho que por ser um ponto explicitamente dito no texto, deveríamos olhar para isso."

**O que aproveitei:** a explicação do mecanismo de page-drift, a estrutura do keyset `WHERE (loaded_at, id) < (cursor_ts, cursor_id)`, o truque do `LIMIT N+1` para detectar `has_next` sem `COUNT(*)`, e a codificação do cursor em Base64 JSON. A implementação foi aplicada em repositórios, services, schemas e routers sem quebrar nenhum teste existente.

---

## Exemplo em que a IA errou ou levou por um caminho ruim

**O que aconteceu:** na primeira implementação dos itens órfãos do Delta, a IA descartava os itens diretamente no adapter com um `warning`, sem consultar o banco. O código funcionava para o caso do enunciado (payload completo), mas estava errado para o cenário real de ingestões incrementais.

**Como percebi:** ao fazer o review do código gerado percebi o comportamento de substituir todos os items do pedido pelos que estavam na requisição atual

**O que fizemos:** a validação de órfãos foi movida para o `IngestionService`, que tem acesso ao repositório. O adapter passou a devolver os itens sem dono em `ParseResult.orphan_items` (em vez de descartá-los), e o service decide: se o pedido existe no banco, mescla por linha; se não existe em nenhum lugar, aí sim descarta com warning.

**Lição:** a IA tende a tomar a decisão mais simples quando o escopo não é explicitado. Perguntar "e se o pedido já existir no banco?" antes de aceitar a implementação teria evitado o retrabalho.

---

## Como garanti que entendo o código entregue

- **Discussão antes da implementação:** cada decisão de arquitetura (padrão de paginação, estratégia de upsert, tratamento de órfãos) foi discutida em linguagem natural antes de virar código. Não aceitei implementação de algo que eu não conseguia explicar.
- **Leitura do código gerado:** todo arquivo criado ou modificado pela IA foi lido por mim. Em vários casos pedi explicações sobre trechos específicos.
- **Execução dos testes:** rodei a suite completa após cada mudança significativa. Os 187 testes passando ao final não são mérito só da IA — são o resultado de cenários que eu defini e validei.

