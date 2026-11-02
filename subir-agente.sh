#!/usr/bin/env bash
# Sobe o agente A2A (porta 7300: /a2a e /.well-known/agent-card.json).
set -euo pipefail
cd "$(dirname "$0")"

exec .venv/bin/python agente/agent.py
