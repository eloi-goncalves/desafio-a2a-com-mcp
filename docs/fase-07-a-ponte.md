---
fase: 07
titulo: "A ponte"
objetivo_uma_linha: "Costurar MCP e A2A: input_required vira TASK_STATE_INPUT_REQUIRED, o requestState fica guardado por Task e a retomada repete o tools/call com id novo."
depende_de: [04, 06]
habilita: [08]
criterios_de_aceite_cobertos:
  - "SendMessage pedindo sala ocupada deixa a Task em TASK_STATE_INPUT_REQUIRED com a linha alternativas: listando os ids na ordem do enum"
  - "A continuação com escolha=<id> conclui a Task em TASK_STATE_COMPLETED com a reserva na sala escolhida"
  - "A continuação com escolha=recusar termina a Task em TASK_STATE_CANCELED"
  - "Escolha fora do enum mantém a Task em TASK_STATE_INPUT_REQUIRED"
  - "Duas Tasks pausadas ao mesmo tempo concluem cada uma com a sua reserva, sem trocar de requestState"
  - "O requestState não aparece em nenhuma resposta A2A"
  - "O retry ao servidor MCP usa um id de JSON-RPC diferente do request inicial, e leva inputResponses com a mesma chave e o requestState ecoado sem modificação"
testes_do_validador_cobertos: [27, 28, 29, 30, 32, 33, 34, 36]
artefatos_produzidos:
  - agente/ (tradução input_required↔INPUT_REQUIRED, store de requestState por Task, retomada com id novo, recusa, isolamento por Task)
status: pendente
---

# Fase 07 — A ponte

## 1. Contexto e objetivo

O coração do desafio. Quando o servidor MCP responde `input_required`, o agente **não responde por
conta própria nem trava**: ele **pausa a Task** em `TASK_STATE_INPUT_REQUIRED`, devolve as
alternativas ao cliente A2A como a linha `alternativas: ...`, e **guarda o `requestState`** ligado
àquela Task. Na continuação (`escolha=<id>`), repete o `tools/call` original com **id de JSON-RPC
novo**, levando `inputResponses` e o `requestState` **ecoado sem modificação**, e conclui. É a
costura MCP↔A2A. Faz passar **27–30, 32–34 e 36**.

> **A única coisa que atravessa a fronteira é estado nomeado explicitamente.** No MCP, o
> `requestState`. No A2A, a `Task`. A ponte liga os dois.

## 2. Fontes de verdade desta fase

- `exemplos/wire/08-a2a-send-message.json` → sala ocupada → Task `TASK_STATE_INPUT_REQUIRED`, mensagem
  `alternativas: ...`.
- `exemplos/wire/09-a2a-get-task-input-required.json` → Task pausada no `GetTask` (sem artifact ainda).
- `exemplos/wire/10-a2a-send-message-continuacao.json` → continuação `escolha=<id>` → `COMPLETED` +
  artifact.
- `exemplos/wire/03`/`04`/`11` → o par MCP por baixo: `input_required` → retry com id novo /
  `action: decline`.
- `validador/validar.py` → checks 27–36: a linha exata `alternativas: sala-fusca, sala-mirante`
  (check 28), escolha fora do enum (29), conclusão (30), recusa→CANCELED (32), duas Tasks
  simultâneas (33), não-vazamento do `requestState` (34), determinismo (36).
- `docs/challenge.md` → **"5. A ponte"**.

## 3. Pré-condições

- Fase 04: o servidor MCP emite `input_required`, valida `requestState` e aceita retry com id novo.
- Fase 06: a máquina de estados da Task existe (`SUBMITTED/WORKING/COMPLETED/FAILED`) e o artifact
  `reserva` é produzido. Esta fase adiciona o estado `INPUT_REQUIRED` e o `CANCELED`.

## 4. Passo a passo de execução

1. **Receber `input_required`** do MCP ao chamar `reservar_sala` com conflito. Extrair do
   `inputRequests`: a **chave** (única) e o **enum** de `requestedSchema.properties.sala`; e o
   `requestState`.
2. **Pausar a Task** em `TASK_STATE_INPUT_REQUIRED` e devolver, como **mensagem de texto da Task**,
   **exatamente**:
   ```
   alternativas: <id1>, <id2>, ...
   ```
   na **mesma ordem do enum**, separados por **vírgula e espaço**, **sem prefixo, sem saudação**. O
   validador compara byte a byte (check 28: `alternativas: sala-fusca, sala-mirante`).
3. **Guardar o `requestState` por Task** num store em memória (`taskId → {requestState, chave,
   arguments originais, ...}`). O `requestState` é **opaco**: guardar e ecoar, **nunca** abrir. Ele
   **não** pode aparecer no card, no artifact, nem em nenhuma resposta A2A (check 34).
4. **Continuação `escolha=<id>`** (`SendMessage` com `taskId` + texto `escolha=<valor>`):
   - Se `<valor>` **não** está no enum guardado (check 29): manter a Task em `INPUT_REQUIRED` e
     **repetir** a linha `alternativas: ...`. Não chamar o MCP.
   - Se `<valor>` é `recusar` (check 32): montar o retry com `inputResponses[<chave>] = {"action":
     "decline"}` + `requestState`, enviar ao MCP, e terminar a Task em `TASK_STATE_CANCELED`.
   - Se `<valor>` é um id válido do enum (check 30): montar o retry com `inputResponses[<chave>] =
     {"action": "accept", "content": {"sala": "<valor>"}}` + `requestState` ecoado, **id de JSON-RPC
     novo** (diferente do request inicial), enviar ao MCP, receber `complete`, e terminar a Task em
     `TASK_STATE_COMPLETED` com o artifact `reserva` na sala escolhida.
5. **Id do retry é novo** (regra da spec): nunca reutilizar o id do `tools/call` inicial. O servidor
   trata como request independente.
6. **Isolamento por Task** (check 33): o estado pausado é **por Task**. Duas Tasks pausadas ao mesmo
   tempo guardam `requestState` próprios; cada continuação usa o `requestState` **da sua** Task. Elas
   concluem com **reservas distintas** (`reserva` e `inicio` diferentes), sem trocar de estado.
7. **Determinismo** (check 36): o mesmo pedido repetido produz a **mesma** linha de pausa
   (`alternativas: ...`). Nada de aleatoriedade na ordem ou no texto.
8. **Não-vazamento** (check 34): revisar todas as respostas A2A (`SendMessage`, `GetTask`) e o card
   para garantir que o `requestState` (nem um prefixo dele) aparece.

## 5. Contratos e exemplos de wire aplicáveis

- **Pausa:** `exemplos/wire/08` (response → `status.state: TASK_STATE_INPUT_REQUIRED`, `status.message`
  com `alternativas: ...`). **Nota:** o wire mostra `alternativas: sala-mirante` porque naquele
  cenário `sala-fusca` já estava ocupada; o validador, em estado limpo, espera
  `alternativas: sala-fusca, sala-mirante`. A linha é **sempre** derivada do enum da execução.
- **Retomada:** `exemplos/wire/10` (continuação → `COMPLETED`, artifact `reserva`). Por baixo, o MCP é
  o `exemplos/wire/04` (retry com id novo).
- **Recusa:** o MCP por baixo é `exemplos/wire/11` (`action: decline`).

## 6. Riscos e armadilhas

- **Linha de pausa com prefixo/saudação** → reprova o check 28 (comparação byte a byte). Só
  `alternativas: <ids>`.
- **Ordem das alternativas diferente do enum** → reprova. Preservar a ordem do enum.
- **Reaproveitar o id do retry** → reprova a verificação manual (ids iguais). Id novo sempre.
- **Vazar o `requestState`** em qualquer resposta A2A → reprova o check 34.
- **Compartilhar `requestState` entre Tasks** → reprova o check 33. Store por `taskId`.
- **Responder a elicitation no agente** (callback) → a Task nunca pausa. O agente devolve ao cliente A2A.
- **Escolha fora do enum avançando** → reprova o check 29. Manter pausada e repetir alternativas.

## 7. Definição de Pronto (verificável)

- [ ] Sala ocupada → `INPUT_REQUIRED` + `alternativas: sala-fusca, sala-mirante` (checks 27, 28).
- [ ] `escolha=sala-aquario` (fora do enum) mantém `INPUT_REQUIRED` (check 29).
- [ ] `escolha=sala-fusca` → `COMPLETED` na sala escolhida (check 30).
- [ ] `escolha=recusar` → `CANCELED` (check 32).
- [ ] Duas Tasks pausadas concluem com reservas distintas (check 33).
- [ ] `requestState` não aparece em nenhuma resposta A2A (check 34).
- [ ] Mesmo pedido → mesma pausa (check 36).
- [ ] Retry ao MCP usa id novo e `requestState` ecoado sem modificação (verificação manual no stderr).

Comando de verificação:
```bash
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301 | sed -n '27,36p'
```

## 8. Sugestão de commit (pt-BR, Conventional Commits)

```
feat(agente): ponte mcp-a2a com pausa da task, guarda do requestState por task e retomada com id novo
```
