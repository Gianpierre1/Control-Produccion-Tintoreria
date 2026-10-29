"""Almacenamiento en memoria para desarrollo y tests de la API.

La implementación de producción usará PostgreSQL (schema.sql + schema_app.sql) con la
misma interfaz. Los eventos son inmutables y se aceptan una sola vez por event_id.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from operaciones import Evento, Motivo
from tarifas import Tarifa
from tickets import TicketNuevo


# Motivos de pausa iniciales. Los tiempos permitidos son PROVISIONALES: confirmar con la planta.
# Se pueden agregar, cambiar o dar de baja desde la API de administración (/api/v1/motivos).
MOTIVOS_INICIALES = [
    Motivo("BAN", 10, "Baño"),
    Motivo("MAQ", 30, "Falla de máquina"),
    Motivo("MAT", 20, "Falta de material"),
    Motivo("REF", 60, "Refrigerio"),
    Motivo("REU", 30, "Reunión"),
    Motivo("OTR", 10, "Otro"),
]


def hash_secreto(valor: str, sal: Optional[bytes] = None) -> str:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", valor.encode(), sal, 100_000)
    return sal.hex() + "$" + h.hex()


def verificar_secreto(valor: str, guardado: str) -> bool:
    sal_hex, _ = guardado.split("$", 1)
    return hmac.compare_digest(hash_secreto(valor, bytes.fromhex(sal_hex)), guardado)


@dataclass
class Dispositivo:
    id: int
    nombre: str
    token_hash: str
    estado: str = "pendiente"  # pendiente | aprobado | bloqueado


@dataclass
class Operaria:
    id: int
    nombre: str
    gafete: str
    pin_hash: str


@dataclass
class OperacionTicket:
    id: int
    secuencia: int
    operacion_id: int
    nombre: str
    smv: float


@dataclass
class Ticket:
    codigo: str
    orden: str
    color: str
    talla: str
    cantidad: int
    operaciones: List[OperacionTicket]
    estado: str = "activo"  # activo | anulado
    tipo_prenda: Optional[str] = None


@dataclass
class EventoGuardado:
    evento: Evento
    operaria_id: int
    dispositivo_id: int
    ts_servidor: datetime


@dataclass
class Repositorio:
    motivos: Dict[str, Motivo] = field(default_factory=dict)
    tarifas: Dict[int, Tarifa] = field(default_factory=dict)
    dispositivos: Dict[int, Dispositivo] = field(default_factory=dict)
    operarias: Dict[int, Operaria] = field(default_factory=dict)
    tickets: Dict[str, Ticket] = field(default_factory=dict)
    sesiones: Dict[str, tuple] = field(default_factory=dict)  # token -> (operaria_id, dispositivo_id, vence)
    eventos: Dict[str, EventoGuardado] = field(default_factory=dict)
    intentos_pin: Dict[int, List[datetime]] = field(default_factory=dict)
    _sig_ticket: int = 1
    _sig_oper_ticket: int = 1
    _sig_dispositivo: int = 1
    _sig_tarifa: int = 1

    # --- dispositivos ---
    def registrar_dispositivo(self, nombre: str) -> tuple[Dispositivo, str]:
        token = secrets.token_urlsafe(32)
        d = Dispositivo(self._sig_dispositivo, nombre, hash_secreto(token))
        self._sig_dispositivo += 1
        self.dispositivos[d.id] = d
        return d, token

    def dispositivo_por_token(self, token: str) -> Optional[Dispositivo]:
        for d in self.dispositivos.values():
            if verificar_secreto(token, d.token_hash):
                return d
        return None

    # --- operarias ---
    def agregar_operaria(self, id: int, nombre: str, gafete: str, pin: str) -> Operaria:
        o = Operaria(id, nombre, gafete, hash_secreto(pin))
        self.operarias[id] = o
        return o

    def operaria_por_gafete(self, gafete: str) -> Optional[Operaria]:
        return next((o for o in self.operarias.values() if o.gafete == gafete), None)

    # --- tickets ---
    def agregar_tarifa(self, t: Tarifa) -> int:
        id_ = self._sig_tarifa
        self._sig_tarifa += 1
        self.tarifas[id_] = t
        return id_

    def proxima_secuencia_ticket(self) -> int:
        return self._sig_ticket

    def siguiente_secuencia_ticket(self, cantidad: int) -> int:
        inicio = self._sig_ticket
        self._sig_ticket += cantidad
        return inicio

    def guardar_tickets(
        self, nuevos: List[TicketNuevo], ops_por_ticket: List[List[dict]], tipo_prenda: Optional[str] = None
    ) -> List[Ticket]:
        guardados = []
        for t, operaciones in zip(nuevos, ops_por_ticket):
            ops = []
            for i, op in enumerate(operaciones, start=1):
                ops.append(OperacionTicket(self._sig_oper_ticket, i, op["operacion_id"], op["nombre"], op["smv"]))
                self._sig_oper_ticket += 1
            tk = Ticket(t.codigo, t.orden, t.color, t.talla, t.cantidad, ops, tipo_prenda=tipo_prenda)
            self.tickets[tk.codigo] = tk
            guardados.append(tk)
        return guardados

    def smv_por_ticket_operacion(self) -> Dict[int, float]:
        return {op.id: op.smv for t in self.tickets.values() for op in t.operaciones}

    # --- eventos ---
    def guardar_evento(self, ev: Evento, operaria_id: int, dispositivo_id: int, ahora: datetime) -> bool:
        """True si es nuevo; False si ya existía (idempotente por event_id)."""
        if ev.event_id in self.eventos:
            return False
        self.eventos[ev.event_id] = EventoGuardado(ev, operaria_id, dispositivo_id, ahora)
        return True

    def eventos_de(self, operaria_id: int) -> List[Evento]:
        return [g.evento for g in self.eventos.values() if g.operaria_id == operaria_id]
