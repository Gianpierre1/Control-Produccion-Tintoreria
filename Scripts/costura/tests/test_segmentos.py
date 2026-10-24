import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from formulas import eficiencia_compensada  # noqa: E402
from segmentos import Causa, Evento, deduplicar, resumen_dia  # noqa: E402

TZ = timezone(timedelta(hours=-5))
CAUSAS = {"MAT": Causa("MAT", True), "MAQ": Causa("MAQ", True), "REP": Causa("REP", False)}
SMV = {1: 2.0, 2: 1.5, 3: 2.0}
_n = 0


def ev(hhmm, tipo, **kw):
    global _n
    _n += 1
    partes = [int(x) for x in hhmm.split(":")]
    h, m = partes[0], partes[1]
    s = partes[2] if len(partes) == 3 else 0
    return Evento(f"e{_n}", tipo, datetime(2026, 10, 26, h, m, s, tzinfo=TZ), **kw)


def dia_tipico():
    return [
        ev("08:00", "JORNADA_INICIO"),
        ev("08:00", "OP_INICIO", ticket_operacion_id=1),
        ev("09:00", "PARADA_INICIO", causa="MAT"),
        ev("09:20", "PARADA_FIN"),
        ev("11:00", "OP_FIN", ticket_operacion_id=1, piezas=100),   # 200 min estándar
        ev("11:01", "OP_INICIO", ticket_operacion_id=2),            # hueco de 60 s: manipulación
        ev("12:00", "OP_FIN", ticket_operacion_id=2, piezas=40),    # 60 min estándar
        ev("12:00", "DESCANSO_INICIO"),
        ev("13:00", "DESCANSO_FIN"),
        ev("13:10", "OP_INICIO", ticket_operacion_id=3),            # hueco de 10 min: sin causa
        ev("14:00", "PARADA_INICIO", causa="REP"),
        ev("14:30", "PARADA_FIN"),
        ev("17:00", "OP_FIN", ticket_operacion_id=3, piezas=80),    # 160 min estándar
        ev("17:00", "JORNADA_FIN"),
    ]


def test_dia_tipico_politica_compensables():
    r = resumen_dia(dia_tipico(), SMV, CAUSAS)
    assert r.min_trabajados == pytest.approx(480)           # 540 - 60 de descanso
    assert r.min_estandar == pytest.approx(420)
    assert r.piezas == 220
    assert r.min_parada_compensable == pytest.approx(20)
    assert r.min_parada_no_compensable == pytest.approx(30)
    assert r.min_hueco_sin_causa == pytest.approx(10)
    assert r.min_manipulacion == pytest.approx(1)
    assert r.min_improductivos == pytest.approx(20)
    assert len(r.huecos_sin_causa) == 1
    d = r.a_dia_trabajador()
    assert eficiencia_compensada(d.min_estandar, d.min_trabajados, d.min_improductivos) == pytest.approx(420 / 460)


def test_dia_tipico_politica_todas():
    r = resumen_dia(dia_tipico(), SMV, CAUSAS, politica="todas")
    assert r.min_improductivos == pytest.approx(50)
    assert eficiencia_compensada(r.min_estandar, r.min_trabajados, r.min_improductivos) == pytest.approx(420 / 430)


def test_hueco_corto_es_manipulacion_y_largo_es_sin_causa():
    base = [ev("08:00", "JORNADA_INICIO"), ev("08:00:30", "OP_INICIO", ticket_operacion_id=1),
            ev("08:30", "OP_FIN", ticket_operacion_id=1, piezas=10),
            ev("08:31", "OP_INICIO", ticket_operacion_id=1),
            ev("09:00", "OP_FIN", ticket_operacion_id=1, piezas=10),
            ev("09:00", "JORNADA_FIN")]
    r = resumen_dia(base, SMV, CAUSAS, umbral_manipulacion_s=90)
    assert r.min_manipulacion == pytest.approx(1.5)    # 30 s al inicio + 60 s entre operaciones
    assert r.min_hueco_sin_causa == 0
    r2 = resumen_dia(base, SMV, CAUSAS, umbral_manipulacion_s=45)
    assert r2.min_hueco_sin_causa == pytest.approx(1.0)  # solo el hueco de 60 s supera 45 s
    assert r2.min_manipulacion == pytest.approx(0.5)


def test_parada_sin_causa_no_se_descuenta():
    evs = [ev("08:00", "JORNADA_INICIO"), ev("08:00", "OP_INICIO", ticket_operacion_id=1),
           ev("09:00", "PARADA_INICIO"), ev("09:30", "PARADA_FIN"),
           ev("10:00", "OP_FIN", ticket_operacion_id=1, piezas=30), ev("10:00", "JORNADA_FIN")]
    r = resumen_dia(evs, SMV, CAUSAS, politica="todas")
    assert r.min_parada_sin_causa == pytest.approx(30)
    assert r.min_improductivos == 0


def test_operacion_abierta_al_cerrar_la_jornada_no_suma_piezas():
    evs = [ev("08:00", "JORNADA_INICIO"), ev("08:00", "OP_INICIO", ticket_operacion_id=1),
           ev("10:00", "JORNADA_FIN")]
    r = resumen_dia(evs, SMV, CAUSAS)
    assert r.min_operacion == pytest.approx(120)
    assert r.piezas == 0 and r.min_estandar == 0


def test_deduplicar_por_event_id_y_orden():
    a = ev("08:00", "JORNADA_INICIO")
    b = ev("09:00", "JORNADA_FIN")
    assert [e.event_id for e in deduplicar([b, a, a, b])] == [a.event_id, b.event_id]
    r = resumen_dia([b, a, a, b], SMV, CAUSAS)
    assert r.min_trabajados == pytest.approx(60)


@pytest.mark.parametrize("evs", [
    [],
    [ev("08:00", "OP_INICIO", ticket_operacion_id=1)],
    [ev("08:00", "JORNADA_INICIO")],  # falta JORNADA_FIN
    [ev("08:00", "JORNADA_INICIO"), ev("08:10", "OP_INICIO", ticket_operacion_id=1),
     ev("08:20", "OP_INICIO", ticket_operacion_id=2), ev("09:00", "JORNADA_FIN")],
    [ev("08:00", "JORNADA_INICIO"), ev("08:10", "OP_FIN", ticket_operacion_id=1, piezas=1),
     ev("09:00", "JORNADA_FIN")],
    [ev("08:00", "JORNADA_INICIO"), ev("08:10", "PARADA_INICIO", causa="XXX"),
     ev("09:00", "JORNADA_FIN")],
    [ev("08:00", "JORNADA_INICIO"), ev("08:10", "OP_INICIO", ticket_operacion_id=99),
     ev("09:00", "JORNADA_FIN")],
    [ev("08:00", "JORNADA_INICIO"), ev("09:00", "JORNADA_FIN"), ev("09:10", "OP_INICIO", ticket_operacion_id=1)],
])
def test_secuencias_invalidas(evs):
    with pytest.raises(ValueError):
        resumen_dia(evs, SMV, CAUSAS)


def test_politica_invalida():
    with pytest.raises(ValueError):
        resumen_dia(dia_tipico(), SMV, CAUSAS, politica="otra")
