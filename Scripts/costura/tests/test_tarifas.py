import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tarifas import SinTarifa, Tarifa, buscar_tarifa  # noqa: E402

HOY = date(2026, 10, 29)


def test_tarifa_general_por_rango_de_cantidad():
    ts = [Tarifa(10, 2.0, cantidad_min=1, cantidad_max=30), Tarifa(10, 1.8, cantidad_min=31)]
    assert buscar_tarifa(ts, 10, "Polo", 30, HOY).min_por_pieza == 2.0
    assert buscar_tarifa(ts, 10, "Polo", 31, HOY).min_por_pieza == 1.8
    assert buscar_tarifa(ts, 10, "Polo", 500, HOY).min_por_pieza == 1.8


def test_tipo_de_prenda_especifico_gana_a_la_tarifa_general():
    ts = [Tarifa(10, 2.0), Tarifa(10, 2.6, tipo_prenda="Casaca")]
    assert buscar_tarifa(ts, 10, "Casaca", 20, HOY).min_por_pieza == 2.6
    assert buscar_tarifa(ts, 10, "Polo", 20, HOY).min_por_pieza == 2.0


def test_cambio_de_tiempo_con_vigencia_no_toca_el_pasado():
    ts = [Tarifa(10, 2.0, vigente_hasta=date(2026, 10, 31)),
          Tarifa(10, 1.9, vigente_desde=date(2026, 11, 1))]
    assert buscar_tarifa(ts, 10, None, 20, date(2026, 10, 31)).min_por_pieza == 2.0
    assert buscar_tarifa(ts, 10, None, 20, date(2026, 11, 1)).min_por_pieza == 1.9


def test_sin_tarifa():
    with pytest.raises(SinTarifa):
        buscar_tarifa([Tarifa(10, 2.0)], 99, None, 20, HOY)
    with pytest.raises(SinTarifa):
        buscar_tarifa([Tarifa(10, 2.0, cantidad_min=50)], 10, None, 20, HOY)
    with pytest.raises(SinTarifa):
        buscar_tarifa([Tarifa(10, 2.0, vigente_desde=date(2027, 1, 1))], 10, None, 20, HOY)


def test_tarifas_ambiguas_se_rechazan():
    ts = [Tarifa(10, 2.0, tipo_prenda="Polo"), Tarifa(10, 2.2, tipo_prenda="Polo")]
    with pytest.raises(ValueError):
        buscar_tarifa(ts, 10, "Polo", 20, HOY)


@pytest.mark.parametrize("kw", [
    dict(min_por_pieza=0), dict(min_por_pieza=-1), dict(cantidad_min=0),
    dict(cantidad_min=10, cantidad_max=5),
    dict(vigente_desde=date(2026, 5, 1), vigente_hasta=date(2026, 4, 1)),
])
def test_tarifas_invalidas(kw):
    base = dict(operacion_id=1, min_por_pieza=1.0)
    base.update(kw)
    with pytest.raises(ValueError):
        Tarifa(**base)
