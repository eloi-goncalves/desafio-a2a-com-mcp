---
fase: 06
titulo: "Agente como servidor A2A"
objetivo_uma_linha: "Publicar o Agent Card v1.0 e o endpoint /a2a com SendMessage/GetTask, a máquina de estados da Task e o artifact reserva."
depende_de: [05]
habilita: [07]
criterios_de_aceite_cobertos:
  - "GET /.well-known/agent-card.json responde 200 com um card v1.0 válido"
  - "O card declara a interface JSON-RPC com a URL do endpoint e a versão de protocolo 1.0, e uma skill de id reservar-sala"
  - "SendMessage com sala livre termina a Task em TASK_STATE_COMPLETED com o artifact reserva"
  - "O artifact traz a reserva criada e o campo politica com o valor lido do resource"
  - "GetTask devolve id, contextId, estado corrente e o artifact quando existir"
  - "SendMessage referenciando Task em estado terminal é recusado com erro"
  - "SendMessage pedindo uma sala inexistente termina a Task em TASK_STATE_FAILED, com a mensagem exata da tool visível no histórico"
testes_do_validador_cobertos: [21, 22, 23, 24, 25, 26, 31, 35]
artefatos_produzidos:
  - agente/ (Agent Card, endpoint /a2a, SendMessage/GetTask, máquina de estados da Task, artifact reserva)
status: pendente
---

# Fase 06 — Agente como servidor A2A

## 1. Contexto e objetivo

Expor o agente ao mundo por fora. Publicar o **Agent Card v1.0** no well-known URI, e o endpoint
`/a2a` (JSON-RPC) com `SendMessage` e `GetTask`. Implementar a **máquina de estados da Task**
(`SUBMITTED → WORKING → COMPLETED|FAILED`; o `INPUT_REQUIRED` entra na Fase 07), o parsing do pedido
em formato fixo, a produção do **artifact `reserva`** (com o campo `politica`), e a recusa de Task em
estado terminal. Usa o host MCP da Fase 05 para executar a reserva. Faz passar **21–26, 31 e 35**.

## 2. Fontes de verdade desta fase

- `exemplos/wire/07-a2a-agent-card.json` → card exato: `supportedInterfaces[]` com `url`,
  `protocolBinding: "JSONRPC"`, `protocolVersion: "1.0"`; `skills[].id: "reservar-sala"`;
  `capabilities.streaming: false`; `defaultInputModes: ["text/plain"]`.
- `exemplos/wire/08-a2a-send-message.json` → forma do `SendMessage` (`params.message` com `messageId`,
  `role: ROLE_USER`, `parts[].text`, opcional `taskId`).
- `exemplos/wire/09-a2a-get-task-input-required.json` → forma da Task em `GetTask` (`id`, `contextId`,
  `status.state`, `status.message`, `history[]`, `artifacts[]`).
- `exemplos/wire/10-a2a-send-message-continuacao.json` → forma do artifact `reserva` (campo
  `politica`) e do `history`.
- `validador/validar.py` → checks 21–26, 31, 35; funções `enviar()`, `tarefa_de()`, `estado()`,
  `mensagem()`, `grafia_card()` (dicas de erro do card).
- `docs/challenge.md` → **"4. O agente como servidor A2A"**.

## 3. Pré-condições

- Fase 05 concluída: o agente consegue descobrir tools, reservar via MCP e ler a versão da política.
- Porta `7300`, endpoints `/a2a` e `/.well-known/agent-card.json`.

## 4. Passo a passo de execução

1. **Agent Card** em `GET /.well-known/agent-card.json` (HTTP 200, JSON v1.0). Campos essenciais
   (ver wire `07`):
   - `name`, `description`, `version`.
   - `supportedInterfaces: [{"url": "http://<host>:7300/a2a", "protocolBinding": "JSONRPC",
     "protocolVersion": "1.0"}]`. **Atenção:** na v1.0 é `supportedInterfaces` (não `interfaces`),
     o transporte é `protocolBinding` (não `preferredTransport`), e `url`/versão vivem **dentro** da
     interface. O `grafia_card()` do validador dá exatamente essas dicas se errar.
   - `capabilities: {streaming: false, pushNotifications: false, extendedAgentCard: false}`.
   - `skills: [{"id": "reservar-sala", ...}]`.
2. **Endpoint `/a2a`** (JSON-RPC 2.0): aceitar os métodos `SendMessage` e `GetTask`.
3. **Parsing do pedido** (formato fixo, sem LLM): `reservar sala=<id> inicio=<iso8601> fim=<iso8601>
   responsavel=<nome>`. Extração determinística por regra.
4. **`SendMessage` sem `taskId`** abre uma Task **nova** com `id` e `contextId` próprios. A Task
   transita por `TASK_STATE_SUBMITTED` e `TASK_STATE_WORKING` antes de terminar (`GetTask` reflete o
   estado corrente a qualquer momento).
5. **Caminho feliz** (checks 24, 25): sala livre → o agente chama `reservar_sala` via MCP, recebe
   `complete`, e termina a Task em `TASK_STATE_COMPLETED` com um **artifact**:
   - `name: "reserva"`, `parts[].text` = JSON da reserva **incluindo `politica`** com a versão lida do
     resource (`2026-11-01`) e a `sala` reservada. Ver wire `10` (artifact `reserva`).
6. **`GetTask`** (check 26): devolver `{task: {id, contextId, status.state, history, artifacts}}`,
   refletindo o estado corrente e o artifact quando existir.
7. **Estado terminal é definitivo** (check 31): uma Task `COMPLETED`/`CANCELED`/`FAILED` **não volta**
   a `WORKING`. Um `SendMessage` referenciando Task terminal é **recusado com `error`** JSON-RPC.
8. **Sala inexistente → FAILED** (check 35): quando a tool devolve `isError: true` (ex.: `Sala
   inexistente: sala-delorean`), terminar a Task em `TASK_STATE_FAILED` com a **mensagem exata** da
   tool visível no `history`/`status.message`.
9. **Histórico e mensagens**: cada mensagem do agente usa `role: ROLE_AGENT`, com `taskId`/`contextId`
   preenchidos. O `history` acumula as mensagens do usuário e do agente (ver wire `09`/`10`).

## 5. Contratos e exemplos de wire aplicáveis

- **Card:** reproduzir `exemplos/wire/07` (campos e grafia v1.0).
- **Task concluída / artifact:** `exemplos/wire/10` (artifact `name: "reserva"`, JSON com `politica`).
- **GetTask:** `exemplos/wire/09` (estrutura `result.task`).
- **SendMessage:** `exemplos/wire/08` (estrutura `params.message`).

## 6. Riscos e armadilhas

- **Grafia v0.x no card** (`interfaces`, `preferredTransport`, `additionalInterfaces`) → reprova o
  check 22. Usar `supportedInterfaces[].protocolBinding`/`protocolVersion`.
- **Artifact sem `politica`** ou com nome diferente de `reserva` → reprova o check 25.
- **Task terminal reaberta** → reprova o check 31. Estado terminal é imutável.
- **Mensagem de erro perdida** no caminho FAILED → reprova o check 35. Propagar o texto exato da tool.
- **Implementar regra de sala no agente**: proibido. Conflito/política/alternativas são do servidor
  MCP; o agente **traduz protocolo**.
- **LLM no parsing**: proibido. Parsing por regra, determinístico.

## 7. Definição de Pronto (verificável)

- [ ] `GET /.well-known/agent-card.json` → 200, card v1.0 válido (check 21).
- [ ] Card com interface JSON-RPC (url + `protocolVersion: 1.0`) e skill `reservar-sala` (checks 22, 23).
- [ ] `SendMessage` sala livre → `COMPLETED` + artifact `reserva` com `politica` e `sala` (checks 24, 25).
- [ ] `GetTask` devolve id, contextId, estado e artifact (check 26).
- [ ] `SendMessage` em Task terminal → `error` (check 31).
- [ ] `SendMessage` sala inexistente → `FAILED` com `Sala inexistente: ...` no histórico (check 35).

Comando de verificação:
```bash
curl -s http://localhost:7300/.well-known/agent-card.json | python3 -m json.tool
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301 | sed -n '21,26p;31p;35p'
```

## 8. Sugestão de commit (pt-BR, Conventional Commits)

```
feat(agente): agent card v1.0, endpoint a2a com sendmessage/gettask e artifact reserva
```
