"""Tiempo asignado por operación (Documentación/costura/03-app-tablet.md, sección 6).

El tiempo asignado de una operación depende del tipo de operación, la cantidad de prendas
del ticket y el tipo de prenda. Se guarda como una tabla de tarifas editable: cambiar un
tiempo es agregar una tarifa nueva con otra fecha de vigencia, sin tocar el código ni los
tickets ya emitidos (cada ticket guarda el valor que se le aplicó al crearse).

Tiempo asignado de una operación terminada = piezas hechas × min_por_pieza.
Si en el ERP el tiempo viene como total por rango de cantidad, equivale a
min_por_pieza = total ÷ cantidad.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional


class SinTarifa(LookupError):
    """No hay una tarifa vigente para la operación, la prenda y la cantidad."""


@dataclass(frozen=True)
class Tarifa:
    operacion_id: int
    min_por_pieza: float
    tipo_prenda: Optional[str] = None      # None = aplica a todos los tipos de prenda
    cantidad_min: int = 1
    cantidad_max: Optional[int] = None     # None = sin tope
    vigente_desde: date = date.min
    vigente_hasta: Optional[date] = None   # None = sin fin

    def __post_init__(self) -> None:
        if self.min_por_pieza <= 0:
            raise ValueError("min_por_pieza debe ser > 0")
        if self.cantidad_min < 1 or (self.cantidad_max is not None and self.cantidad_max < self.cantidad_min):
            raise ValueError("rango de cantidad inválido")
        if self.vigente_hasta is not None and self.vigente_hasta < self.vigente_desde:
            raise ValueError("vigencia inválida")

    def aplica(self, operacion_id: int, tipo_prenda: Optional[str], cantidad: int, fecha: date) -> bool:
        return (
            self.operacion_id == operacion_id
            and (self.tipo_prenda is None or self.tipo_prenda == tipo_prenda)
            and self.cantidad_min <= cantidad
            and (self.cantidad_max is None or cantidad <= self.cantidad_max)
            and self.vigente_desde <= fecha
            and (self.vigente_hasta is None or fecha <= self.vigente_hasta)
        )

    def _especificidad(self) -> tuple:
        ancho = (self.cantidad_max if self.cantidad_max is not None else 10**9) - self.cantidad_min
        # más específica primero: tipo de prenda exacto, rango más angosto, vigencia más reciente
        return (self.tipo_prenda is not None, -ancho, self.vigente_desde.toordinal())


def buscar_tarifa(
    tarifas: Iterable[Tarifa], operacion_id: int, tipo_prenda: Optional[str], cantidad: int, fecha: date
) -> Tarifa:
    """Devuelve la tarifa más específica que aplica; lanza SinTarifa o ValueError (ambigua)."""
    candidatas = sorted(
        (t for t in tarifas if t.aplica(operacion_id, tipo_prenda, cantidad, fecha)),
        key=lambda t: t._especificidad(),
        reverse=True,
    )
    if not candidatas:
        raise SinTarifa(
            f"sin tarifa vigente para operación {operacion_id}, prenda {tipo_prenda!r}, cantidad {cantidad}")
    if len(candidatas) > 1 and candidatas[0]._especificidad() == candidatas[1]._especificidad():
        raise ValueError(
            f"tarifas ambiguas para operación {operacion_id}, prenda {tipo_prenda!r}, cantidad {cantidad}")
    return candidatas[0]
