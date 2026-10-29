"""Eficiencia por operación a partir de los eventos de la tablet.

Modelo (Documentación/costura/03-app-tablet.md, sección 6):
- Cada ticket-operación tiene un tiempo asignado = piezas hechas × SMV.
- Tiempo real = tiempo entre OP_INICIO y OP_FIN, menos las pausas.
- Cada pausa lleva un motivo y cada motivo tiene un tiempo permitido para volver:
  * pausa dentro del permitido: no cuenta (el reloj de la operación se detiene);
  * lo que pase del permitido sí cuenta como tiempo real (política por confirmar).
- Eficiencia = tiempo asignado ÷ tiempo real. Más de 100 % = terminó antes de lo asignado.
- Eficiencia del día = Σ tiempo asignado ÷ Σ tiempo real (minutos sumados, nunca promedio de %).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Mapping, Optional

TIPOS = {"JORNADA_INICIO", "JORNADA_FIN", "OP_INICIO", "OP_FIN", "PAUSA_INICIO", "PAUSA_FIN"}


@dataclass(frozen=True)
class Evento:
    event_id: str
    tipo: str
    ts: datetime
    ticket_operacion_id: Optional[int] = None
    motivo: Optional[str] = None
    piezas: Optional[int] = None


@dataclass(frozen=True)
class Motivo:
    codigo: str
    limite_min: float  # tiempo permitido para volver de una pausa con este motivo
    descripcion: str = ""
    activo: bool = True  # un motivo dado de baja deja de ofrecerse, pero los eventos antiguos se siguen calculando


@dataclass
class Pausa:
    motivo: str
    inicio: datetime
    fin: datetime
    min_total: float
    min_permitido: float
    min_exceso: float


@dataclass
class ResultadoOperacion:
    ticket_operacion_id: int
    inicio: datetime
    fin: datetime
    piezas: int
    min_transcurridos: float
    min_pausa_permitida: float
    min_pausa_exceso: float
    min_real: float
    min_asignado: float
    eficiencia: Optional[float]
    pausas: List[Pausa] = field(default_factory=list)


@dataclass
class ResumenOperaciones:
    operaciones: List[ResultadoOperacion]
    operacion_abierta: Optional[int]
    min_asignado: float
    min_real: float
    eficiencia: Optional[float]
    pausas_con_exceso: List[Pausa]


def deduplicar(eventos: Iterable[Evento]) -> List[Evento]:
    """Descarta eventos repetidos (mismo event_id) y ordena por hora."""
    vistos: Dict[str, Evento] = {}
    for e in eventos:
        vistos.setdefault(e.event_id, e)
    return sorted(vistos.values(), key=lambda e: e.ts)


def _min(delta: timedelta) -> float:
    return delta.total_seconds() / 60.0


def calcular(
    eventos: Iterable[Evento],
    smv_por_ticket_operacion: Mapping[int, float],
    motivos: Mapping[str, Motivo],
) -> ResumenOperaciones:
    """Lanza ValueError si la secuencia de eventos es inválida."""
    evs = [e for e in deduplicar(eventos) if not e.tipo.startswith("JORNADA")]
    for e in evs:
        if e.tipo not in TIPOS:
            raise ValueError(f"tipo de evento desconocido: {e.tipo}")

    resultados: List[ResultadoOperacion] = []
    op_id: Optional[int] = None
    op_inicio: Optional[datetime] = None
    pausas: List[Pausa] = []
    pausa_motivo: Optional[str] = None
    pausa_inicio: Optional[datetime] = None

    for e in evs:
        t = e.tipo
        if t == "OP_INICIO":
            if op_id is not None:
                raise ValueError("OP_INICIO con otra operación abierta")
            if e.ticket_operacion_id not in smv_por_ticket_operacion:
                raise ValueError(f"operación de ticket desconocida: {e.ticket_operacion_id}")
            op_id, op_inicio, pausas = e.ticket_operacion_id, e.ts, []
        elif t == "PAUSA_INICIO":
            if op_id is None:
                raise ValueError("PAUSA_INICIO sin operación abierta")
            if pausa_motivo is not None:
                raise ValueError("PAUSA_INICIO con otra pausa abierta")
            if e.motivo not in motivos:
                raise ValueError(f"motivo desconocido: {e.motivo}")
            pausa_motivo, pausa_inicio = e.motivo, e.ts
        elif t == "PAUSA_FIN":
            if pausa_motivo is None:
                raise ValueError("PAUSA_FIN sin PAUSA_INICIO")
            total = _min(e.ts - pausa_inicio)
            permitido = min(total, motivos[pausa_motivo].limite_min)
            pausas.append(Pausa(pausa_motivo, pausa_inicio, e.ts, total, permitido, total - permitido))
            pausa_motivo = pausa_inicio = None
        elif t == "OP_FIN":
            if op_id is None or e.ticket_operacion_id != op_id:
                raise ValueError("OP_FIN sin OP_INICIO correspondiente")
            if pausa_motivo is not None:
                raise ValueError("OP_FIN con una pausa abierta: hay que reanudar primero")
            transcurridos = _min(e.ts - op_inicio)
            permitida = sum(p.min_permitido for p in pausas)
            exceso = sum(p.min_exceso for p in pausas)
            real = transcurridos - permitida
            piezas = e.piezas or 0
            asignado = piezas * smv_por_ticket_operacion[op_id]
            resultados.append(ResultadoOperacion(
                op_id, op_inicio, e.ts, piezas, transcurridos, permitida, exceso, real, asignado,
                asignado / real if real > 0 else None, pausas))
            op_id = op_inicio = None
            pausas = []

    asignado_total = sum(r.min_asignado for r in resultados)
    real_total = sum(r.min_real for r in resultados)
    return ResumenOperaciones(
        operaciones=resultados,
        operacion_abierta=op_id,
        min_asignado=asignado_total,
        min_real=real_total,
        eficiencia=asignado_total / real_total if real_total > 0 else None,
        pausas_con_exceso=[p for r in resultados for p in r.pausas if p.min_exceso > 0],
    )
