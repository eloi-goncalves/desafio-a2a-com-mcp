"""Servidor MCP 'central-de-salas' (Streamable HTTP, revisao 2026-07-28 da spec).

Usa o SDK oficial do MCP v2 (`mcp`): descoberta de tools, resource, os dois tipos
de erro e o ciclo completo de MRTR na reserva (input_required + requestState selado).

Rode por dentro do venv do projeto:
    REQUEST_STATE_SECRET=<hex> .venv/bin/python servidor-mcp/server.py
"""

from __future__ import annotations

import os
import sys
from typing import Annotated, Any

from pydantic import Field, create_model

from mcp.server.mcpserver import (
    AcceptedElicitation,
    Context,
    DeclinedElicitation,
    CancelledElicitation,
    Elicit,
    ElicitationResult,
    MCPServer,
    RequestStateSecurity,
    Resolve,
)

import dominio
from dominio import (
    Disponibilidade,
    EscolhaSala,
    ListaDeSalas,
    Reserva,
    Reservas,
    SalaOut,
    validar_pedido,
)

MENSAGEM_ELICITACAO = "A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa."

RESERVAS = Reservas()
VERSAO_POLITICA = dominio.versao_politica()


def _segredo() -> str:
    segredo = os.environ.get("REQUEST_STATE_SECRET")
    if not segredo or len(segredo) < 32:
        sys.exit(
            "REQUEST_STATE_SECRET ausente ou curto demais. Gere com:\n"
            '  python3 -c "import secrets; print(secrets.token_hex(32))"\n'
            "e exporte antes de subir o servidor."
        )
    return segredo


async def log_requests(ctx: Any, call_next: Any) -> Any:
    """Registra no stderr metodo, id e traceparent de cada request (sem logging depreciado)."""
    meta = (ctx.params or {}).get("_meta") or {}
    traceparent = meta.get("traceparent")
    print(
        f"[mcp] method={ctx.method} id={ctx.request_id} traceparent={traceparent}",
        file=sys.stderr,
        flush=True,
    )
    return await call_next(ctx)


def _modelo_escolha(alternativas: list[str]) -> type:
    """Schema plano e dinamico: propriedade `sala` restrita as alternativas, nessa ordem."""
    from typing import Literal

    literal = Literal[tuple(alternativas)]  # type: ignore[valid-type]
    return create_model(
        "EscolhaDeSala",
        sala=(literal, Field(title="Sala", description="Sala alternativa escolhida")),
    )


def escolha_de_sala(
    sala: str, inicio: str, fim: str, ctx: Context
) -> Elicit[Any] | EscolhaSala:
    """Resolver do MRTR: decide se reserva direto, pergunta alternativa, ou falha.

    - intervalo livre -> devolve a escolha direta (sem elicitation);
    - ocupado com alternativas -> Elicit em form mode (o SDK sela o requestState);
    - ocupado sem alternativa -> erro de execucao com a mensagem exata.
    """
    ini, f = validar_pedido(RESERVAS, sala, inicio, fim)
    if RESERVAS.livre(sala, ini, f):
        return EscolhaSala(sala=sala)
    alternativas = RESERVAS.alternativas(sala, ini, f)
    if not alternativas:
        from mcp.server.mcpserver.exceptions import ToolError

        raise ToolError(dominio.ERRO_SEM_ALTERNATIVA)
    return Elicit(MENSAGEM_ELICITACAO, _modelo_escolha(alternativas))


def build_server() -> MCPServer:
    server = MCPServer(
        name="central-de-salas",
        version="1.0.0",
        request_state_security=RequestStateSecurity(keys=[_segredo()], ttl=900.0),
        middleware=[log_requests],
    )

    @server.tool(description="Lista todas as salas com capacidade e recursos.")
    def listar_salas() -> ListaDeSalas:
        return ListaDeSalas(salas=RESERVAS.salas())

    @server.tool(
        description="Diz se uma sala esta livre no intervalo, e quais reservas conflitam."
    )
    def consultar_disponibilidade(sala: str, inicio: str, fim: str) -> Disponibilidade:
        ini, f = validar_pedido(RESERVAS, sala, inicio, fim)
        conflitos = RESERVAS.conflitos(sala, ini, f)
        return Disponibilidade(sala=sala, livre=not conflitos, conflitos=conflitos)

    @server.tool(
        description="Reserva uma sala. Se o intervalo estiver ocupado, pergunta qual alternativa usar."
    )
    def reservar_sala(
        sala: str,
        inicio: str,
        fim: str,
        responsavel: str,
        escolha: Annotated[ElicitationResult[EscolhaSala], Resolve(escolha_de_sala)],
    ) -> Reserva:
        if isinstance(escolha, AcceptedElicitation):
            sala_final = escolha.data.sala
            rid = RESERVAS.criar(sala_final, inicio, fim, responsavel)
            return Reserva(
                reserva=rid,
                reservado=True,
                sala=sala_final,
                inicio=inicio,
                fim=fim,
                responsavel=responsavel,
                politica=VERSAO_POLITICA,
                motivo=None,
            )
        # DeclinedElicitation / CancelledElicitation: conclui sem reservar.
        return Reserva(
            reserva=None,
            reservado=False,
            sala=None,
            inicio=None,
            fim=None,
            responsavel=None,
            politica=None,
            motivo="recusado",
        )

    @server.resource("politica://uso", mime_type="text/markdown")
    def politica_de_uso() -> str:
        return dominio.texto_politica()

    return server


def main() -> None:
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "7301"))
    server = build_server()
    print(f"[mcp] central-de-salas em http://{host}:{port}/mcp", file=sys.stderr, flush=True)
    server.run("streamable-http", host=host, port=port, streamable_http_path="/mcp", json_response=True)


if __name__ == "__main__":
    main()
