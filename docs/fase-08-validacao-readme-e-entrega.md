---
fase: 08
titulo: "Validação, README e entrega"
objetivo_uma_linha: "Rodar as 36 verificações do zero, cobrir o fluxo manual do avaliador, escrever o README das 4 seções e publicar na main do fork."
depende_de: [01, 02, 03, 04, 05, 06, 07]
habilita: []
criterios_de_aceite_cobertos:
  - "python3 validador/validar.py passa nas 36 verificações, com os dois processos recém-iniciados, e termina com código de saída 0"
  - "dados/, validador/ e exemplos/ não foram alterados"
  - "O agente é determinístico: o mesmo pedido, enviado duas vezes, produz o mesmo resultado"
  - "O README tem as quatro seções exigidas, e os comandos funcionam a partir de um clone limpo"
testes_do_validador_cobertos: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36]
artefatos_produzidos:
  - README.md (substituído, com as 4 seções obrigatórias)
status: pendente
---

# Fase 08 — Validação, README e entrega

## 1. Contexto e objetivo

Fechar a entrega. Rodar o validador **inteiro** com os dois processos recém-subidos, cobrir as duas
exigências que ficam fora do validador automático (restart do MCP e `traceparent` no stderr),
escrever o **README** com as quatro seções obrigatórias e a saída do validador colada, confirmar que
o starter protegido está intacto e publicar na `main` do fork. Esta fase revalida as **36
verificações**.

## 2. Fontes de verdade desta fase

- `validador/validar.py` e `validador/README.md` → como rodar e por que reiniciar os processos.
- `docs/challenge.md` → **"6. README"**, **"Fluxo do avaliador"**, **"Critérios de Aceite /
  Validação e entrega"**, **"Regras de entrega"**.
- Todas as fases anteriores (01–07).

## 3. Pré-condições

- Fases 01–07 concluídas. Os dois processos sobem e o fluxo ponta a ponta funciona.
- `REQUEST_STATE_SECRET` exportado no ambiente antes de subir o servidor MCP.

## 4. Passo a passo de execução

1. **Subir do zero**: matar processos antigos, subir o servidor MCP (`7301`, stderr visível) e o
   agente (`7300`), cada um em seu terminal. Reservas em memória devem estar no estado inicial.
2. **Rodar o validador**:
   ```bash
   python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
   ```
   Esperado: **36 PASS** e **exit code 0**. Rodar sempre com processos recém-subidos (reservas de uma
   execução alteram a seguinte). Em caso de FAIL, voltar à fase dona daquela verificação (ver matriz
   no `docs/plano-geral.md` §6).
3. **Fluxo manual do avaliador** (não coberto pelo validador automático):
   - **Restart-safe:** capturar o `requestState` de um conflito (corpo de
     `exemplos/wire/03-...conflito-input-required.json`), **reiniciar o servidor MCP**, reenviar o
     retry e confirmar que a reserva conclui.
   - **`traceparent` no stderr:** confirmar que o trace-id impresso na 1ª linha do validador aparece
     no stderr do servidor MCP, e que há um `tools/list` antes do 1º `tools/call`.
   - **Id do retry:** localizar no stderr o par `tools/call` de uma reserva que passou pela pausa e
     confirmar que o id do retry é **diferente** do inicial.
4. **Determinismo** (check 36 + critério): confirmar que o mesmo pedido enviado duas vezes produz o
   mesmo resultado, e que **não há** dependência de SDK de LLM no `package.json`/`pyproject.toml`.
5. **Starter intacto**: `git status` deve mostrar **zero** alterações em `dados/`, `validador/`,
   `exemplos/`. A estrutura do starter foi mantida (dois processos, pastas no lugar).
6. **Escrever o `README.md`** (substituindo o do starter) com as **quatro seções**:
   - **Como rodar**: comandos exatos para subir os dois processos e rodar o validador, a partir de um
     clone limpo, incluindo como **gerar e exportar** `REQUEST_STATE_SECRET`
     (`python3 -c "import secrets; print(secrets.token_hex(32))"`) — **nunca** o valor usado.
   - **Onde a ponte acontece**: um parágrafo apontando o ponto do código em que `input_required` vira
     `TASK_STATE_INPUT_REQUIRED`, e o ponto em que o `requestState` volta para o servidor no retry.
   - **Decisões técnicas**: como o `requestState` é protegido (HMAC/AEAD), por quanto tempo vale
     (expiração 5–30 min), e onde o estado das Tasks é guardado (store em memória por `taskId`).
   - **Saída do validador**: a saída completa da última execução, colada em bloco de código (36 PASS,
     exit 0).
7. **Checklist final** dos Critérios de Aceite (todos os grupos do enunciado), item por item.
8. **Publicar**: commit e `git push origin main` no fork. Confirmar que a entrega está na branch
   `main` do repositório público.

## 5. Contratos e exemplos de wire aplicáveis

- O conjunto completo de `exemplos/wire/` serve de conferência final: cada passo do fluxo ponta a
  ponta deve espelhar o respectivo wire (card `07`, send-message `08`, get-task `09`, continuação
  `10`).

## 6. Riscos e armadilhas

- **Rodar o validador duas vezes sem reiniciar** → falsos negativos (reservas acumuladas). Sempre do zero.
- **Segredo no README** → o repositório é público. Documentar **como gerar**, nunca o valor.
- **README sem uma das 4 seções** → reprova o critério. Conferir as quatro.
- **Alterar `dados/`/`validador/`/`exemplos/`** → invalida a entrega mesmo que o validador passe
  localmente (o avaliador roda o validador do repositório original).
- **Esquecer o fluxo manual** (restart, stderr) → o avaliador testa isso à mão; não basta o validador
  automático.
- **Push fora da `main`** → a entrega precisa estar na `main` do fork.

## 7. Definição de Pronto (verificável)

- [ ] `python3 validador/validar.py` → 36 PASS, exit 0, processos recém-subidos.
- [ ] Retry conclui após restart do servidor MCP (mesmo `REQUEST_STATE_SECRET`).
- [ ] trace-id do validador aparece no stderr; `tools/list` antes do 1º `tools/call`; id do retry ≠ inicial.
- [ ] `git status` limpo em `dados/`, `validador/`, `exemplos/`.
- [ ] Sem dependência de LLM nos manifestos.
- [ ] `README.md` com as 4 seções e a saída do validador colada.
- [ ] Entrega publicada na `main` do fork.

Comandos de verificação:
```bash
python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301 ; echo "exit=$?"
git status --porcelain dados/ validador/ exemplos/   # vazio
```

## 8. Sugestão de commit (pt-BR, Conventional Commits)

```
docs(readme): documenta subida, a ponte, decisoes tecnicas e saida do validador
```
