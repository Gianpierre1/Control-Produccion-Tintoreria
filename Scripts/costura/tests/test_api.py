import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import crear_app  # noqa: E402
from repositorio import Repositorio  # noqa: E402
from segmentos import Causa  # noqa: E402

TZ = timezone(timedelta(hours=-5))
ADMIN = {"X-Admin-Token": "admin-secreto"}
RELOJ = {"t": datetime(2026, 10, 26, 18, 0, tzinfo=TZ)}


@pytest.fixture()
def contexto():
    RELOJ["t"] = datetime(2026, 10, 26, 18, 0, tzinfo=TZ)
    repo = Repositorio()
    repo.causas = {"MAT": Causa("MAT", True), "REP": Causa("REP", False)}
    repo.agregar_operaria(7, "Rosa", "G-0007", "4821")
    app = crear_app(repo, "admin-secreto", ahora=lambda: RELOJ["t"])
    cli = TestClient(app)
    d = cli.post("/api/v1/dispositivos", json={"nombre": "Tablet 01"}).json()
    cli.post(f"/api/v1/dispositivos/{d['id']}/aprobar", headers=ADMIN)
    return cli, repo, {"X-Dispositivo-Token": d["token"]}


def sesion(cli, disp, pin="4821"):
    r = cli.post("/api/v1/sesion", json={"gafete": "G-0007", "pin": pin}, headers=disp)
    return r


def crear_ticket(cli):
    r = cli.post("/api/v1/ordenes/OP-1/tickets", headers=ADMIN, json={
        "lineas": [{"color": "Azul", "talla": "M", "cantidad": 50}], "tam_paquete": 30,
        "operaciones": [{"operacion_id": 10, "nombre": "Pegar cuello", "smv": 2.0}]})
    assert r.status_code == 201
    return r.json()


def test_flujo_completo(contexto):
    cli, repo, disp = contexto
    tickets = crear_ticket(cli)
    assert [t["cantidad"] for t in tickets] == [30, 20]

    token = sesion(cli, disp).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    t = cli.get(f"/api/v1/tickets/{tickets[0]['codigo']}", headers=h).json()
    assert t["color"] == "Azul" and t["operaciones"][0]["nombre"] == "Pegar cuello"
    top = t["operaciones"][0]["ticket_operacion_id"]

    def e(i, tipo, hhmm, **kw):
        h_, m_ = hhmm.split(":")
        return {"event_id": f"ev-{i:08d}", "tipo": tipo,
                "ts": datetime(2026, 10, 26, int(h_), int(m_), tzinfo=TZ).isoformat(), **kw}

    lote = [e(1, "JORNADA_INICIO", "08:00"), e(2, "OP_INICIO", "08:00", ticket_operacion_id=top),
            e(3, "PARADA_INICIO", "09:00", causa="MAT"), e(4, "PARADA_FIN", "09:30"),
            e(5, "OP_FIN", "10:00", ticket_operacion_id=top, piezas=30),
            e(6, "JORNADA_FIN", "17:00")]
    r = cli.post("/api/v1/eventos", json=lote, headers=h)
    assert r.json() == {"aceptados": 6, "duplicados": 0}
    # reenvío del mismo lote: idempotente
    assert cli.post("/api/v1/eventos", json=lote, headers=h).json() == {"aceptados": 0, "duplicados": 6}

    res = cli.get("/api/v1/resumen/hoy", headers=h).json()
    assert res["parcial"] is False
    assert res["piezas"] == 30 and res["min_estandar"] == 60.0
    assert res["min_trabajados"] == 540.0 and res["min_improductivos"] == 30.0
    assert res["min_hueco_sin_causa"] == 420.0  # 10:00 a 17:00 sin actividad
    assert res["ef_compensada"] == pytest.approx(60 / 510, abs=1e-4)


def test_resumen_parcial_antes_de_cerrar_la_jornada(contexto):
    cli, repo, disp = contexto
    h = {"Authorization": f"Bearer {sesion(cli, disp).json()['token']}"}
    cli.post("/api/v1/eventos", headers=h, json=[
        {"event_id": "ev-00000001", "tipo": "JORNADA_INICIO", "ts": datetime(2026, 10, 26, 8, 0, tzinfo=TZ).isoformat()}])
    res = cli.get("/api/v1/resumen/hoy", headers=h).json()
    assert res["parcial"] is True and res["min_trabajados"] == 600.0


def test_dispositivo_no_aprobado_no_puede_iniciar_sesion(contexto):
    cli, _, _ = contexto
    d = cli.post("/api/v1/dispositivos", json={"nombre": "Tablet 02"}).json()
    r = cli.post("/api/v1/sesion", json={"gafete": "G-0007", "pin": "4821"},
                 headers={"X-Dispositivo-Token": d["token"]})
    assert r.status_code == 401


def test_pin_incorrecto_y_bloqueo_por_intentos(contexto):
    cli, _, disp = contexto
    for _ in range(5):
        assert sesion(cli, disp, pin="0000").status_code == 401
    assert sesion(cli, disp, pin="4821").status_code == 429       # bloqueada aunque el PIN sea correcto
    RELOJ["t"] += timedelta(minutes=11)
    assert sesion(cli, disp, pin="4821").status_code == 200


def test_sesion_vencida(contexto):
    cli, _, disp = contexto
    h = {"Authorization": f"Bearer {sesion(cli, disp).json()['token']}"}
    assert cli.get("/api/v1/causas", headers=h).status_code == 200
    RELOJ["t"] += timedelta(hours=13)
    assert cli.get("/api/v1/causas", headers=h).status_code == 401


def test_rutas_de_administracion_requieren_token(contexto):
    cli, _, _ = contexto
    r = cli.post("/api/v1/ordenes/OP-1/tickets", json={})
    assert r.status_code == 401


def test_ticket_invalido_inexistente_y_anulado(contexto):
    cli, _, disp = contexto
    h = {"Authorization": f"Bearer {sesion(cli, disp).json()['token']}"}
    codigo = crear_ticket(cli)[0]["codigo"]
    assert cli.get("/api/v1/tickets/T123", headers=h).status_code == 422
    assert cli.get("/api/v1/tickets/T000999990", headers=h).status_code in (404, 422)
    assert cli.post(f"/api/v1/tickets/{codigo}/anular", headers=ADMIN).status_code == 200
    assert cli.get(f"/api/v1/tickets/{codigo}", headers=h).status_code == 409


def test_lote_con_un_evento_invalido_no_guarda_nada(contexto):
    cli, repo, disp = contexto
    h = {"Authorization": f"Bearer {sesion(cli, disp).json()['token']}"}
    ts = datetime(2026, 10, 26, 8, 0, tzinfo=TZ).isoformat()
    r = cli.post("/api/v1/eventos", headers=h, json=[
        {"event_id": "ev-00000001", "tipo": "JORNADA_INICIO", "ts": ts},
        {"event_id": "ev-00000002", "tipo": "PARADA_INICIO", "ts": ts, "causa": "NOEXISTE"}])
    assert r.status_code == 422
    assert repo.eventos == {}


def test_evento_en_el_futuro_se_rechaza(contexto):
    cli, _, disp = contexto
    h = {"Authorization": f"Bearer {sesion(cli, disp).json()['token']}"}
    futuro = (RELOJ["t"] + timedelta(hours=2)).isoformat()
    r = cli.post("/api/v1/eventos", headers=h,
                 json=[{"event_id": "ev-00000001", "tipo": "JORNADA_INICIO", "ts": futuro}])
    assert r.status_code == 422


def test_eventos_sin_zona_horaria_se_rechazan(contexto):
    cli, _, disp = contexto
    h = {"Authorization": f"Bearer {sesion(cli, disp).json()['token']}"}
    r = cli.post("/api/v1/eventos", headers=h,
                 json=[{"event_id": "ev-00000001", "tipo": "JORNADA_INICIO", "ts": "2026-10-26T08:00:00"}])
    assert r.status_code == 422
