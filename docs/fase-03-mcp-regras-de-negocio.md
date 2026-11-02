---
fase: 03
titulo: "MCP — regras de negócio"
objetivo_uma_linha: "Implementar consultar_disponibilidade, reservar_sala no caminho feliz e os quatro erros de execução com mensagens exatas."
depende_de: [02]
habilita: [04]
criterios_de_aceite_cobertos:
  - "Sala inexistente, janela violada, duração acima do limite e intervalo invertido devolvem isError: true com as mensagens exatas definidas neste enunciado"
  - "consultar_disponibilidade, com sala, inicio e fim, devolvendo se o intervalo está livre e, se não estiver, as reservas em conflito"
  - "reservar_sala, com sala, inicio, fim e responsavel, criando a reserva quando o intervalo está livre e dentro da política"
  - "As três tools devolvem structuredContent além do bloco de texto"
testes_do_validador_cobertos: [9, 10, 11, 12]
artefatos_produzidos:
  - servidor-mcp/ (lógica de política, consultar_disponibilidade, reservar_sala caminho feliz, erros de execução)
status: pendente
---

# Fase 03 — MCP: regras de negócio

## 1. Contexto e objetivo

Dar vida às duas tools de domínio no **caminho sem conflito**. Implementar as validações da política
(janela 08:00–20:00, máx 2h, intervalo válido, sala existente) e os **quatro erros de execução** com
as mensagens literais. Implementar `consultar_disponibilidade` (livre/conflitos) e `reservar_sala`
quando o intervalo está livre, devolvendo o `structuredContent` da reserva. O ciclo MRTR (conflito →
elicitation) é a Fase 04. Esta fase faz passar as **verificações 9 a 12**.

## 2. Fontes de verdade desta fase

- `docs/challenge.md` → **"Regras de negócio e semântica de erros"** e **"Decisões de produto já
  fechadas"**.
- `dados/politica-de-uso.md` → janela, duração, não-sobreposição.
- `dados/reservas.json` → reservas iniciais (garagem 14–15h, fusca 16–17h).
- `exemplos/wire/02-tools-call-livre.json` → forma do `structuredContent` da reserva concluída.
- `validador/validar.py` → checks 9–12 (mensagens `ERRO_SALA`, `ERRO_JANELA`, `ERRO_DURACAO`,
  `ERRO_INTERVALO`) e a função `texto()` (concatena `content[].text`).

## 3. Pré-condições

- Fase 02 concluída: `tools/list`, `_meta`, resource e log prontos; as 3 tools declaradas.
- Reservas iniciais carregadas de `dados/reservas.json` em memória ao subir.

## 4. Passo a passo de execução

1. **Carregar estado em memória** ao subir: salas de `dados/salas.json`, reservas de
   `dados/reservas.json`. Reservas criadas durante a execução ficam visíveis para consultas
   seguintes do **mesmo processo** (não precisam sobreviver a restart).
2. **Ordem de validação** (aplicada igualmente por `consultar_disponibilidade` e `reservar_sala`):
   1. **Sala existe?** Se não: `isError: true`, mensagem `Sala inexistente: <id informado>` (check 9).
   2. **Intervalo válido?** `fim > inicio`; senão `Intervalo invalido: fim deve ser posterior a
      inicio` (check 12).
   3. **Janela?** `inicio` e `fim` entre 08:00 e 20:00 (horário -03:00); senão `Fora da janela de
      uso: a politica permite reservas entre 08:00 e 20:00` (check 10).
   4. **Duração?** `fim - inicio <= 2h`; senão `Duracao acima do limite: a politica permite no
      maximo 2 horas` (check 11).
   > **Atenção à ordem para bater com o validador:** check 10 usa `07:00→08:00` (janela), check 11
   > usa `09:00→12:00` (duração), check 12 usa `10:00→09:00` (invertido). Garanta que cada caso
   > dispare a mensagem esperada. O intervalo invertido deve ser pego **antes** da checagem de
   > duração (um intervalo negativo não deve virar erro de duração).
3. **`consultar_disponibilidade`** (`sala`, `inicio`, `fim`): após as validações, devolver
   `structuredContent` `{sala, livre: bool, conflitos: [ConflitoOut]}`, onde `conflitos` são as
   reservas da sala que se sobrepõem ao intervalo (`inicio < fim_existente` e `fim > inicio_existente`).
   Devolver também o bloco de texto equivalente.
4. **`reservar_sala` — caminho feliz** (`sala`, `inicio`, `fim`, `responsavel`): após validações, se o
   intervalo estiver **livre**, criar a reserva (novo id sequencial `res-000N`) e devolver
   `resultType: complete`, `isError: false`, e o `structuredContent`:
   ```json
   {"reserva":"res-000N","reservado":true,"sala":"<id>","inicio":"<iso>","fim":"<iso>",
    "responsavel":"<nome>","politica":"2026-11-01","motivo":null}
   ```
   mais o bloco de texto com o **mesmo** JSON (ver wire `02`). O valor de `politica` é a versão lida do
   resource (ou do arquivo); mantê-lo `2026-11-01`.
5. **Sobreposição:** duas reservas na mesma sala não podem se sobrepor. No caminho feliz desta fase, se
   houver conflito, ainda **não** há elicitation — isso é Fase 04. Deixar um ponto de extensão claro
   para onde o conflito será tratado.

## 5. Contratos e exemplos de wire aplicáveis

- **Reserva livre:** `exemplos/wire/02-tools-call-livre.json` — `result.structuredContent` com os 8
  campos (`reserva`, `reservado`, `sala`, `inicio`, `fim`, `responsavel`, `politica`, `motivo:null`) e
  `content[0].text` com o mesmo JSON (indentado é aceito; o validador compara por `json.loads`).
- **Erros de execução:** devolvidos **dentro** de um resultado `complete` com `isError: true` e a
  mensagem no `content[].text`. Prefixo tipo `Error executing tool <nome>:` é aceito; a mensagem em si
  deve ser **exata**.

## 6. Riscos e armadilhas

- **Mensagem com acento ou texto diferente** reprova. Copiar as mensagens literais do enunciado
  (sem acento: `Duracao`, `politica`, `maximo`).
- **Ordem de validação trocada** faz o caso de teste bater na mensagem errada (ex.: invertido virar
  "duração"). Seguir a ordem do passo 2.
- **`isError` como erro de protocolo:** os 4 erros desta fase são **erros de execução**
  (`isError: true` dentro de `complete`), **não** `error` JSON-RPC.
- **`structuredContent` sem o bloco de texto** (ou divergente) reprova por analogia ao check 3.

## 7. Definição de Pronto (verificável)

- [ ] `reservar_sala` em sala livre cria a reserva e devolve o `structuredContent` completo.
- [ ] `consultar_disponibilidade` devolve `livre` e `conflitos` corretos.
- [ ] Sala inexistente → `isError` + `Sala inexistente: <id>` (check 9).
- [ ] `07:00→08:00` → `Fora da janela de uso: ...` (check 10).
- [ ] `09:00→12:00` → `Duracao acima do limite: ...` (check 11).
- [ ] `10:00→09:00` → `Intervalo invalido: fim deve ser posterior a inicio` (check 12).

Comando de verificação:
```bash
python3 validador/validar.py --mcp http://localhost:7301 --agente http://localhost:7300 | sed -n '9,12p'
```

## 8. Sugestão de commit (pt-BR, Conventional Commits)

```
feat(mcp): consultar_disponibilidade, reservar_sala no caminho feliz e erros de execucao
```
