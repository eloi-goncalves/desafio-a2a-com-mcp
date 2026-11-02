"""Agente 'Central de Salas': host MCP por dentro, servidor A2A por fora.

- Por dentro e um cliente MCP de verdade, falando HTTP com o servidor MCP: descobre
  as tools por tools/list, le o resource da politica e enxerga o input_required cru.
- Por fora e um servidor A2A (JSON-RPC 1.0): publica o Agent Card, aceita SendMessage
  e GetTask, e e aqui que a ponte acontece (input_required -> TASK_STATE_INPUT_REQUIRED,
  com o requestState guardado por Task e ecoado sem modificacao no retry com id novo).

Sem LLM: o pedido chega em formato fixo e a decisao e por regra (deterministica).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROTO = "2026-07-28"
CAPS = {"elicitation": {"form": {}}}
CLIENT_INFO = {"name": "agente-central-de-salas", "version": "1.0.0"}

MCP_URL = os.environ.get("MCP_URL", "http://localhost:7301/mcp")
AGENTE_HOST = os.environ.get("AGENTE_HOST", "127.0.0.1")
AGENTE_PORT = int(os.environ.get("AGENTE_PORT", "7300"))
AGENTE_PUBLIC_URL = os.environ.get("AGENTE_PUBLIC_URL", f"http://{AGENTE_HOST}:{AGENTE_PORT}")

ESTADOS_TERMINAIS = {"TASK_STATE_COMPLETED", "TASK_STATE_CANCELED", "TASK_STATE_FAILED"}

_RE_RESERVAR = re.compile(
    r"reservar\s+sala=(?P<sala>\S+)\s+inicio=(?P<inicio>\S+)\s+fim=(?P<fim>\S+)\s+responsavel=(?P<responsavel>.+?)\s*$"
)
_RE_ESCOLHA = re.compile(r"escolha=(?P<valor>\S+)")


def _novo_id() -> str:
    return secrets.token_hex(6)


# --------------------------------------------------------------------------- #
# Cliente MCP (raw JSON-RPC sobre HTTP). O requestState e opaco: guardar/ecoar.
# --------------------------------------------------------------------------- #


def mcp_call(method: str, params: dict, mcp_name: str | None = None, traceparent: str | None = None) -> dict:
    meta: dict = {
        "io.modelcontextprotocol/protocolVersion": PROTO,
        "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
        "io.modelcontextprotocol/clientCapabilities": CAPS,
    }
    if traceparent:
        meta["traceparent"] = traceparent
    # Cada chamada usa um id de JSON-RPC novo: garante id do retry != id inicial.
    corpo = {"jsonrpc": "2.0", "id": _novo_id(), "method": method, "params": {**params, "_meta": meta}}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTO,
        "Mcp-Method": method,
    }
    if mcp_name:
        headers["Mcp-Name"] = mcp_name
    req = urllib.request.Request(MCP_URL, data=json.dumps(corpo).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def mcp_reservar(args: dict, traceparent: str | None) -> dict:
    return mcp_call("tools/call", {"name": "reservar_sala", "arguments": args}, "reservar_sala", traceparent)


def mcp_retry(args: dict, chave: str, resposta_elicit: dict, request_state: str, traceparent: str | None) -> dict:
    params = {
        "name": "reservar_sala",
        "arguments": args,
        "inputResponses": {chave: resposta_elicit},
        "requestState": request_state,  # ecoado sem modificacao
    }
    return mcp_call("tools/call", params, "reservar_sala", traceparent)


def _texto_resultado(result: dict) -> str:
    return " ".join(p.get("text", "") for p in result.get("content", []))


def _enum_do_input(input_requests: dict) -> tuple[str, list[str]]:
    chave = next(iter(input_requests))
    schema = (input_requests[chave].get("params", {}).get("requestedSchema") or {})
    campo = (schema.get("properties") or {}).get("sala", {})
    enum = campo.get("enum") or ([campo["const"]] if "const" in campo else [])
    return chave, enum


# --------------------------------------------------------------------------- #
# Estado das Tasks (A2A). Guardado em memoria, por taskId.
# --------------------------------------------------------------------------- #

_LOCK = threading.Lock()
_TASKS: dict[str, dict] = {}
# Estado pausado por Task: o requestState opaco e o contexto para retomar.
_PAUSAS: dict[str, dict] = {}
POLITICA_VERSAO = "2026-11-01"


def _msg_agente(task: dict, texto: str) -> dict:
    return {
        "messageId": f"msg-{_novo_id()}",
        "role": "ROLE_AGENT",
        "parts": [{"text": texto}],
        "taskId": task["id"],
        "contextId": task["contextId"],
    }


def _definir(task: dict, state: str, texto: str) -> None:
    m = _msg_agente(task, texto)
    task["status"] = {"state": state, "message": m}
    task["history"].append(m)


def _artifact(sc: dict) -> dict:
    conteudo = {
        "reserva": sc.get("reserva"),
        "sala": sc.get("sala"),
        "inicio": sc.get("inicio"),
        "fim": sc.get("fim"),
        "responsavel": sc.get("responsavel"),
        "politica": POLITICA_VERSAO,
    }
    return {
        "artifactId": f"art-{_novo_id()}",
        "name": "reserva",
        "parts": [{"text": json.dumps(conteudo, ensure_ascii=False)}],
    }


def _propagar_traceparent(tp: str | None) -> str | None:
    """Mesmo trace-id, span-id novo. O trace-id nunca muda."""
    if not tp:
        return None
    partes = tp.split("-")
    if len(partes) >= 4:
        return f"00-{partes[1]}-{secrets.token_hex(8)}-01"
    return tp


def _nova_mensagem_usuario(msg: dict) -> dict:
    return {
        "messageId": msg.get("messageId") or f"msg-{_novo_id()}",
        "role": msg.get("role", "ROLE_USER"),
        "parts": msg.get("parts", []),
        **({"taskId": msg["taskId"]} if msg.get("taskId") else {}),
    }


def send_message(params: dict, traceparent: str | None) -> dict:
    msg = params.get("message") or {}
    if msg.get("taskId"):
        return _continuar(msg, traceparent)
    return _abrir(msg, traceparent)


def _abrir(msg: dict, traceparent: str | None) -> dict:
    texto = " ".join(p.get("text", "") for p in msg.get("parts", []))
    task_id = f"task-{_novo_id()}"
    ctx_id = f"ctx-{_novo_id()}"
    task = {
        "id": task_id,
        "contextId": ctx_id,
        "status": {"state": "TASK_STATE_SUBMITTED"},
        "history": [_nova_mensagem_usuario(msg)],
        "artifacts": [],
    }
    with _LOCK:
        _TASKS[task_id] = task

    m = _RE_RESERVAR.search(texto)
    if not m:
        _definir(task, "TASK_STATE_FAILED", "Pedido invalido: use reservar sala=<id> inicio=<iso> fim=<iso> responsavel=<nome>")
        return {"task": task}

    task["status"] = {"state": "TASK_STATE_WORKING"}
    args = {"sala": m["sala"], "inicio": m["inicio"], "fim": m["fim"], "responsavel": m["responsavel"]}
    tp = _propagar_traceparent(traceparent)
    resp = mcp_reservar(args, tp)
    return {"task": _tratar_resposta_mcp(task, resp, args, tp)}


def _tratar_resposta_mcp(task: dict, resp: dict, args: dict, traceparent: str | None) -> dict:
    erro = resp.get("error")
    result = resp.get("result") or {}
    if erro:
        _definir(task, "TASK_STATE_FAILED", str(erro.get("message", "erro")))
        return task
    if result.get("isError"):
        _definir(task, "TASK_STATE_FAILED", _texto_resultado(result))
        return task
    if result.get("resultType") == "input_required":
        chave, enum = _enum_do_input(result.get("inputRequests") or {})
        with _LOCK:
            _PAUSAS[task["id"]] = {
                "requestState": result.get("requestState"),
                "chave": chave,
                "enum": enum,
                "args": args,
                "traceparent": traceparent,
            }
        _definir(task, "TASK_STATE_INPUT_REQUIRED", "alternativas: " + ", ".join(enum))
        return task
    # resultType complete, reservado
    sc = result.get("structuredContent") or {}
    task["artifacts"] = [_artifact(sc)]
    _definir(task, "TASK_STATE_COMPLETED", f"Reserva {sc.get('reserva')} confirmada na {sc.get('sala')}.")
    return task


def _continuar(msg: dict, traceparent: str | None) -> dict:
    task_id = msg["taskId"]
    with _LOCK:
        task = _TASKS.get(task_id)
        pausa = _PAUSAS.get(task_id)
    if task is None:
        raise _JsonRpcError(-32001, "Task nao encontrada")
    if task["status"]["state"] in ESTADOS_TERMINAIS:
        raise _JsonRpcError(-32002, "Task em estado terminal nao aceita novas mensagens")

    task["history"].append(_nova_mensagem_usuario(msg))
    texto = " ".join(p.get("text", "") for p in msg.get("parts", []))
    m = _RE_ESCOLHA.search(texto)
    valor = m["valor"] if m else ""

    if valor == "recusar":
        mcp_retry(pausa["args"], pausa["chave"], {"action": "decline"}, pausa["requestState"], _propagar_traceparent(traceparent))
        _definir(task, "TASK_STATE_CANCELED", "Reserva recusada.")
        with _LOCK:
            _PAUSAS.pop(task_id, None)
        return {"task": task}

    if valor not in pausa["enum"]:
        # Escolha fora do enum: mantem pausada e repete as alternativas.
        _definir(task, "TASK_STATE_INPUT_REQUIRED", "alternativas: " + ", ".join(pausa["enum"]))
        return {"task": task}

    tp = _propagar_traceparent(traceparent)
    resp = mcp_retry(pausa["args"], pausa["chave"], {"action": "accept", "content": {"sala": valor}}, pausa["requestState"], tp)
    result = resp.get("result") or {}
    sc = result.get("structuredContent") or {}
    task["artifacts"] = [_artifact(sc)]
    _definir(task, "TASK_STATE_COMPLETED", f"Reserva {sc.get('reserva')} confirmada na {sc.get('sala')}.")
    with _LOCK:
        _PAUSAS.pop(task_id, None)
    return {"task": task}


def get_task(params: dict) -> dict:
    task_id = params.get("id")
    with _LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        raise _JsonRpcError(-32001, "Task nao encontrada")
    return {"task": task}


# --------------------------------------------------------------------------- #
# Agent Card e transporte HTTP (A2A JSON-RPC 1.0).
# --------------------------------------------------------------------------- #


def agent_card() -> dict:
    return {
        "name": "Central de Salas",
        "description": "Reserva salas de reuniao da Hill Valley Tech.",
        "provider": {"organization": "Hill Valley Tech", "url": "https://hillvalley.example"},
        "version": "1.0.0",
        "supportedInterfaces": [
            {"url": f"{AGENTE_PUBLIC_URL}/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
        ],
        "capabilities": {"streaming": False, "pushNotifications": False, "extendedAgentCard": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "reservar-sala",
                "name": "Reservar sala",
                "description": "Reserva uma sala em um intervalo. Se houver conflito, pergunta qual alternativa usar.",
                "tags": ["salas", "agenda"],
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain"],
                "examples": [
                    "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"
                ],
            }
        ],
    }


class _JsonRpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silencia o log padrao do http.server
        pass

    def _enviar_json(self, status: int, corpo: dict) -> None:
        dado = json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dado)))
        self.end_headers()
        self.wfile.write(dado)

    def do_GET(self) -> None:
        if self.path == "/.well-known/agent-card.json":
            self._enviar_json(200, agent_card())
        else:
            self._enviar_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/a2a":
            self._enviar_json(404, {"error": "not found"})
            return
        tamanho = int(self.headers.get("Content-Length", "0"))
        try:
            req = json.loads(self.rfile.read(tamanho).decode() or "{}")
        except json.JSONDecodeError:
            self._enviar_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            return
        req_id = req.get("id")
        metodo = req.get("method")
        params = req.get("params") or {}
        traceparent = self.headers.get("traceparent")
        try:
            if metodo == "SendMessage":
                resultado = send_message(params, traceparent)
            elif metodo == "GetTask":
                resultado = get_task(params)
            else:
                raise _JsonRpcError(-32601, f"metodo desconhecido: {metodo}")
            self._enviar_json(200, {"jsonrpc": "2.0", "id": req_id, "result": resultado})
        except _JsonRpcError as e:
            self._enviar_json(200, {"jsonrpc": "2.0", "id": req_id, "error": {"code": e.code, "message": e.message}})


def _descobrir() -> None:
    """tools/list ANTES do primeiro tools/call e leitura do resource da politica."""
    global POLITICA_VERSAO
    resp = mcp_call("tools/list", {})
    tools = [t.get("name") for t in (resp.get("result") or {}).get("tools", [])]
    if not tools:
        raise RuntimeError("tools/list vazio")
    print(f"[agente] tools descobertas: {tools}", file=sys.stderr, flush=True)
    resp = mcp_call("resources/read", {"uri": "politica://uso"}, "politica://uso")
    contents = (resp.get("result") or {}).get("contents") or [{}]
    texto = contents[0].get("text", "")
    if texto:
        POLITICA_VERSAO = texto.splitlines()[0].split(":", 1)[1].strip()
    print(f"[agente] versao da politica: {POLITICA_VERSAO}", file=sys.stderr, flush=True)


def _descobrir_com_retry(tentativas: int = 60, intervalo: float = 0.5) -> None:
    """Descobre as tools antes de servir. Espera o servidor MCP subir se preciso."""
    import time

    for i in range(tentativas):
        try:
            _descobrir()
            return
        except Exception as e:  # noqa: BLE001 - aguarda o MCP ficar disponivel
            if i == tentativas - 1:
                print(f"[agente] aviso: descoberta nao concluida ({e}); seguirei assim mesmo", file=sys.stderr, flush=True)
                return
            time.sleep(intervalo)


def main() -> None:
    _descobrir_com_retry()
    servidor = ThreadingHTTPServer((AGENTE_HOST, AGENTE_PORT), Handler)
    print(f"[agente] Central de Salas (A2A) em {AGENTE_PUBLIC_URL}/a2a", file=sys.stderr, flush=True)
    servidor.serve_forever()


if __name__ == "__main__":
    main()
