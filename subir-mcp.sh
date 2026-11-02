#!/usr/bin/env bash
# Sobe o servidor MCP (porta 7301, Streamable HTTP em /mcp), com o stderr visivel.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -z "${REQUEST_STATE_SECRET:-}" ]]; then
  echo "ERRO: defina REQUEST_STATE_SECRET antes de subir o servidor MCP." >&2
  echo "  export REQUEST_STATE_SECRET=\$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >&2
  exit 1
fi

exec .venv/bin/python servidor-mcp/server.py
