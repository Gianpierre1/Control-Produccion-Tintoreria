"""Minutos del día de una costurera a partir de los eventos de la tablet.

Reglas (Documentación/costura/03-app-tablet.md, sección 6):
- Min. trabajados = jornada - descansos planificados.
- Min. estándar = Σ piezas × SMV de cada OP_FIN.
- Hueco sin operación ni parada: si dura hasta el umbral es manipulación del ciclo
  (no improductivo); si lo supera es "sin causa" y no se compensa.
- Parada con causa: improductiva; se descuenta según la política
  ("compensables" o "todas", [ABIERTO] en el brief).
- Prioridad cuando se superponen estados: descanso > parada > operación > libre.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from formulas import DiaTrabajador

TIPOS = {
    "JORNADA_INICIO", "JORNADA_FIN", "DESCANSO_INICIO", "DESCANSO_FIN",
    "OP_INICIO", "OP_FIN", "PARADA_INICIO", "PARADA_FIN",
}
UMBRAL_MANIPULACION_S = 90


@dataclass(frozen=True)
class Evento:
    event_id: str
    tipo: str
    ts: datetime
    ticket_operacion_id: Optional[int] = None
    causa: Optional[str] = None
    piezas: Optional[int] = None


@dataclass(frozen=True)
class Causa:
    codigo: str
    compensable: bool


@dataclass
class ResumenDia:
    min_estandar: float = 0.0
    min_trabajados: float = 0.0
    min_operacion: float = 0.0
    min_parada_compensable: float = 0.0
    min_parada_no_compensable: float = 0.0
    min_parada_sin_causa: float = 0.0
    min_hueco_sin_causa: float = 0.0
    min_manipulacion: float = 0.0
    min_descanso: float = 0.0
    piezas: int = 0
    min_improductivos: float = 0.0
    huecos_sin_causa: List[Tuple[datetime, datetime]] = field(default_factory=list)

    def a_dia_trabajador(self) -> DiaTrabajador:
        return DiaTrabajador(self.min_estandar, self.min_trabajados, self.min_improductivos)


def deduplicar(eventos: Iterable[Evento]) -> List[Evento]:
    """Descarta eventos repetidos (mismo event_id) y ordena por hora."""
    vistos: Dict[str, Evento] = {}
    for e in eventos:
        vistos.setdefault(e.event_id, e)
    return sorted(vistos.values(), key=lambda e: e.ts)


def _min(delta: timedelta) -> float:
    return delta.total_seconds() / 60.0


def resumen_dia(
    eventos: Iterable[Evento],
    smv_por_ticket_operacion: Mapping[int, float],
    causas: Mapping[str, Causa],
    politica: str = "compensables",
    umbral_manipulacion_s: int = UMBRAL_MANIPULACION_S,
) -> ResumenDia:
    """Calcula los minutos del día. Lanza ValueError si la secuencia de eventos es inválida."""
    if politica not in ("compensables", "todas"):
        raise ValueError("politica debe ser 'compensables' o 'todas'")
    evs = deduplicar(eventos)
    if not evs:
        raise ValueError("sin eventos")
    for e in evs:
        if e.tipo not in TIPOS:
            raise ValueError(f"tipo de evento desconocido: {e.tipo}")
    if evs[0].tipo != "JORNADA_INICIO":
        raise ValueError("el primer evento debe ser JORNADA_INICIO")
    if sum(e.tipo == "JORNADA_INICIO" for e in evs) != 1:
        raise ValueError("solo se admite una jornada por cálculo")

    r = ResumenDia()
    op_abierta: Optional[int] = None
    parada_causa: Optional[str] = None
    parada_abierta = False
    descanso = False
    libre_desde: Optional[datetime] = None
    prev = evs[0].ts
    cerrada = False

    def cerrar_libre(hasta: datetime) -> None:
        nonlocal libre_desde
        if libre_desde is None:
            return
        dur = hasta - libre_desde
        if dur.total_seconds() > umbral_manipulacion_s:
            r.min_hueco_sin_causa += _min(dur)
            r.huecos_sin_causa.append((libre_desde, hasta))
        else:
            r.min_manipulacion += _min(dur)
        libre_desde = None

    def atribuir(hasta: datetime) -> None:
        nonlocal prev, libre_desde
        if hasta < prev:
            raise ValueError("eventos fuera de orden")
        dur = hasta - prev
        if descanso:
            r.min_descanso += _min(dur)
        elif parada_abierta:
            m = _min(dur)
            if parada_causa is None:
                r.min_parada_sin_causa += m
            elif causas[parada_causa].compensable:
                r.min_parada_compensable += m
            else:
                r.min_parada_no_compensable += m
        elif op_abierta is not None:
            r.min_operacion += _min(dur)
        elif dur > timedelta(0) and libre_desde is None:
            libre_desde = prev
        prev = hasta

    inicio = evs[0].ts
    libre_desde = inicio
    for e in evs[1:]:
        if cerrada:
            raise ValueError("hay eventos posteriores a JORNADA_FIN")
        # Antes de atribuir, un hueco libre en curso se cierra si el estado va a cambiar.
        estaba_libre = not descanso and not parada_abierta and op_abierta is None
        atribuir(e.ts)
        t = e.tipo
        if t == "OP_INICIO":
            if op_abierta is not None:
                raise ValueError("OP_INICIO con otra operación abierta")
            if e.ticket_operacion_id not in smv_por_ticket_operacion:
                raise ValueError(f"operación de ticket desconocida: {e.ticket_operacion_id}")
            if estaba_libre:
                cerrar_libre(e.ts)
            op_abierta = e.ticket_operacion_id
        elif t == "OP_FIN":
            if op_abierta is None or e.ticket_operacion_id != op_abierta:
                raise ValueError("OP_FIN sin OP_INICIO correspondiente")
            piezas = e.piezas or 0
            r.piezas += piezas
            r.min_estandar += piezas * smv_por_ticket_operacion[op_abierta]
            op_abierta = None
            libre_desde = e.ts
        elif t == "PARADA_INICIO":
            if parada_abierta:
                raise ValueError("PARADA_INICIO con otra parada abierta")
            if e.causa is not None and e.causa not in causas:
                raise ValueError(f"causa desconocida: {e.causa}")
            if estaba_libre:
                cerrar_libre(e.ts)
            parada_abierta, parada_causa = True, e.causa
        elif t == "PARADA_FIN":
            if not parada_abierta:
                raise ValueError("PARADA_FIN sin PARADA_INICIO")
            parada_abierta, parada_causa = False, None
            if op_abierta is None and not descanso:
                libre_desde = e.ts
        elif t == "DESCANSO_INICIO":
            if descanso:
                raise ValueError("DESCANSO_INICIO con descanso abierto")
            if estaba_libre:
                cerrar_libre(e.ts)
            descanso = True
        elif t == "DESCANSO_FIN":
            if not descanso:
                raise ValueError("DESCANSO_FIN sin DESCANSO_INICIO")
            descanso = False
            if op_abierta is None and not parada_abierta:
                libre_desde = e.ts
        elif t == "JORNADA_FIN":
            if estaba_libre:
                cerrar_libre(e.ts)
            r.min_trabajados = _min(e.ts - inicio) - r.min_descanso
            cerrada = True
        elif t == "JORNADA_INICIO":
            raise ValueError("solo se admite una jornada por cálculo")

    if not cerrada:
        raise ValueError("falta JORNADA_FIN")

    r.min_improductivos = r.min_parada_compensable
    if politica == "todas":
        r.min_improductivos += r.min_parada_no_compensable
    return r
