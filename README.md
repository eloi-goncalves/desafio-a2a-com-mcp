# A Ponte: um agente A2A com MCP por dentro

Entrega do desafio **A Ponte** da Hill Valley Tech: um **servidor MCP** (Streamable HTTP) que expõe
as salas de reunião, e um **agente** que é **host MCP por dentro** e **servidor A2A por fora**. A
costura entre os dois — o `input_required` do MCP virando `TASK_STATE_INPUT_REQUIRED` no A2A, com o
`requestState` guardado por Task — é a ponte que dá nome ao desafio.

- **Servidor MCP** (`servidor-mcp/`): SDK oficial do MCP **v2 (`mcp==2.3.0`, revisão 2026-07-28)**.
  Três tools, um resource, os dois tipos de erro e o ciclo completo de MRTR.
- **Agente** (`agente/`): cliente MCP puro (JSON-RPC sobre HTTP, só biblioteca padrão) + servidor A2A
  (JSON-RPC 1.0). **Sem LLM**: decide por regra, de forma determinística.

## Como rodar

A partir de um clone limpo (Python 3.10+):

```bash
# 1. Ambiente e dependências do servidor MCP (o agente usa só a biblioteca padrão).
python3 -m venv .venv
.venv/bin/pip install mcp==2.3.0

# 2. Segredo de integridade do requestState (>= 32 bytes). NUNCA comite este valor.
export REQUEST_STATE_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

Em **dois terminais separados** (o mesmo `REQUEST_STATE_SECRET` precisa estar exportado no terminal
do servidor MCP):

```bash
# Terminal 1 — servidor MCP (porta 7301, /mcp), com o stderr visível
./subir-mcp.sh

# Terminal 2 — agente A2A (porta 7300: /a2a e /.well-known/agent-card.json)
./subir-agente.sh
```

Rodar o validador (com os dois processos recém-iniciados):

```bash
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
```

> As reservas ficam em memória; **reinicie os dois processos antes de cada execução** do validador,
> senão as reservas de uma execução alteram a seguinte. O atalho `bash scripts/validar-e2e.sh` sobe
> tudo do zero, roda o validador e derruba os processos.

Variáveis de ambiente (ver `.env.example`): `REQUEST_STATE_SECRET` (obrigatória), `MCP_PORT` (7301),
`AGENTE_PORT` (7300), `MCP_URL` (`http://localhost:7301/mcp`).

## Onde a ponte acontece

A ponte está no agente, em [agente/agent.py](agente/agent.py):

- O `input_required` do MCP vira `TASK_STATE_INPUT_REQUIRED` em `_tratar_resposta_mcp`: ao receber
  `resultType == "input_required"` do servidor, o agente extrai o `enum` de alternativas e o
  `requestState`, **guarda o `requestState` por Task** no dicionário `_PAUSAS[task_id]` (nunca
  exposto em nenhuma resposta A2A) e pausa a Task devolvendo a linha exata `alternativas: <ids>`.
- O `requestState` volta para o servidor em `_continuar` → `mcp_retry`: na continuação
  (`escolha=<id>`), o agente repete o `tools/call` original com um **id de JSON-RPC novo** (cada
  `mcp_call` gera um id fresco), levando `inputResponses` com a mesma chave e o `requestState`
  **ecoado sem modificação**. `escolha=recusar` vira `action: decline` e encerra a Task em
  `TASK_STATE_CANCELED`.

Do lado do servidor [servidor-mcp/server.py](servidor-mcp/server.py), o resolver
`escolha_de_sala` é o ponto do MRTR: intervalo livre reserva direto; ocupado com alternativas emite a
elicitation em form mode (o SDK sela o `requestState`); ocupado sem alternativa devolve o erro de
execução.

## Decisões técnicas

- **Stack.** Servidor no **SDK oficial do MCP v2 (`mcp==2.3.0`)**, a versão alinhada à revisão
  `2026-07-28` da spec — ela traz o MRTR de primeira classe (`input_required`, `inputRequests`,
  `requestState`) e o Streamable HTTP. Os exemplos de `exemplos/wire/` foram capturados dessa mesma
  stack (chave `__main__:escolha_de_sala`, `requestState` com prefixo `v1.`). O agente usa **apenas a
  biblioteca padrão** do Python: um cliente MCP raw (JSON-RPC sobre HTTP) é o que permite enxergar o
  `input_required` cru e ecoar o `requestState` opaco, sem um callback de elicitation respondendo
  sozinho — exatamente o que a ponte exige. Nenhuma dependência de provedor de LLM.
- **Proteção do `requestState`.** Delegada ao `RequestStateSecurity(keys=[REQUEST_STATE_SECRET])` do
  SDK: **AES-256-GCM** (assina e cifra), com _request binding_ (um retry com argumentos adulterados
  não toma efeito) e expiração. A chave vem **só** da variável de ambiente `REQUEST_STATE_SECRET`
  (mínimo 32 bytes), nunca do código. Uma adulteração de qualquer caractere é rejeitada com `-32602`.
- **Validade e restart.** O `requestState` vale **15 minutos** (`ttl=900`, dentro da janela de 5 a 30
  min exigida). Como todo o estado do MRTR viaja selado no `requestState` (o servidor não guarda nada
  em memória entre o `input_required` e o retry), um retry continua válido **mesmo após reiniciar o
  servidor MCP**, desde que o `REQUEST_STATE_SECRET` seja o mesmo.
- **Estado das Tasks.** Guardado em memória no agente, por `taskId` (`_TASKS` e `_PAUSAS` em
  [agente/agent.py](agente/agent.py)), protegido por lock. O estado pausado é por Task: duas Tasks em
  conflito ao mesmo tempo terminam cada uma com a sua reserva, sem trocar de `requestState`. Reservas
  ficam em memória no servidor MCP e não sobrevivem a restart (por contrato).
- **Determinismo.** O agente não usa LLM: o pedido chega em formato fixo e a decisão é por regra.
  Conflito, política e alternativas são decisão exclusiva do servidor MCP; o agente traduz protocolo,
  não domínio.

## Saída do validador

Última execução, com os dois processos recém-iniciados (`exit code 0`):

```
trace-id desta execucao: 73574e886b69dec60f86400361f44713
procure esse valor no stderr do servidor MCP para conferir a propagacao do traceparent.

PASS 01 tools/list traz as tres tools
PASS 02 toda tool tem inputSchema de objeto
PASS 03 listar_salas devolve structuredContent e o mesmo JSON em texto
PASS 04 _meta sem protocolVersion devolve -32602 e HTTP 400
PASS 05 _meta sem clientCapabilities devolve -32602 e HTTP 400
PASS 06 tool inexistente e recusada, por -32602 ou por isError
PASS 07 resources/read de politica://uso devolve a politica
PASS 08 resources/read de URI inexistente devolve -32602
PASS 09 sala inexistente devolve isError com a mensagem exata
PASS 10 fora da janela devolve isError com a mensagem exata
PASS 11 duracao acima de 2h devolve isError com a mensagem exata
PASS 12 intervalo invertido devolve isError com a mensagem exata
PASS 13 conflito devolve input_required com inputRequests e requestState
PASS 14 a elicitation e form mode e oferece as alternativas na ordem certa
PASS 15 conflito sem a capability elicitation devolve -32021 e HTTP 400
PASS 16 retry com inputResponses e requestState conclui a reserva
PASS 17 requestState adulterado e rejeitado com -32602
PASS 18 argumentos adulterados no retry nao tomam efeito
PASS 19 recusa conclui sem reservar e sem isError
PASS 20 conflito sem alternativa possivel devolve isError com a mensagem exata

PASS 21 agent card responde 200 no well-known com JSON
PASS 22 o card declara a interface JSON-RPC com url e versao 1.0
PASS 23 o card declara a skill reservar-sala
PASS 24 SendMessage com sala livre conclui a Task
PASS 25 o artifact chama reserva e traz a versao da politica
PASS 26 GetTask devolve id, contextId e estado corrente
PASS 27 SendMessage com sala ocupada pausa a Task
PASS 28 a Task pausada lista as alternativas na ordem certa
PASS 29 escolha fora do enum mantem a Task pausada
PASS 30 a continuacao conclui a Task na sala escolhida
PASS 31 SendMessage em Task terminal e recusado
PASS 32 a recusa termina a Task em CANCELED
PASS 33 duas Tasks pausadas ao mesmo tempo concluem cada uma com a sua reserva
PASS 34 nenhuma resposta A2A carrega o requestState
PASS 35 sala inexistente termina a Task em FAILED com a mensagem da tool
PASS 36 o agente e deterministico: o mesmo pedido produz a mesma pausa

resumo: 36 passaram, 0 falharam, de 36 verificacoes
```

## Estrutura

```
servidor-mcp/        servidor MCP (SDK oficial mcp v2)
  server.py          MCPServer, tools, resource, resolver do MRTR, run streamable-http
  dominio.py         dados fixos, validacoes, regra de alternativas, modelos
agente/              agente A2A + cliente MCP (biblioteca padrao)
  agent.py           Agent Card, SendMessage/GetTask, maquina de estados da Task, a ponte
dados/               dominio fixo (nao alterado)
validador/           validador oficial (nao alterado)
exemplos/            wire dos dois protocolos (nao alterado)
subir-mcp.sh         sobe o servidor MCP (exige REQUEST_STATE_SECRET)
subir-agente.sh      sobe o agente
scripts/validar-e2e.sh  sobe tudo, roda o validador e derruba
```
