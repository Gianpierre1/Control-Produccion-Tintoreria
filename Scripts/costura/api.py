"""API REST de la app de tablet (Documentación/costura/03-app-tablet.md, sección 5).

Autenticación:
- Cada tablet se registra y un administrador la aprueba; usa su token en `X-Dispositivo-Token`.
- La costurera inicia sesión con gafete + PIN y recibe un token de sesión (`Authorization: Bearer`).
- Las rutas de administración usan `X-Admin-Token`.
"""

from __future__ import annotations

import hmac
import secrets
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import AwareDatetime, BaseModel, Field

from operaciones import TIPOS, Evento, Motivo, calcular
from repositorio import Repositorio, verificar_secreto
from tarifas import SinTarifa, Tarifa, buscar_tarifa
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
    motivo: Optional[str] = None
    piezas: Optional[int] = Field(default=None, ge=0)


class LineaIn(BaseModel):
    color: str
    talla: str
    cantidad: int = Field(gt=0)


class OperacionIn(BaseModel):
    operacion_id: int
    nombre: str
    smv: Optional[float] = Field(default=None, gt=0)  # si falta, se usa la tarifa vigente


class GenerarTicketsIn(BaseModel):
    lineas: List[LineaIn] = Field(min_length=1)
    tam_paquete: int = Field(gt=0)
    operaciones: List[OperacionIn] = Field(min_length=1)
    tipo_prenda: Optional[str] = None


class MotivoIn(BaseModel):
    codigo: str = Field(min_length=2, max_length=10, pattern=r"^[A-Z0-9_]+$")
    descripcion: str = Field(min_length=1, max_length=80)
    limite_min: float = Field(ge=0)


class MotivoCambio(BaseModel):
    descripcion: Optional[str] = Field(default=None, min_length=1, max_length=80)
    limite_min: Optional[float] = Field(default=None, ge=0)
    activo: Optional[bool] = None


class TarifaIn(BaseModel):
    operacion_id: int
    min_por_pieza: float = Field(gt=0)
    tipo_prenda: Optional[str] = None
    cantidad_min: int = Field(default=1, ge=1)
    cantidad_max: Optional[int] = Field(default=None, ge=1)
    vigente_desde: Optional[date] = None
    vigente_hasta: Optional[date] = None


class TarifaCierre(BaseModel):
    vigente_hasta: date


def crear_app(
    repo: Repositorio,
    admin_token: str,
    ahora: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
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
    @app.get("/api/v1/motivos")
    def motivos(_s=Depends(sesion)):
        return [{"codigo": m.codigo, "descripcion": m.descripcion, "limite_min": m.limite_min}
                for m in repo.motivos.values() if m.activo]

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
            "codigo": t.codigo, "orden": t.orden, "tipo_prenda": t.tipo_prenda, "color": t.color, "talla": t.talla, "cantidad": t.cantidad,
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
            if e.tipo == "PAUSA_INICIO" and not (e.motivo in repo.motivos and repo.motivos[e.motivo].activo):
                raise HTTPException(422, f"motivo desconocido: {e.motivo}")
            if e.ts > t + timedelta(minutes=5):
                raise HTTPException(422, "hora en el futuro; revisar el reloj de la tablet")
        nuevos = duplicados = 0
        for e in lote:
            ev = Evento(e.event_id, e.tipo, e.ts, e.ticket_operacion_id, e.motivo, e.piezas)
            if repo.guardar_evento(ev, s[0], s[1], t):
                nuevos += 1
            else:
                duplicados += 1
        return {"aceptados": nuevos, "duplicados": duplicados}

    # ---------- resumen ----------
    @app.get("/api/v1/resumen/hoy")
    def resumen_hoy(s=Depends(sesion)):
        hoy = ahora().astimezone(TZ_PLANTA).date()
        evs = [e for e in repo.eventos_de(s[0]) if e.ts.astimezone(TZ_PLANTA).date() == hoy]
        if not evs:
            raise HTTPException(404, "sin eventos hoy")
        try:
            r = calcular(evs, repo.smv_por_ticket_operacion(), repo.motivos)
        except ValueError as exc:
            raise HTTPException(409, f"eventos inconsistentes: {exc}") from exc
        return {
            "operaciones_terminadas": len(r.operaciones),
            "operacion_abierta": r.operacion_abierta,
            "piezas": sum(o.piezas for o in r.operaciones),
            "min_asignado": round(r.min_asignado, 2),
            "min_real": round(r.min_real, 2),
            "eficiencia": None if r.eficiencia is None else round(r.eficiencia, 4),
            "pausas_con_exceso": [
                {"motivo": p.motivo, "min_exceso": round(p.min_exceso, 2)} for p in r.pausas_con_exceso],
        }

    # ---------- administración de motivos de pausa ----------
    @app.post("/api/v1/motivos", status_code=201, dependencies=[Depends(admin)])
    def crear_motivo(body: MotivoIn):
        if body.codigo in repo.motivos:
            raise HTTPException(409, "ya existe un motivo con ese código")
        repo.motivos[body.codigo] = Motivo(body.codigo, body.limite_min, body.descripcion)
        return {"codigo": body.codigo, "descripcion": body.descripcion, "limite_min": body.limite_min, "activo": True}

    @app.put("/api/v1/motivos/{codigo}", dependencies=[Depends(admin)])
    def cambiar_motivo(codigo: str, body: MotivoCambio):
        m = repo.motivos.get(codigo)
        if m is None:
            raise HTTPException(404, "motivo no encontrado")
        cambios = {k: v for k, v in body.model_dump().items() if v is not None}
        m = replace(m, **cambios)
        repo.motivos[codigo] = m
        return {"codigo": m.codigo, "descripcion": m.descripcion, "limite_min": m.limite_min, "activo": m.activo}

    # ---------- administración de tarifas (tiempo asignado) ----------
    @app.post("/api/v1/tarifas", status_code=201, dependencies=[Depends(admin)])
    def crear_tarifa(body: TarifaIn):
        try:
            t = Tarifa(body.operacion_id, body.min_por_pieza, body.tipo_prenda, body.cantidad_min,
                       body.cantidad_max, body.vigente_desde or ahora().astimezone(TZ_PLANTA).date(),
                       body.vigente_hasta)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"id": repo.agregar_tarifa(t)}

    @app.get("/api/v1/tarifas", dependencies=[Depends(admin)])
    def listar_tarifas():
        return [{"id": i, "operacion_id": t.operacion_id, "tipo_prenda": t.tipo_prenda,
                 "cantidad_min": t.cantidad_min, "cantidad_max": t.cantidad_max,
                 "min_por_pieza": t.min_por_pieza, "vigente_desde": t.vigente_desde.isoformat(),
                 "vigente_hasta": t.vigente_hasta.isoformat() if t.vigente_hasta else None}
                for i, t in repo.tarifas.items()]

    @app.put("/api/v1/tarifas/{id}", dependencies=[Depends(admin)])
    def cerrar_tarifa(id: int, body: TarifaCierre):
        """Una tarifa no se edita: se cierra su vigencia y se crea otra con el tiempo nuevo."""
        t = repo.tarifas.get(id)
        if t is None:
            raise HTTPException(404, "tarifa no encontrada")
        try:
            repo.tarifas[id] = replace(t, vigente_hasta=body.vigente_hasta)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"id": id, "vigente_hasta": body.vigente_hasta.isoformat()}

    # ---------- administración de tickets ----------
    @app.post("/api/v1/ordenes/{orden}/tickets", status_code=201, dependencies=[Depends(admin)])
    def crear_tickets(orden: str, body: GenerarTicketsIn):
        fecha = ahora().astimezone(TZ_PLANTA).date()
        inicio = repo.proxima_secuencia_ticket()
        nuevos = generar_tickets(orden, [(l.color, l.talla, l.cantidad) for l in body.lineas],
                                 body.tam_paquete, inicio)
        ops_por_ticket = []
        for t in nuevos:  # se resuelve el tiempo de cada ticket antes de guardar nada
            ops = []
            for o in body.operaciones:
                smv = o.smv
                if smv is None:
                    try:
                        smv = buscar_tarifa(repo.tarifas.values(), o.operacion_id, body.tipo_prenda,
                                            t.cantidad, fecha).min_por_pieza
                    except (SinTarifa, ValueError) as exc:
                        raise HTTPException(422, str(exc)) from exc
                ops.append({"operacion_id": o.operacion_id, "nombre": o.nombre, "smv": smv})
            ops_por_ticket.append(ops)
        repo.siguiente_secuencia_ticket(len(nuevos))
        guardados = repo.guardar_tickets(nuevos, ops_por_ticket, body.tipo_prenda)
        return [{"codigo": g.codigo, "color": g.color, "talla": g.talla, "cantidad": g.cantidad} for g in guardados]

    @app.post("/api/v1/tickets/{codigo}/anular", dependencies=[Depends(admin)])
    def anular_ticket(codigo: str):
        t = repo.tickets.get(codigo)
        if t is None:
            raise HTTPException(404, "ticket no encontrado")
        t.estado = "anulado"
        return {"codigo": codigo, "estado": t.estado}

    return app
