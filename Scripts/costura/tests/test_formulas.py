import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from formulas import (  # noqa: E402
    DiaTrabajador,
    compensada_agregada,
    eficiencia_compensada,
    eficiencia_real,
    incentivo_total,
    min_estandar,
    pct_improductivo,
)


@pytest.mark.parametrize(
    "improd, esperado",
    [(60, 0.9524), (20, 0.8696), (100, 1.0526)],  # ejemplos del brief, sección 2
)
def test_compensada_ejemplos_del_brief(improd, esperado):
    c = eficiencia_compensada(400, 480, improd)
    assert c == pytest.approx(esperado, abs=5e-5)


def test_compensada_sin_base_devuelve_none():
    assert eficiencia_compensada(400, 60, 60) is None
    assert eficiencia_compensada(400, 60, 90) is None


def test_min_estandar():
    assert min_estandar(120, 1.25) == 150
    with pytest.raises(ValueError):
        min_estandar(10, 0)


def test_real_y_pct_improductivo_usan_minutos_sumados_no_promedio_de_porcentajes():
    filas = [DiaTrabajador(400, 480, 60), DiaTrabajador(100, 120, 0)]
    assert eficiencia_real(filas) == pytest.approx(500 / 600)
    assert pct_improductivo(filas) == pytest.approx(60 / 600)
    filas2 = [DiaTrabajador(400, 480, 60), DiaTrabajador(10, 60, 0)]
    assert eficiencia_real(filas2) == pytest.approx(410 / 540)
    assert eficiencia_real(filas2) != pytest.approx((400 / 480 + 10 / 60) / 2)


def test_compensada_agregada_ponderada_por_minutos():
    filas = [DiaTrabajador(400, 480, 60), DiaTrabajador(100, 120, 0)]
    c1 = 400 / 420
    c2 = 100 / 120
    esperado = (c1 * 480 + c2 * 120) / 600
    assert compensada_agregada(filas) == pytest.approx(esperado)


def test_compensada_agregada_ignora_filas_sin_dato():
    filas = [DiaTrabajador(400, 480, 60), DiaTrabajador(50, 60, 60)]  # 2da sin divisor
    assert compensada_agregada(filas) == pytest.approx(400 / 420)


def test_agregados_vacios():
    assert eficiencia_real([]) is None
    assert pct_improductivo([]) is None
    assert compensada_agregada([]) is None


def test_incentivo_suma_directa():
    assert incentivo_total([10.5, 20, 0]) == pytest.approx(30.5)
    assert math.isclose(incentivo_total([]), 0)
