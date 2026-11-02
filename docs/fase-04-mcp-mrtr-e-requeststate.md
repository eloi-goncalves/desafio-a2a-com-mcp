---
fase: 04
titulo: "MCP — MRTR e requestState"
objetivo_uma_linha: "Fechar o ciclo MRTR na reserva: input_required com elicitation, requestState assinado e restart-safe, -32021, -32602 e recusa."
depende_de: [03]
habilita: [05, 07]
criterios_de_aceite_cobertos:
  - "Quando o intervalo pedido conflita com uma reserva existente, reservar_sala responde com resultType igual a input_required"
  - "O requestedSchema da elicitation é plano, com uma propriedade sala restrita às salas alternativas"
  - "O mesmo pedido, vindo de cliente que não declarou elicitation em form mode, recebe -32021 com data.requiredCapabilities e HTTP 400"
  - "O retry com inputResponses e requestState conclui a reserva e devolve resultType igual a complete"
  - "requestState adulterado recebe -32602"
  - "Um retry com argumentos adulterados não produz reserva com os valores adulterados"
  - "Um retry com requestState válido conclui a reserva mesmo que o processo do servidor MCP tenha sido reiniciado"
  - "A chave de integridade vem de REQUEST_STATE_SECRET, com no mínimo 32 bytes, e não há segredo hardcoded no código"
  - "Recusa com action igual a decline conclui sem reservar e sem isError"
  - "Conflito de horário em que nenhuma sala alternativa atende à regra: Sem alternativas disponiveis no intervalo"
testes_do_validador_cobertos: [13, 14, 15, 16, 17, 18, 19, 20]
artefatos_produzidos:
  - servidor-mcp/ (MRTR na reserva, cálculo de alternativas, selagem/verificação do requestState)
status: pendente
---

# Fase 04 — MCP: MRTR e requestState

## 1. Contexto e objetivo

A fase mais densa do servidor. Quando `reservar_sala` encontra conflito, em vez de erro ela **termina
a resposta** pedindo informação: `resultType: input_required`, com uma elicitation em form mode
restrita às salas alternativas, e um `requestState` **opaco e assinado**. No retry (id novo, com
`inputResponses` + `requestState`), o servidor reconstrói o pedido **a partir do próprio
`requestState`** e conclui. Trata `-32021` (sem capability), `-32602` (requestState adulterado/
expirado), recusa (`decline`) e "sem alternativas". Faz passar as **verificações 13 a 20**.

> **Fricção #1 — MRTR não é callback.** Não existe canal de volta. O servidor **não chama** o cliente.
> No SDK Python, o caminho se chama `input_required` (no de TS, `inputRequired`). Se você procurar
> como manter a chamada aberta esperando o usuário, está no caminho errado.

## 2. Fontes de verdade desta fase

- `exemplos/wire/03-...conflito-input-required.json` → forma do `input_required`: `inputRequests` com
  **uma** entrada (chave `__main__:escolha_de_sala`), `method: elicitation/create`, `params.mode:
  form`, `requestedSchema` plano com `sala.enum`; `requestState` com prefixo `v1.`.
- `exemplos/wire/04-tools-call-retry.json` → retry com `id` novo, `inputResponses` +
  `requestState` → reserva concluída (`structuredContent` completo).
- `exemplos/wire/06-erro-32021-sem-elicitation.json` → `clientCapabilities: {}` → HTTP 400,
  `error.code: -32021`, `data.requiredCapabilities: {"elicitation":{"form":{}}}`.
- `exemplos/wire/11-tools-call-retry-recusa.json` → `action: decline` → `complete`, `reservado:
  false`, `motivo: "recusado"`.
- `validador/validar.py` → checks 13–20, funções `reservar()`, `retomar()`; o check 17 adultera os 6
  últimos caracteres do `requestState`; o check 18 verifica que valores selados vencem.
- `docs/challenge.md` → **"2. O ciclo de MRTR na reserva"** e regra de **alternativas**.

## 3. Pré-condições

- Fase 03 concluída: validações, conflito detectável, reserva feliz e `structuredContent` prontos.
- `REQUEST_STATE_SECRET` disponível no ambiente (≥32 bytes). Verificar que o servidor **falha ao
  subir** se o segredo não existir (nunca usar default hardcoded).

## 4. Passo a passo de execução

1. **Cálculo das alternativas** (regra fechada): quando `reservar_sala` acha conflito, computar as
   salas **livres no intervalo** com **capacidade ≥** a da sala pedida, no **máx 3**, ordenadas por
   **capacidade crescente** e, em empate, por **id alfabético**.
   - Exemplo do validador (check 14): pedir `sala-garagem` (cap 12) 14:00→15:00. Livres com cap ≥ 12:
     `sala-fusca` (12) e `sala-mirante` (20) → enum `["sala-fusca", "sala-mirante"]`.
2. **Sem alternativa** (check 20): se a lista ficar vazia, **não** há elicitation — devolver
   `isError: true` com `Sem alternativas disponiveis no intervalo`.
3. **`input_required`** (checks 13, 14): devolver
   ```json
   {"resultType":"input_required",
    "inputRequests":{"<chave>":{"method":"elicitation/create",
      "params":{"mode":"form","message":"...",
        "requestedSchema":{"type":"object","required":["sala"],
          "properties":{"sala":{"type":"string","enum":[<alternativas>]}}}}}},
    "requestState":"<opaco assinado>"}
   ```
   - **Uma única** entrada em `inputRequests`. A **chave** é atribuída pelo servidor (livre; o SDK
     Python gera `__main__:escolha_de_sala`). `mode: form`. Com 1 alternativa, `const` é aceito no
     lugar de `enum`.
4. **Selar o `requestState`** (fricção #3): usar o **utilitário pronto do SDK** para assinar
   (HMAC/AEAD) com chave vinda de `REQUEST_STATE_SECRET`. O conteúdo carrega **tudo** para reconstruir
   o pedido original (sala pedida, inicio, fim, responsavel, chave da elicitation, alternativas) e uma
   **expiração entre 5 e 30 min**. O servidor **não guarda nada em memória** entre o `input_required`
   e o retry. Assinar é obrigatório; cifrar é opcional.
5. **Capability obrigatória** (fricção #2, check 15): antes de emitir a elicitation, verificar que o
   `_meta` do request declarou `{"elicitation":{"form":{}}}`. Se não: `error.code == -32021`, **HTTP
   400**, `data.requiredCapabilities = {"elicitation":{"form":{}}}`. Nada de elicitation nesse caso.
6. **Retry** (check 16): em `tools/call` com `params.inputResponses` + `params.requestState`:
   1. **Verificar a integridade** do `requestState` (SDK). Falhou/expirou → `error.code == -32602`
      (check 17).
   2. **Reconstruir** o pedido a partir do `requestState` selado. Ler a escolha do usuário em
      `inputResponses[<chave>]`.
   3. Se `action == accept`: reservar na sala escolhida (`content.sala`). Devolver `complete` com o
      `structuredContent` da reserva.
   4. Se `action == decline`/`cancel` (check 19): concluir **sem reservar**, `complete`, `isError`
      ausente/false, `structuredContent` com `reservado: false`, `motivo: "recusado"` (demais campos
      null — ver wire `11`).
7. **Argumentos adulterados no retry** (check 18): os `arguments` reenviados **não são confiáveis**.
   A divergência **não pode tomar efeito**: ou **rejeitar** o estado, ou **usar os valores selados**.
   O validador confirma que `inicio`/`responsavel` do resultado batem com o **selado**, não com o
   adulterado.
8. **Id do retry é independente.** O servidor não deve exigir nem reutilizar o id do request inicial
   (o agente, na Fase 07, mandará um id novo). Tratar cada request como independente.
9. **Restart-safe** (verificação manual): como o estado está **no `requestState`** (não em memória),
   um retry apresentado após reiniciar o servidor deve concluir normalmente, desde que o
   `REQUEST_STATE_SECRET` seja o mesmo.

## 5. Contratos e exemplos de wire aplicáveis

- **Conflito:** `exemplos/wire/03` (response → `result` com `inputRequests`, `requestState`,
  `resultType: input_required`).
- **Retry aceito:** `exemplos/wire/04` (id novo; `inputResponses.<chave>.action = accept`,
  `content.sala`; response com `structuredContent` completo).
- **Sem capability:** `exemplos/wire/06` (HTTP 400, `-32021`, `data.requiredCapabilities`).
- **Recusa:** `exemplos/wire/11` (`action: decline`; `reservado: false`, `motivo: "recusado"`).

## 6. Riscos e armadilhas

- **MRTR como callback** (fricção #1): o sintoma é um erro de "sem canal de volta". Use o caminho
  `input_required` do SDK, não elicitation síncrona.
- **`requestState` só base64** (fricção #3): atende o caminho feliz e **reprova** na adulteração. Tem
  que ser **assinado**. Teste você mesmo: trocar 1 caractere → `-32602`.
- **Segredo hardcoded**: reprova. `REQUEST_STATE_SECRET` do ambiente, ≥32 bytes, servidor falha sem ele.
- **Elicitation sem checar capability**: reprova o check 15. Checar **antes** de montar a elicitation.
- **Confiar nos `arguments` do retry** (check 18): usar os valores **selados**.
- **Guardar estado em memória** entre pausa e retry quebra o restart-safe. Todo estado vai no `requestState`.
- **Enum fora de ordem**: respeitar capacidade crescente, depois id alfabético.

## 7. Definição de Pronto (verificável)

- [ ] Conflito → `input_required`, 1 `inputRequests`, `requestState` presente (check 13).
- [ ] Enum na ordem `["sala-fusca","sala-mirante"]`, `mode: form` (check 14).
- [ ] Sem capability → `-32021` + `requiredCapabilities` + HTTP 400 (check 15).
- [ ] Retry aceito → `complete`, reserva na sala escolhida (check 16).
- [ ] `requestState` com 6 chars finais trocados → `-32602` (check 17).
- [ ] Argumentos adulterados não tomam efeito (selado vence) (check 18).
- [ ] `decline` → `complete`, `reservado: false`, `motivo: "recusado"` (check 19).
- [ ] Sem alternativa → `isError` + `Sem alternativas disponiveis no intervalo` (check 20).
- [ ] Retry conclui após **restart** do servidor (mesmo segredo) — teste manual.
- [ ] Nenhum segredo no código; servidor exige `REQUEST_STATE_SECRET`.

Comando de verificação:
```bash
python3 validador/validar.py --mcp http://localhost:7301 --agente http://localhost:7300 | sed -n '13,20p'
# restart-safe: capturar o requestState do wire 03, reiniciar o servidor, reenviar o retry → reserva
```

## 8. Sugestão de commit (pt-BR, Conventional Commits)

```
feat(mcp): ciclo mrtr na reserva com requestState assinado, -32021, -32602 e recusa
```
