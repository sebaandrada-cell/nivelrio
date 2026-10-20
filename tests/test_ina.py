"""Tests del adaptador INA.

Fixture tests/fixtures/ina_estaciones.json: recorte REAL de la respuesta del 2026-10-20
(Barranqueras 20, Corrientes 19, Paraná 29, Rosario 34, Santa Fe 30, Concordia 79, y
Federación 76, que en la respuesta real viene con vigente=false), más UNA entrada SINTÉTICA:
`TEST-SIN-VALOR` (copia de Barranqueras con valor_actual null).
"""
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import make_estacion
from fuentes import ina
from modelo import FuenteError, Umbrales

FILAS = json.loads((Path(__file__).parent / "fixtures" / "ina_estaciones.json").read_text(encoding="utf-8"))


def fila(id_):
    return next(f for f in FILAS if str(f["estacion_id"]) == str(id_))


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.cuerpo.encode("utf-8")


def test_umbrales_barranqueras():
    assert ina.umbrales(fila(20)) == Umbrales(5.4, 6.0, 6.5, "oficial")


def test_umbrales_incoherentes_son_en_estudio():
    en_estudio = Umbrales(None, None, None, "en_estudio")
    assert ina.umbrales({"nivel_alerta": 7, "nivel_evacuacion": 6}) == en_estudio
    assert ina.umbrales({"nivel_alerta": 6, "nivel_evacuacion": 6}) == en_estudio
    assert ina.umbrales({"nivel_alerta": None, "nivel_evacuacion": 6}) == en_estudio
    assert ina.umbrales({"nivel_alerta": 6, "nivel_evacuacion": None}) == en_estudio
    assert ina.umbrales({"nivel_alerta": 0, "nivel_evacuacion": 6}) == en_estudio
    assert ina.umbrales({"nivel_alerta": "x", "nivel_evacuacion": 6}) == en_estudio


def test_umbrales_aceptan_numeros_como_texto():
    assert ina.umbrales({"nivel_alerta": "6", "nivel_evacuacion": "6.5"}) == Umbrales(5.4, 6.0, 6.5, "oficial")


def test_fecha_se_convierte_a_utc():
    r = ina.parse(FILAS)["20"]
    assert r["t_utc"] == datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
    assert r["valor"] == 7.13


def test_valor_como_texto():
    f = dict(fila(20), valor_actual="7.13")
    assert ina.parse([f])["20"]["valor"] == 7.13


def test_fila_sin_valor_no_genera_lectura():
    assert "TEST-SIN-VALOR" not in ina.parse(FILAS)


def test_vigente_false_no_genera_lectura():
    assert fila(76)["vigente"] is False
    assert "76" not in ina.parse(FILAS)


def test_fecha_ilegible_se_descarta():
    assert ina.parse([dict(fila(20), fecha_actual="ayer")]) == {}


def test_lecturas_para_usa_ref():
    est = make_estacion(id="barranqueras", fuente="ina", ref="20", magnitud="altura", unidad="m")
    otra = make_estacion(id="otra", fuente="ina", ref="9999", magnitud="altura", unidad="m")
    aca = make_estacion(id="aca1", fuente="aca", ref="20")
    lecs = ina.lecturas_para([est, otra, aca], ina.parse(FILAS))
    assert len(lecs) == 1
    l = lecs[0]
    assert (l.estacion_id, l.valor, l.unidad, l.fuente) == ("barranqueras", 7.13, "m", "ina")
    assert l.t_utc == datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)


def test_bajar_devuelve_filas():
    filas = ina.bajar(abrir=lambda req, timeout: Resp(json.dumps(FILAS)), dormir=lambda s: None)
    assert len(filas) == len(FILAS)


def test_bajar_json_roto_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        ina.bajar(abrir=lambda req, timeout: Resp("<html>mantenimiento"), dormir=lambda s: None)


def test_bajar_json_no_lista_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        ina.bajar(abrir=lambda req, timeout: Resp('{"error": 1}'), dormir=lambda s: None)


def test_bajar_reintenta_y_falla():
    llamadas = []

    def abrir(req, timeout):
        llamadas.append(1)
        raise urllib.error.URLError("caído")

    with pytest.raises(FuenteError):
        ina.bajar(abrir=abrir, dormir=lambda s: None)
    assert len(llamadas) == 3
