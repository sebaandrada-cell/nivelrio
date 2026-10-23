"""Tests del adaptador Environment Agency - real time flood-monitoring (Reino Unido).

Fixture REAL del 2026-10-23 (sin tocar): ea_uk_severn_2077.json, estación 2077
(Welsh Bridge, Shrewsbury, River Severn), tal como la devuelve readings.json?_sorted&_limit=1.
"""
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import make_estacion
from fuentes import ea_uk
from modelo import FuenteError

FIX = Path(__file__).parent / "fixtures"
SHREWSBURY = (FIX / "ea_uk_severn_2077.json").read_text(encoding="utf-8")


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.cuerpo.encode("utf-8")


def est(id_="severn-shrewsbury", ref="2077"):
    return make_estacion(id=id_, fuente="ea_uk", ref=ref, pais="gb", zona="severn",
                         magnitud="altura", unidad="m", componente=None, muestreo_min=15)


def test_url_lectura():
    assert ea_uk.url_lectura("2077") == (
        "https://environment.data.gov.uk/flood-monitoring/id/stations/2077/readings.json?_sorted&_limit=1")


def test_parse_lee_metros_y_hora_utc():
    assert ea_uk.parse(SHREWSBURY) == (0.844, datetime(2026, 10, 23, 19, 45, tzinfo=timezone.utc))


def test_parse_sin_items_devuelve_none():
    assert ea_uk.parse('{"items": []}') is None


def test_parse_json_invalido_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        ea_uk.parse("no es json")


def abrir_fake(rutas):
    def abrir(req, timeout=None):
        url = req.full_url
        for clave, cuerpo in rutas.items():
            if clave in url:
                if isinstance(cuerpo, Exception):
                    raise cuerpo
                return Resp(cuerpo)
        raise AssertionError("URL inesperada " + url)
    return abrir


def test_bajar_todo_lee_la_estacion():
    abrir = abrir_fake({"stations/2077": SHREWSBURY})
    lecturas, umb = ea_uk.bajar_todo([est()], abrir=abrir, dormir=lambda s: None)
    assert umb == {}
    assert len(lecturas) == 1
    l = lecturas[0]
    assert (l.estacion_id, l.valor, l.unidad, l.fuente) == ("severn-shrewsbury", 0.844, "m", "ea_uk")
    assert l.t_utc == datetime(2026, 10, 23, 19, 45, tzinfo=timezone.utc)


def test_bajar_todo_ignora_estaciones_de_otra_fuente():
    abrir = abrir_fake({"stations/2077": SHREWSBURY})
    ests = [est(), make_estacion(id="otra", fuente="aca")]
    lecturas, _ = ea_uk.bajar_todo(ests, abrir=abrir, dormir=lambda s: None)
    assert [l.estacion_id for l in lecturas] == ["severn-shrewsbury"]


def test_bajar_todo_propaga_fuenteerror_si_todas_las_estaciones_fallan():
    abrir = abrir_fake({"stations/2077": urllib.error.URLError("caído")})
    with pytest.raises(FuenteError):
        ea_uk.bajar_todo([est()], abrir=abrir, dormir=lambda s: None)
