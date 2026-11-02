"""Dominio do servidor MCP: dados fixos, modelos, validacoes e regra de alternativas.

O agente nao implementa nada disto: conflito, politica e alternativas sao decisao
do servidor MCP (dois processos separados, o agente so traduz protocolo).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

# dados/ fica na raiz do repositorio, um nivel acima de servidor-mcp/.
_RAIZ = Path(__file__).resolve().parent.parent
_DADOS = _RAIZ / "dados"

# Janela de uso (horario de Sao Paulo, -03:00), em minutos desde a meia-noite.
_ABERTURA_MIN = 8 * 60
_FECHAMENTO_MIN = 20 * 60
_DURACAO_MAX_MIN = 2 * 60

# Mensagens de erro de execucao: fonte unica de verdade, texto exato do enunciado.
ERRO_SALA = "Sala inexistente: {sala}"
ERRO_JANELA = "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
ERRO_DURACAO = "Duracao acima do limite: a politica permite no maximo 2 horas"
ERRO_INTERVALO = "Intervalo invalido: fim deve ser posterior a inicio"
ERRO_SEM_ALTERNATIVA = "Sem alternativas disponiveis no intervalo"


class SalaOut(BaseModel):
    id: str
    nome: str
    capacidade: int
    recursos: list[str]


class ListaDeSalas(BaseModel):
    salas: list[SalaOut]


class ConflitoOut(BaseModel):
    id: str
    inicio: str
    fim: str
    responsavel: str


class Disponibilidade(BaseModel):
    sala: str
    livre: bool
    conflitos: list[ConflitoOut]


class Reserva(BaseModel):
    reserva: str | None
    reservado: bool
    sala: str | None
    inicio: str | None
    fim: str | None
    responsavel: str | None
    politica: str | None
    motivo: str | None


class EscolhaSala(BaseModel):
    """Payload da escolha quando o intervalo pedido ja esta livre (sem elicitation)."""

    sala: str


def _ler_json(nome: str) -> object:
    return json.loads((_DADOS / nome).read_text(encoding="utf-8"))


def versao_politica() -> str:
    """Le a versao declarada na primeira linha de dados/politica-de-uso.md."""
    primeira = (_DADOS / "politica-de-uso.md").read_text(encoding="utf-8").splitlines()[0]
    # formato: "versao: 2026-11-01"
    return primeira.split(":", 1)[1].strip()


def texto_politica() -> str:
    return (_DADOS / "politica-de-uso.md").read_text(encoding="utf-8")


class Reservas:
    """Reservas em memoria. Partem de dados/reservas.json e nao sobrevivem a restart."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._salas: dict[str, SalaOut] = {}
        for s in _ler_json("salas.json"):  # type: ignore[union-attr]
            self._salas[s["id"]] = SalaOut(**s)
        self._reservas: list[dict] = []
        maior = 0
        for r in _ler_json("reservas.json"):  # type: ignore[union-attr]
            self._reservas.append(
                {
                    "id": r["id"],
                    "sala": r["sala"],
                    "inicio": r["inicio"],
                    "fim": r["fim"],
                    "responsavel": r["responsavel"],
                    "_ini": datetime.fromisoformat(r["inicio"]),
                    "_fim": datetime.fromisoformat(r["fim"]),
                }
            )
            try:
                maior = max(maior, int(str(r["id"]).split("-")[-1]))
            except ValueError:
                pass
        self._seq = maior

    def salas(self) -> list[SalaOut]:
        return list(self._salas.values())

    def existe(self, sala: str) -> bool:
        return sala in self._salas

    def capacidade(self, sala: str) -> int:
        return self._salas[sala].capacidade

    def conflitos(self, sala: str, ini: datetime, fim: datetime) -> list[ConflitoOut]:
        return [
            ConflitoOut(id=r["id"], inicio=r["inicio"], fim=r["fim"], responsavel=r["responsavel"])
            for r in self._reservas
            if r["sala"] == sala and r["_ini"] < fim and r["_fim"] > ini
        ]

    def livre(self, sala: str, ini: datetime, fim: datetime) -> bool:
        return not self.conflitos(sala, ini, fim)

    def alternativas(self, sala_pedida: str, ini: datetime, fim: datetime) -> list[str]:
        """Salas livres no intervalo com capacidade >= a da sala pedida.

        No maximo tres, ordenadas por capacidade crescente e, em empate, por id.
        """
        cap = self.capacidade(sala_pedida)
        candidatas = [
            s
            for s in self._salas.values()
            if s.id != sala_pedida and s.capacidade >= cap and self.livre(s.id, ini, fim)
        ]
        candidatas.sort(key=lambda s: (s.capacidade, s.id))
        return [s.id for s in candidatas[:3]]

    def criar(self, sala: str, inicio: str, fim: str, responsavel: str) -> str:
        with self._lock:
            self._seq += 1
            rid = f"res-{self._seq:04d}"
            self._reservas.append(
                {
                    "id": rid,
                    "sala": sala,
                    "inicio": inicio,
                    "fim": fim,
                    "responsavel": responsavel,
                    "_ini": datetime.fromisoformat(inicio),
                    "_fim": datetime.fromisoformat(fim),
                }
            )
            return rid


def _minuto_do_dia(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def validar_pedido(reservas: Reservas, sala: str, inicio: str, fim: str) -> tuple[datetime, datetime]:
    """Aplica sala/intervalo/janela/duracao. Levanta ToolError com a mensagem exata.

    A ordem importa para casar com o validador: sala, depois intervalo invertido,
    depois janela, depois duracao.
    """
    if not reservas.existe(sala):
        raise ToolError(ERRO_SALA.format(sala=sala))
    ini = datetime.fromisoformat(inicio)
    f = datetime.fromisoformat(fim)
    if f <= ini:
        raise ToolError(ERRO_INTERVALO)
    if _minuto_do_dia(ini) < _ABERTURA_MIN or _minuto_do_dia(f) > _FECHAMENTO_MIN:
        raise ToolError(ERRO_JANELA)
    if (f - ini).total_seconds() / 60 > _DURACAO_MAX_MIN:
        raise ToolError(ERRO_DURACAO)
    return ini, f
