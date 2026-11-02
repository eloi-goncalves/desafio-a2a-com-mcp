---
fase: 05
titulo: "Agente como host MCP"
objetivo_uma_linha: "Construir o agente como cliente MCP puro: descobre tools, lê o resource, monta _meta e headers, propaga traceparent e enxerga o input_required cru."
depende_de: [02, 04]
habilita: [06]
criterios_de_aceite_cobertos:
  - "O agente descobre as ferramentas por tools/list antes da primeira chamada, e não carrega uma lista fixa no código"
  - "O agente lê o resource politica://uso e extrai dele a versão declarada na primeira linha"
  - "Todo request MCP emitido pelo agente carrega os campos obrigatórios de _meta e declara a capability de elicitation em form mode"
  - "Todo request MCP emitido pelo agente carrega os headers que o transporte espelha do corpo"
  - "Quando o cliente A2A envia o header traceparent, o agente propaga o mesmo trace-id no traceparent dentro do _meta"
  - "Um erro de execução da tool, com isError: true, termina a Task em TASK_STATE_FAILED com a mensagem exata da tool"
testes_do_validador_cobertos: [35]
artefatos_produzidos:
  - agente/ (cliente MCP: descoberta, leitura de resource, montagem de _meta/headers, propagação de traceparent, tratamento de input_required cru)
status: pendente
---

# Fase 05 — Agente como host MCP

## 1. Contexto e objetivo

Construir o **miolo MCP do agente** antes de colocar o A2A por fora. O agente é um **cliente MCP de
verdade**, falando HTTP com o servidor da porta `7301`. Ele descobre as tools por `tools/list`, lê o
resource da política, extrai a versão, e sabe emitir `tools/call` com `_meta` e headers corretos,
propagando o `traceparent`. O ponto crítico: o agente precisa **enxergar o `input_required` cru** — se
usar um callback de elicitation do SDK, o cliente responde sozinho e a ponte (Fase 07) nunca pausa.
Nesta fase, validar o ciclo "na mão" (script que completa o MRTR) antes do A2A.

> **Fricção #1 (lado agente):** se o cliente MCP do SDK tiver um callback de elicitation, **não** o
> use para responder automaticamente. O agente precisa receber o `input_required` e devolvê-lo ao
> cliente A2A. Caso contrário, a Task nunca pausa e metade do desafio evapora.

## 2. Fontes de verdade desta fase

- `exemplos/wire/01-tools-list.json` → forma do request de descoberta (headers + `_meta`, incl.
  `clientInfo` e `clientCapabilities`).
- `exemplos/wire/05-resources-read-politica.json` → leitura do resource; extrair `versao: 2026-11-01`
  da **primeira linha** do texto.
- `exemplos/wire/03`/`04`/`11` → o agente deve reconhecer `resultType: input_required` e saber montar
  o retry (id novo, `inputResponses`, `requestState` ecoado) — a orquestração A2A disso é a Fase 07.
- `docs/challenge.md` → **"3. O agente como host MCP"**.
- `validador/validar.py` → função `mcp()` (headers e `_meta` que o validador usa como referência); o
  check 35 (sala inexistente → Task FAILED) exige que o `isError` da tool suba como falha.

## 3. Pré-condições

- Fase 02 (servidor responde `tools/list`, resource) e Fase 04 (servidor emite `input_required`,
  valida capability e `requestState`) concluídas.
- `MCP_URL` apontando para `http://localhost:7301/mcp`.

## 4. Passo a passo de execução

1. **Cliente MCP** apontado para o servidor por HTTP. Manter o objeto cliente vivo entre chamadas é
   **recomendado** (não é sessão de protocolo — o estado de protocolo continua por request).
2. **Descoberta por `tools/list`** **antes** da primeira `tools/call`. Não carregar lista fixa de
   tools no código. (Verificação: o stderr do servidor mostra um `tools/list` antes do 1º `tools/call`.)
3. **`_meta` em todo request**, montado por request (sem sessão):
   - `io.modelcontextprotocol/protocolVersion: "2026-07-28"`
   - `io.modelcontextprotocol/clientCapabilities: {"elicitation": {"form": {}}}` (sempre declarar)
   - opcional `io.modelcontextprotocol/clientInfo`
   - `traceparent` quando propagando trace (passo 6).
4. **Headers espelhados do corpo** em todo request:
   - `MCP-Protocol-Version: 2026-07-28`
   - `Mcp-Method: <método>`
   - `Mcp-Name: <nome da tool ou URI>` em `tools/call` e `resources/read`
   - `Accept: application/json, text/event-stream`
   Header que **não bate** com o corpo é recusado com `-32020` — garantir coerência.
5. **Ler o resource `politica://uso`** e **extrair a versão** da primeira linha (`versao: <valor>` →
   `2026-11-01`). Guardar para preencher o campo `politica` do artifact (Fase 06).
6. **Propagar `traceparent`**: quando o cliente A2A enviar o header `traceparent`, o agente usa o
   **mesmo trace-id** no `traceparent` dentro do `_meta` de **todos** os requests MCP daquela Task. O
   span-id pode ser novo; o **trace-id não muda**. (O validador imprime o trace-id na 1ª linha; ele
   deve aparecer no stderr do servidor.)
7. **Enxergar o `input_required` cru**: ao chamar `reservar_sala` e receber `resultType:
   input_required`, **não** responder automaticamente. Expor o `inputRequests` (chave + enum) e o
   `requestState` para a camada A2A guardar e retomar (Fase 07).
8. **Erro de execução → falha** (check 35, materializado na Fase 06): quando a tool devolve `isError:
   true`, o agente deve **propagar a mensagem exata** para que a Task termine em `TASK_STATE_FAILED`
   com esse texto no histórico. Aqui, garantir que o agente **lê e preserva** a mensagem de `isError`.
9. **Validação "na mão"** (sem A2A ainda): um script que descobre as tools, lê o resource, faz uma
   reserva livre, provoca um conflito, recebe o `input_required`, monta o retry com **id novo** e
   `requestState` ecoado, e conclui. Isso prova o miolo MCP antes de montar o A2A.

## 5. Contratos e exemplos de wire aplicáveis

- Requests do agente devem ser indistinguíveis, em forma, dos requests dos wire `01`–`05` (mesmos
  headers, mesmo `_meta`).
- O retry montado pelo agente deve espelhar `exemplos/wire/04` (id novo, `inputResponses` com a
  **mesma chave**, `requestState` **ecoado sem modificação**).

## 6. Riscos e armadilhas

- **Callback de elicitation** respondendo sozinho → a Task nunca pausa. O agente precisa do
  `input_required` cru.
- **Lista de tools hardcoded** → reprova o critério de descoberta. Sempre `tools/list` primeiro.
- **Abrir/interpretar o `requestState`** → proibido. Guardar e ecoar, nunca decodificar.
- **Header divergente do corpo** → `-32020`. Manter `Mcp-Method`/`Mcp-Name` coerentes.
- **Esquecer de propagar o trace-id** → reprova a verificação manual do stderr.
- **Perder a mensagem de `isError`** → a Task não consegue ir a FAILED com o texto certo (check 35).

## 7. Definição de Pronto (verificável)

- [ ] O agente faz `tools/list` antes do 1º `tools/call` (visível no stderr do servidor).
- [ ] Todo request do agente carrega `_meta` com `elicitation.form` e os headers espelhados.
- [ ] O agente lê `politica://uso` e extrai `2026-11-01`.
- [ ] Com `traceparent` recebido, o mesmo trace-id aparece no stderr do servidor MCP.
- [ ] Um script host-MCP completa o MRTR na mão (reserva, conflito, retry com id novo, conclusão).
- [ ] A mensagem de `isError` é preservada para uso na Fase 06.

Comando de verificação:
```bash
# com o servidor-mcp no ar, rodar o script host-MCP do agente e observar o stderr do servidor:
# deve aparecer tools/list antes do primeiro tools/call, e o traceparent propagado.
```

## 8. Sugestão de commit (pt-BR, Conventional Commits)

```
feat(agente): host mcp com descoberta, leitura de resource, _meta/headers e propagacao de traceparent
```
