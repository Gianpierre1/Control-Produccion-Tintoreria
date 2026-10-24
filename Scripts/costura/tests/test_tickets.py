import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tickets import (  # noqa: E402
    codigo_ticket,
    dividir_en_paquetes,
    generar_tickets,
    validar_codigo,
)


def test_codigo_tiene_formato_y_valida():
    c = codigo_ticket(123)
    assert c.startswith("T00000123") and len(c) == 10
    assert validar_codigo(c)


def test_cualquier_error_de_un_digito_se_detecta():
    c = codigo_ticket(4567)
    for i in range(1, len(c)):
        for d in "0123456789":
            if d != c[i]:
                assert not validar_codigo(c[:i] + d + c[i + 1:])


def test_codigos_invalidos():
    assert not validar_codigo("")
    assert not validar_codigo("X000001230")
    assert not validar_codigo("T0000012")
    assert not validar_codigo("T0000012AB")
    assert not validar_codigo(None)  # type: ignore[arg-type]


def test_secuencia_fuera_de_rango():
    with pytest.raises(ValueError):
        codigo_ticket(-1)
    with pytest.raises(ValueError):
        codigo_ticket(10**8)


def test_dividir_en_paquetes():
    assert dividir_en_paquetes(100, 30) == [30, 30, 30, 10]
    assert dividir_en_paquetes(60, 30) == [30, 30]
    assert dividir_en_paquetes(5, 30) == [5]
    with pytest.raises(ValueError):
        dividir_en_paquetes(0, 10)


def test_generar_tickets_por_color_y_talla():
    ts = generar_tickets("OP-1", [("Azul", "M", 50), ("Rojo", "L", 20)], 30, 100)
    assert [(t.color, t.talla, t.cantidad, t.paquete) for t in ts] == [
        ("Azul", "M", 30, 1), ("Azul", "M", 20, 2), ("Rojo", "L", 20, 1)]
    assert sum(t.cantidad for t in ts) == 70
    assert len({t.codigo for t in ts}) == 3
    assert all(validar_codigo(t.codigo) for t in ts)
    assert ts[0].codigo == codigo_ticket(100)
