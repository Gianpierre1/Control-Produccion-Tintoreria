"""Fórmulas oficiales de eficiencia (Documentación/costura/00-brief-tecnico.md, sección 2).

Reglas que no se cambian:
- Los indicadores agregados se calculan con minutos sumados, nunca promediando porcentajes.
- Eficiencia compensada (trabajador-día) = Min. estándar / (Min. trabajados - Min. improductivos).
- Compensada agregada = Σ(compensada × min. trabajados) / Σ min. trabajados, solo con filas con dato.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class DiaTrabajador:
    """Datos de un trabajador en un día (minutos)."""

    min_estandar: float
    min_trabajados: float
    min_improductivos: float = 0.0


def min_estandar(piezas: int, smv: float) -> float:
    """Minutos estándar = piezas producidas × SMV de la operación."""
    if piezas < 0 or smv <= 0:
        raise ValueError("piezas debe ser >= 0 y smv > 0")
    return piezas * smv


def eficiencia_compensada(
    min_est: float, min_trab: float, min_improd: float
) -> Optional[float]:
    """Min. estándar ÷ (Min. trabajados − Min. improductivos). None si el divisor es <= 0."""
    base = min_trab - min_improd
    if base <= 0:
        return None
    return min_est / base


def eficiencia_real(filas: Iterable[DiaTrabajador]) -> Optional[float]:
    """Σ Min. estándar ÷ Σ Min. trabajados (minutos sumados)."""
    filas = list(filas)
    trab = sum(f.min_trabajados for f in filas)
    if trab <= 0:
        return None
    return sum(f.min_estandar for f in filas) / trab


def pct_improductivo(filas: Iterable[DiaTrabajador]) -> Optional[float]:
    """Σ Min. improductivos ÷ Σ Min. trabajados (minutos sumados)."""
    filas = list(filas)
    trab = sum(f.min_trabajados for f in filas)
    if trab <= 0:
        return None
    return sum(f.min_improductivos for f in filas) / trab


def compensada_agregada(filas: Iterable[DiaTrabajador]) -> Optional[float]:
    """Σ(compensada × min. trabajados) ÷ Σ min. trabajados, solo filas con compensada calculable."""
    num = 0.0
    den = 0.0
    for f in filas:
        c = eficiencia_compensada(f.min_estandar, f.min_trabajados, f.min_improductivos)
        if c is None or f.min_trabajados <= 0:
            continue
        num += c * f.min_trabajados
        den += f.min_trabajados
    if den <= 0:
        return None
    return num / den


def incentivo_total(incentivos: Iterable[float]) -> float:
    """Σ Incentivo (suma directa)."""
    return sum(incentivos)
