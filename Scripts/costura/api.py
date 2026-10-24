"""API REST de la app de tablet (Documentación/costura/03-app-tablet.md, sección 5).

Autenticación:
- Cada tablet se registra y un administrador la aprueba; usa su token en `X-Dispositivo-Token`.
- La costurera inicia sesión con gafete + PIN y recibe un token de sesión (`Authorization: Bearer`).
- Las rutas de administración usan `X-Admin-Token`.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import AwareDatetime, BaseModel, Field

from formulas import eficiencia_compensada
from repositorio import Repositorio, verificar_secreto
from segmentos import TIPOS, Evento, resumen_dia
from tickets import generar_tickets, validar_codigo

DURACION_SESION = timedelta(hours=12)
MAX_INTENTOS_PIN = 5
VENTANA_INTENTOS = timedelta(minutes=10)
TZ_PLANTA = timezone(timedelta(hours=-5))  # Perú


class DispositivoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)


class SesionIn(BaseModel):
    gafete: str
    pin: str


class EventoIn(BaseModel):
    event_id: str = Field(min_length=8, max_length=64)
    tipo: str
    ts: AwareDatetime
    ticket_operacion_id: Optional[int] = None
    causa: Optional[str] = None
    piezas: Optional[int] = Field(default=None, ge=0)


class LineaIn(BaseModel):
    color: str
    talla: str
    cantidad: int = Field(gt=0)


class OperacionIn(BaseModel):
    operacion_id: int
    nombre: str
    smv: float = Field(gt=0)


class GenerarTicketsIn(BaseModel):
    lineas: List[LineaIn] = Field(min_length=1)
    tam_paquete: int = Field(gt=0)
    operaciones: List[OperacionIn] = Field(min_length=1)


def crear_app(
    repo: Repositorio,
    admin_token: str,
    ahora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    politica: str = "compensables",
) -> FastAPI:
    app = FastAPI(title="Costura · app de tablet", version="1")

    # ---------- dependencias de autenticación ----------
    def admin(x_admin_token: str = Header(default="")) -> None:
        if not hmac.compare_digest(x_admin_token, admin_token):
            raise HTTPException(401, "token de administración inválido")

    def dispositivo(x_dispositivo_token: str = Header(default="")):
        d = repo.dispositivo_por_token(x_dispositivo_token) if x_dispositivo_token else None
        if d is None or d.estado != "aprobado":
            raise HTTPException(401, "dispositivo no autorizado")
        return d

    def sesion(authorization: str = Header(default="")):
        token = authorization.removeprefix("Bearer ").strip()
        s = repo.sesiones.get(token)
        if s is None or s[2] <= ahora():
            raise HTTPException(401, "sesión inválida o vencida")
        return s  # (operaria_id, dispositivo_id, vence)

    # ---------- dispositivos ----------
    @app.post("/api/v1/dispositivos", status_code=201)
    def registrar_dispositivo(body: DispositivoIn):
        d, token = repo.registrar_dispositivo(body.nombre)
        return {"id": d.id, "estado": d.estado, "token": token}  # el token solo se muestra una vez

    @app.post("/api/v1/dispositivos/{id}/aprobar", dependencies=[Depends(admin)])
    def aprobar_dispositivo(id: int):
        d = repo.dispositivos.get(id)
        if d is None:
            raise HTTPException(404, "dispositivo no encontrado")
        d.estado = "aprobado"
        return {"id": d.id, "estado": d.estado}

    # ---------- sesión ----------
    @app.post("/api/v1/sesion")
    def iniciar_sesion(body: SesionIn, disp=Depends(dispositivo)):
        op = repo.operaria_por_gafete(body.gafete)
        t = ahora()
        if op is None:
            raise HTTPException(401, "gafete o PIN incorrecto")
        intentos = [x for x in repo.intentos_pin.get(op.id, []) if t - x < VENTANA_INTENTOS]
        if len(intentos) >= MAX_INTENTOS_PIN:
            raise HTTPException(429, "demasiados intentos; espere unos minutos")
        if not verificar_secreto(body.pin, op.pin_hash):
            intentos.append(t)
            repo.intentos_pin[op.id] = intentos
            raise HTTPException(401, "gafete o PIN incorrecto")
        repo.intentos_pin.pop(op.id, None)
        token = secrets.token_urlsafe(32)
        repo.sesiones[token] = (op.id, disp.id, t + DURACION_SESION)
        return {"token": token, "operaria": {"id": op.id, "nombre": op.nombre}, "hora_servidor": t.isoformat()}

    # ---------- consulta ----------
    @app.get("/api/v1/causas")
    def causas(_s=Depends(sesion)):
        return [{"codigo": c.codigo, "compensable": c.compensable} for c in repo.causas.values()]

    @app.get("/api/v1/tickets/{codigo}")
    def ver_ticket(codigo: str, _s=Depends(sesion)):
        if not validar_codigo(codigo):
            raise HTTPException(422, "código de ticket inválido")
        t = repo.tickets.get(codigo)
        if t is None:
            raise HTTPException(404, "ticket no encontrado")
        if t.estado == "anulado":
            raise HTTPException(409, "ticket anulado")
        return {
            "codigo": t.codigo, "orden": t.orden, "color": t.color, "talla": t.talla, "cantidad": t.cantidad,
            "operaciones": [
                {"ticket_operacion_id": o.id, "secuencia": o.secuencia, "operacion_id": o.operacion_id,
                 "nombre": o.nombre, "smv": o.smv} for o in t.operaciones],
        }

    # ---------- eventos ----------
    @app.post("/api/v1/eventos")
    def enviar_eventos(lote: List[EventoIn], s=Depends(sesion)):
        if len(lote) > 500:
            raise HTTPException(413, "lote demasiado grande")
        smv = repo.smv_por_ticket_operacion()
        t = ahora()
        for e in lote:  # se valida todo el lote antes de guardar nada
            if e.tipo not in TIPOS:
                raise HTTPException(422, f"tipo de evento desconocido: {e.tipo}")
            if e.tipo in ("OP_INICIO", "OP_FIN") and e.ticket_operacion_id not in smv:
                raise HTTPException(422, "ticket_operacion_id desconocido")
            if e.causa is not None and e.causa not in repo.causas:
                raise HTTPException(422, f"causa desconocida: {e.causa}")
            if e.ts > t + timedelta(minutes=5):
                raise HTTPException(422, "hora en el futuro; revisar el reloj de la tablet")
        nuevos = duplicados = 0
        for e in lote:
            ev = Evento(e.event_id, e.tipo, e.ts, e.ticket_operacion_id, e.causa, e.piezas)
            if repo.guardar_evento(ev, s[0], s[1], t):
                nuevos += 1
            else:
                duplicados += 1
        return {"aceptados": nuevos, "duplicados": duplicados}

    # ---------- resumen ----------
    @app.get("/api/v1/resumen/hoy")
    def resumen_hoy(s=Depends(sesion)):
        t = ahora()
        hoy = t.astimezone(TZ_PLANTA).date()
        evs = [e for e in repo.eventos_de(s[0]) if e.ts.astimezone(TZ_PLANTA).date() == hoy]
        if not evs:
            raise HTTPException(404, "sin eventos hoy")
        parcial = not any(e.tipo == "JORNADA_FIN" for e in evs)
        if parcial:
            evs.append(Evento("sintetico-fin", "JORNADA_FIN", max(t, max(e.ts for e in evs))))
        try:
            r = resumen_dia(evs, repo.smv_por_ticket_operacion(), repo.causas, politica)
        except ValueError as exc:
            raise HTTPException(409, f"eventos inconsistentes: {exc}") from exc
        ef = eficiencia_compensada(r.min_estandar, r.min_trabajados, r.min_improductivos)
        return {
            "parcial": parcial, "piezas": r.piezas,
            "min_estandar": round(r.min_estandar, 2), "min_trabajados": round(r.min_trabajados, 2),
            "min_improductivos": round(r.min_improductivos, 2),
            "min_hueco_sin_causa": round(r.min_hueco_sin_causa, 2),
            "ef_compensada": None if ef is None else round(ef, 4),
        }

    # ---------- administración de tickets ----------
    @app.post("/api/v1/ordenes/{orden}/tickets", status_code=201, dependencies=[Depends(admin)])
    def crear_tickets(orden: str, body: GenerarTicketsIn):
        total = sum(
            -(-l.cantidad // body.tam_paquete) for l in body.lineas)  # paquetes, redondeando hacia arriba
        inicio = repo.siguiente_secuencia_ticket(total)
        nuevos = generar_tickets(orden, [(l.color, l.talla, l.cantidad) for l in body.lineas],
                                 body.tam_paquete, inicio)
        guardados = repo.guardar_tickets(nuevos, [o.model_dump() for o in body.operaciones])
        return [{"codigo": g.codigo, "color": g.color, "talla": g.talla, "cantidad": g.cantidad} for g in guardados]

    @app.post("/api/v1/tickets/{codigo}/anular", dependencies=[Depends(admin)])
    def anular_ticket(codigo: str):
        t = repo.tickets.get(codigo)
        if t is None:
            raise HTTPException(404, "ticket no encontrado")
        t.estado = "anulado"
        return {"codigo": codigo, "estado": t.estado}

    return app
