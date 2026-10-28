import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from operaciones import Evento, Motivo, calcular, deduplicar  # noqa: E402

TZ = timezone(timedelta(hours=-5))
MOTIVOS = {"BAN": Motivo("BAN", 10), "MAQ": Motivo("MAQ", 30), "REF": Motivo("REF", 60)}
SMV = {1: 2.0, 2: 1.5}
_n = 0


def ev(hhmm, tipo, **kw):
    global _n
    _n += 1
    partes = [int(x) for x in hhmm.split(":")]
    s = partes[2] if len(partes) == 3 else 0
    return Evento(f"e{_n}", tipo, datetime(2026, 10, 26, partes[0], partes[1], s, tzinfo=TZ), **kw)


def test_sin_pausas():
    r = calcular([ev("08:00", "OP_INICIO", ticket_operacion_id=1),
                  ev("09:00", "OP_FIN", ticket_operacion_id=1, piezas=25)], SMV, MOTIVOS)
    op = r.operaciones[0]
    assert op.min_real == pytest.approx(60) and op.min_asignado == pytest.approx(50)
    assert op.eficiencia == pytest.approx(50 / 60)


def test_pausa_dentro_del_tiempo_permitido_no_cuenta():
    r = calcular([ev("08:00", "OP_INICIO", ticket_operacion_id=1),
                  ev("08:20", "PAUSA_INICIO", motivo="BAN"), ev("08:28", "PAUSA_FIN"),
                  ev("09:00", "OP_FIN", ticket_operacion_id=1, piezas=25)], SMV, MOTIVOS)
    op = r.operaciones[0]
    assert op.min_pausa_permitida == pytest.approx(8) and op.min_pausa_exceso == 0
    assert op.min_real == pytest.approx(52)
    assert op.eficiencia == pytest.approx(50 / 52)
    assert r.pausas_con_exceso == []


def test_exceso_sobre_el_tiempo_permitido_si_cuenta():
    # baño permitido 10 min; se tomó 15: 10 se descuentan y 5 cuentan como tiempo real
    r = calcular([ev("08:00", "OP_INICIO", ticket_operacion_id=1),
                  ev("08:20", "PAUSA_INICIO", motivo="BAN"), ev("08:35", "PAUSA_FIN"),
                  ev("09:00", "OP_FIN", ticket_operacion_id=1, piezas=25)], SMV, MOTIVOS)
    op = r.operaciones[0]
    assert op.min_pausa_permitida == pytest.approx(10) and op.min_pausa_exceso == pytest.approx(5)
    assert op.min_real == pytest.approx(50)
    assert op.eficiencia == pytest.approx(1.0)
    assert len(r.pausas_con_exceso) == 1 and r.pausas_con_exceso[0].motivo == "BAN"


def test_varias_pausas_y_cada_una_con_su_motivo():
    r = calcular([ev("08:00", "OP_INICIO", ticket_operacion_id=1),
                  ev("08:10", "PAUSA_INICIO", motivo="BAN"), ev("08:15", "PAUSA_FIN"),
                  ev("08:30", "PAUSA_INICIO", motivo="MAQ"), ev("09:00", "PAUSA_FIN"),
                  ev("10:00", "OP_FIN", ticket_operacion_id=1, piezas=40)], SMV, MOTIVOS)
    op = r.operaciones[0]
    assert op.min_pausa_permitida == pytest.approx(5 + 30)
    assert op.min_real == pytest.approx(120 - 35)
    assert op.min_asignado == pytest.approx(80)


def test_eficiencia_del_dia_suma_minutos_no_promedia_porcentajes():
    r = calcular([
        ev("08:00", "OP_INICIO", ticket_operacion_id=1), ev("08:30", "OP_FIN", ticket_operacion_id=1, piezas=10),   # 20/30
        ev("09:00", "OP_INICIO", ticket_operacion_id=2), ev("12:00", "OP_FIN", ticket_operacion_id=2, piezas=200),  # 300/180
    ], SMV, MOTIVOS)
    assert r.min_asignado == pytest.approx(320) and r.min_real == pytest.approx(210)
    assert r.eficiencia == pytest.approx(320 / 210)
    promedio = (20 / 30 + 300 / 180) / 2
    assert r.eficiencia != pytest.approx(promedio)


def test_operacion_abierta_no_entra_en_el_calculo():
    r = calcular([ev("08:00", "OP_INICIO", ticket_operacion_id=1)], SMV, MOTIVOS)
    assert r.operacion_abierta == 1 and r.operaciones == [] and r.eficiencia is None


def test_jornada_se_ignora_y_deduplica():
    a = ev("08:00", "OP_INICIO", ticket_operacion_id=1)
    b = ev("09:00", "OP_FIN", ticket_operacion_id=1, piezas=25)
    assert [e.event_id for e in deduplicar([b, a, a])] == [a.event_id, b.event_id]
    r = calcular([ev("07:55", "JORNADA_INICIO"), b, a, a], SMV, MOTIVOS)
    assert len(r.operaciones) == 1


@pytest.mark.parametrize("evs", [
    [ev("08:00", "OP_FIN", ticket_operacion_id=1, piezas=1)],
    [ev("08:00", "OP_INICIO", ticket_operacion_id=1), ev("08:10", "OP_INICIO", ticket_operacion_id=2)],
    [ev("08:00", "PAUSA_INICIO", motivo="BAN")],
    [ev("08:00", "OP_INICIO", ticket_operacion_id=1), ev("08:10", "PAUSA_INICIO", motivo="XXX")],
    [ev("08:00", "OP_INICIO", ticket_operacion_id=1), ev("08:10", "PAUSA_FIN")],
    [ev("08:00", "OP_INICIO", ticket_operacion_id=1), ev("08:10", "PAUSA_INICIO", motivo="BAN"),
     ev("08:11", "OP_FIN", ticket_operacion_id=1, piezas=1)],
    [ev("08:00", "OP_INICIO", ticket_operacion_id=99)],
    [ev("08:00", "OP_INICIO", ticket_operacion_id=1), ev("08:10", "PAUSA_INICIO", motivo="BAN"),
     ev("08:11", "PAUSA_INICIO", motivo="MAQ")],
])
def test_secuencias_invalidas(evs):
    with pytest.raises(ValueError):
        calcular(evs, SMV, MOTIVOS)
