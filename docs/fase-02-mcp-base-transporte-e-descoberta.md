---
fase: 02
titulo: "MCP base — transporte e descoberta"
objetivo_uma_linha: "Servir Streamable HTTP na 7301 com validação de _meta, tools/list, listar_salas, o resource da política e log em stderr."
depende_de: [01]
habilita: [03, 05]
criterios_de_aceite_cobertos:
  - "Sobe na porta 7301 em Streamable HTTP e responde a tools/list com as três tools"
  - "Toda tool tem inputSchema que é um objeto JSON Schema válido"
  - "listar_salas devolve structuredContent conforme o outputSchema declarado e o mesmo JSON serializado em bloco de texto"
  - "Request sem io.modelcontextprotocol/protocolVersion ou sem io.modelcontextprotocol/clientCapabilities recebe -32602 com HTTP 400"
  - "tools/call de tool inexistente é recusado, por -32602 ou por isError"
  - "resources/read de politica://uso devolve o conteúdo de dados/politica-de-uso.md, e de URI inexistente devolve -32602"
  - "O stderr do processo registra método, id e traceparent de cada request"
testes_do_validador_cobertos: [1, 2, 3, 4, 5, 6, 7, 8]
artefatos_produzidos:
  - servidor-mcp/ (transporte Streamable HTTP, declaração de tools/resources, listar_salas, resource politica://uso, logging)
status: pendente
---

# Fase 02 — MCP base: transporte e descoberta

## 1. Contexto e objetivo

Levantar o servidor MCP real: transporte Streamable HTTP em `/mcp` na `7301`, validação estrita dos
campos obrigatórios de `_meta`, declaração de capabilities (`tools` e `resources`), as **três** tools
registradas (com `inputSchema` objeto válido), a tool `listar_salas` funcional, o resource
`politica://uso`, e o log em stderr. As regras de negócio da reserva ficam para a Fase 03; aqui
`consultar_disponibilidade` e `reservar_sala` podem estar **declaradas** (para o `tools/list`) mas a
lógica delas é das próximas fases. Esta fase faz passar as **verificações 1 a 8**.

## 2. Fontes de verdade desta fase

- `exemplos/wire/01-tools-list.json` → forma exata do `tools/list`: `resultType: complete`, cada tool
  com `name`, `description`, `inputSchema.type == "object"`; `listar_salas` e
  `consultar_disponibilidade` com `outputSchema` declarado.
- `exemplos/wire/05-resources-read-politica.json` → `resources/read politica://uso` →
  `contents[0]` com `mimeType: text/markdown`, `text` igual ao conteúdo de `dados/politica-de-uso.md`.
- `validador/validar.py` → função `mcp(...)` (monta `_meta` e headers), checks **1–8** e `omitir`.
- `docs/challenge.md` → **Requisitos / 1. Servidor MCP**.
- `dados/salas.json` → dados de `listar_salas`.

## 3. Pré-condições

- Fase 01 concluída: `servidor-mcp/` sobe na `7301`.
- Verificar o transporte esperado: headers `MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` e `Accept:
  application/json, text/event-stream` (ver qualquer wire de request).

## 4. Passo a passo de execução

1. **Transporte Streamable HTTP** em endpoint único `/mcp`, porta `7301` (parametrizável por env).
2. **Validação de `_meta` por request, sem sessão.** Para **todo** request, exigir em `params._meta`:
   - `io.modelcontextprotocol/protocolVersion` (valor `2026-07-28`)
   - `io.modelcontextprotocol/clientCapabilities`
   Se **qualquer um** faltar: responder `error.code == -32602` **e HTTP 400**. Não inferir de request
   anterior. (checks 4, 5 — o validador omite um de cada vez via `omitir=`.)
3. **Declarar capabilities** de `tools` e `resources` na inicialização do servidor.
4. **Registrar as três tools** com `inputSchema` objeto JSON Schema válido (check 2):
   - `listar_salas`: sem parâmetros → `inputSchema` `{"type":"object","properties":{}}`.
   - `consultar_disponibilidade`: `sala`, `inicio`, `fim` (todos string, required).
   - `reservar_sala`: `sala`, `inicio`, `fim`, `responsavel`.
   Declarar `outputSchema` em `listar_salas` (objeto com `salas: [SalaOut]`) e em
   `consultar_disponibilidade` (`sala`, `livre`, `conflitos`), conforme wire `01`.
5. **`tools/list`** deve devolver as 3 tools (check 1), com `resultType: complete`.
6. **`listar_salas`** (check 3): devolver **ao mesmo tempo**:
   - `structuredContent` conforme o `outputSchema` (`{"salas":[{id,nome,capacidade,recursos}, ...]}`
     com as 5 salas de `dados/salas.json`);
   - um **bloco de texto** em `content[].text` cujo `json.loads` seja **idêntico** ao
     `structuredContent`. O validador faz `json.loads(bloco) == structuredContent`.
7. **Tool inexistente** (check 6): `tools/call` de nome desconhecido deve ser **recusado** — por
   `error.code == -32602` **ou** por `result.isError == true`. Ambos aceitos.
8. **Resource `politica://uso`** (checks 7, 8): `resources/read` devolve `contents: [{uri, mimeType:
   "text/markdown", text: <conteúdo de dados/politica-de-uso.md>}]`. O texto deve conter
   `versao: 2026-11-01`. `resources/read` de URI inexistente (ex.: `politica://inexistente`) →
   `error.code == -32602`. **Proibido** devolver `contents` vazio.
9. **Log em stderr** por request: no mínimo **método**, **id** e **`traceparent`** (quando vier no
   `_meta`). Usar stderr, não o logging depreciado de stdout do protocolo.

## 5. Contratos e exemplos de wire aplicáveis

- **`tools/list`**: reproduzir a forma de `exemplos/wire/01-tools-list.json` (response → `result.tools`).
- **`resources/read`**: reproduzir `exemplos/wire/05-resources-read-politica.json` (response →
  `result.contents[0]` com `mimeType: text/markdown` e o texto da política terminando em `\n`).
- Headers de request esperados (espelho do corpo): `MCP-Protocol-Version: 2026-07-28`,
  `Mcp-Method: <método>`, e `Mcp-Name` em `tools/call`/`resources/read`.

## 6. Riscos e armadilhas

- **Inferir `_meta` de request anterior** (sessão) → reprova os checks 4/5. Validar sempre, por request.
- **`structuredContent` divergindo do bloco de texto** → reprova o check 3. Serializar o **mesmo**
  objeto para os dois.
- **HTTP 200 com erro de `_meta`**: o validador exige **HTTP 400** junto do `-32602`.
- **`contents` vazio** em `resources/read` é proibido pela spec; URI inexistente é `-32602`, não lista vazia.
- Esquecer o **log em stderr** quebra a verificação manual do avaliador (traceparent).

## 7. Definição de Pronto (verificável)

- [ ] `tools/list` devolve as 3 tools, todas com `inputSchema.type == "object"`.
- [ ] `listar_salas`: `json.loads(bloco_texto) == structuredContent`, com as 5 salas.
- [ ] `_meta` sem `protocolVersion` → `-32602` + HTTP 400; idem sem `clientCapabilities`.
- [ ] `tools/call` de tool inexistente → `-32602` ou `isError: true`.
- [ ] `resources/read politica://uso` contém `versao: 2026-11-01`; URI inexistente → `-32602`.
- [ ] stderr mostra método, id e `traceparent` por request.

Comando de verificação (parcial, só a faixa MCP inicial):
```bash
# subir o servidor-mcp e rodar o validador; as verificações 1-8 devem dar PASS
python3 validador/validar.py --mcp http://localhost:7301 --agente http://localhost:7300 | sed -n '1,8p'
```

## 8. Sugestão de commit (pt-BR, Conventional Commits)

```
feat(mcp): transporte streamable http, descoberta de tools, resource da politica e log em stderr
```
