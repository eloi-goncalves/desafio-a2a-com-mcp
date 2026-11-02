#!/usr/bin/env bash
# Validacao ponta a ponta: sobe MCP + agente do zero, roda o validador, derruba.
set -uo pipefail
cd "$(dirname "$0")/.."

pkill -f "servidor-mcp/server.py" 2>/dev/null; pkill -f "agente/agent.py" 2>/dev/null
sleep 1
export REQUEST_STATE_SECRET="${REQUEST_STATE_SECRET:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"

.venv/bin/python servidor-mcp/server.py >/tmp/mcp.log 2>&1 &
MCP_PID=$!
sleep 2
.venv/bin/python agente/agent.py >/tmp/agente.log 2>&1 &
AG_PID=$!
sleep 3

.venv/bin/python validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301
CODE=$?

kill "$MCP_PID" "$AG_PID" 2>/dev/null
exit "$CODE"
