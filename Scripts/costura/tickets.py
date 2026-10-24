"""Generación de tickets de paquete (Documentación/costura/03-app-tablet.md, sección 4).

Código del ticket: "T" + 8 dígitos + dígito de control (Luhn). El código solo identifica
el ticket; el contenido se consulta en el servidor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

PREFIJO = "T"
LARGO_NUMERO = 8


def _luhn(numero: str) -> int:
    total = 0
    for i, ch in enumerate(reversed(numero)):
        d = int(ch)
        if i % 2 == 0:  # se duplica cada segundo dígito empezando por el de la derecha
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def codigo_ticket(secuencia: int) -> str:
    if secuencia < 0 or secuencia >= 10**LARGO_NUMERO:
        raise ValueError("secuencia fuera de rango")
    numero = f"{secuencia:0{LARGO_NUMERO}d}"
    return f"{PREFIJO}{numero}{_luhn(numero)}"


def validar_codigo(codigo: str) -> bool:
    """Valida formato y dígito de control, sin red."""
    if not isinstance(codigo, str) or len(codigo) != 1 + LARGO_NUMERO + 1:
        return False
    if codigo[0] != PREFIJO or not codigo[1:].isdigit():
        return False
    return int(codigo[-1]) == _luhn(codigo[1:-1])


def dividir_en_paquetes(cantidad: int, tam_paquete: int) -> List[int]:
    """Parte una cantidad en paquetes; el último lleva el resto."""
    if cantidad <= 0 or tam_paquete <= 0:
        raise ValueError("cantidad y tam_paquete deben ser > 0")
    completos, resto = divmod(cantidad, tam_paquete)
    return [tam_paquete] * completos + ([resto] if resto else [])


@dataclass(frozen=True)
class TicketNuevo:
    codigo: str
    orden: str
    color: str
    talla: str
    cantidad: int
    paquete: int  # número de paquete dentro del color y talla (desde 1)


def generar_tickets(
    orden: str,
    lineas: Iterable[Tuple[str, str, int]],
    tam_paquete: int,
    secuencia_inicial: int,
) -> List[TicketNuevo]:
    """Un ticket por paquete, para cada (color, talla, cantidad) de la orden."""
    tickets: List[TicketNuevo] = []
    seq = secuencia_inicial
    for color, talla, cantidad in lineas:
        for n, cant in enumerate(dividir_en_paquetes(cantidad, tam_paquete), start=1):
            tickets.append(TicketNuevo(codigo_ticket(seq), orden, color, talla, cant, n))
            seq += 1
    return tickets
