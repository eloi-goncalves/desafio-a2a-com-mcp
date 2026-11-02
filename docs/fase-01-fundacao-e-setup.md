---
fase: 01
titulo: "Fundação e setup"
objetivo_uma_linha: "Preparar o repositório, a estrutura de pastas, a stack e os scripts de subida, sem escrever regra de negócio."
depende_de: []
habilita: [02, 05, 08]
criterios_de_aceite_cobertos:
  - "dados/, validador/ e exemplos/ não foram alterados"
  - "não há dependência de SDK de provedor de LLM no package.json ou no pyproject.toml"
  - "Versões travadas no package.json ou no pyproject.toml"
testes_do_validador_cobertos: []
artefatos_produzidos:
  - servidor-mcp/ (projeto inicializado)
  - agente/ (projeto inicializado)
  - pyproject.toml ou package.json (versões travadas)
  - scripts de subida na raiz (ex.: subir-mcp, subir-agente)
  - .env.example (REQUEST_STATE_SECRET e portas)
status: pendente
---

# Fase 01 — Fundação e setup

## 1. Contexto e objetivo

Preparar o terreno para as fases de implementação. Nenhuma tool, nenhuma regra de negócio, nenhum
endpoint ainda. Ao fim desta fase existe: a stack escolhida e **travada**, a estrutura de pastas do
starter preservada, `servidor-mcp/` e `agente/` inicializados como projetos, e os scripts para subir
cada processo. É aqui que a **decisão de stack** é tomada e registrada.

## 2. Fontes de verdade desta fase

- `docs/challenge.md` → seções **"Tecnologias obrigatórias"**, **"Estrutura obrigatória do
  entregável"**, **"Regras de entrega"**, **"Portas"**.
- `docs/plano-geral.md` → §3 (invariantes), §7 (decisão de stack pendente).
- Estrutura atual do repositório (pastas `dados/`, `validador/`, `exemplos/`, `servidor-mcp/`,
  `agente/` com `.gitkeep`).

## 3. Pré-condições

- Fork do starter `https://github.com/devfullcycle/desafio-a2a-com-mcp` criado, clone local na
  branch `main`. Verificar: `git remote -v` aponta para o fork; `git branch` mostra `main`.
- Python 3.10+ disponível para o validador: `python3 --version`.

## 4. Passo a passo de execução

1. **Decidir a stack** e registrar a decisão (1 parágrafo) no topo do `README` de trabalho ou numa
   nota: Python (`mcp`, 3.10+) ou Node (`@modelcontextprotocol/server`, Node 20+, ESM). Critério:
   os wire examples foram capturados do SDK Python (`requestState` com prefixo `v1.`, chave
   `__main__:escolha_de_sala`), o que indica menor atrito em Python para o MRTR de primeira classe.
   **A nota não depende da linguagem.** Escolha uma e siga até o fim.
2. **Inicializar `servidor-mcp/`** como projeto da stack escolhida, com o SDK oficial do MCP v2
   alinhado à revisão `2026-07-28` da spec. **Travar a versão** (`pyproject.toml` com versão exata,
   ou `package.json` com versão fixa + lockfile).
3. **Inicializar `agente/`** como projeto separado, com dependência do SDK MCP (lado cliente) e de
   um servidor HTTP/JSON-RPC para o A2A. **Sem nenhuma dependência de provedor de LLM.**
4. **Preservar o starter protegido.** Não tocar em `dados/`, `validador/`, `exemplos/`. Confirmar que
   o `.gitkeep` das pastas foi substituído por código real só dentro de `servidor-mcp/` e `agente/`.
5. **Criar `.env.example`** na raiz documentando as variáveis, **sem valores reais**:
   - `REQUEST_STATE_SECRET` (gerar com `python3 -c "import secrets; print(secrets.token_hex(32))"`)
   - `MCP_PORT=7301`, `AGENTE_PORT=7300` (parametrizáveis, com esses padrões)
   - `MCP_URL=http://localhost:7301/mcp` (usado pelo agente)
6. **Criar scripts de subida** na raiz (permitido pelo enunciado), por exemplo `subir-mcp` e
   `subir-agente`, cada um subindo **um processo**. Eles devem exportar/ler o `REQUEST_STATE_SECRET`
   do ambiente, nunca embutir o valor.
7. **Esqueleto mínimo que sobe** (sem lógica): o servidor MCP deve iniciar na `7301` e o agente na
   `7300`, mesmo que ainda respondam vazio. Objetivo: provar que a infra de processo funciona.

## 5. Contratos e exemplos de wire aplicáveis

- Nenhum contrato de protocolo é implementado aqui. Apenas confirmar, por leitura, que os headers e
  o `_meta` esperados (ver `exemplos/wire/01`) vão exigir Streamable HTTP na Fase 02.
- Confirmar as portas e caminhos: MCP `7301` em `/mcp`; agente `7300` em `/a2a` e
  `/.well-known/agent-card.json` (ver URLs nos wire `01`, `07`, `08`).

## 6. Riscos e armadilhas

- **Alterar `dados/`, `validador/` ou `exemplos/`** invalida a entrega. Não formatar, não "organizar".
- **Dependência de LLM** no manifesto reprova no check 36/critério de determinismo. Não incluir SDKs
  de OpenAI/Anthropic/etc.
- **Colapsar os dois processos** (um único servidor) descaracteriza a entrega. São dois manifestos,
  duas pastas, dois processos.
- **Versão não travada** reprova. Fixar a versão do SDK.

## 7. Definição de Pronto (verificável)

- [ ] `servidor-mcp/` sobe na `7301` e `agente/` sobe na `7300` (ainda que respondam vazio).
- [ ] `git status` mostra zero alterações em `dados/`, `validador/`, `exemplos/`.
- [ ] Manifesto (`pyproject.toml`/`package.json`) tem a versão do SDK MCP **travada** e **nenhuma**
      dependência de provedor de LLM.
- [ ] `.env.example` documenta `REQUEST_STATE_SECRET` e portas, **sem valor real**.
- [ ] Scripts de subida leem o segredo do ambiente e sobem um processo cada.
- [ ] Decisão de stack registrada por escrito.

Comandos de verificação:
```bash
git status --porcelain dados/ validador/ exemplos/   # deve sair vazio
grep -riE "openai|anthropic|langchain|llm" servidor-mcp/ agente/ --include=*.toml --include=*.json || echo "sem LLM"
```

## 8. Sugestão de commit (pt-BR, Conventional Commits)

```
chore(setup): inicializa servidor-mcp e agente, trava versoes e scripts de subida
```
