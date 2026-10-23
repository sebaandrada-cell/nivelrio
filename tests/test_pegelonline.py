"""Tests del adaptador PEGELONLINE (Alemania).

Fixture REAL del 2026-10-23 (recortada a 4 puntos, valores sin tocar): pegelonline_koeln_w.json,
estación a6ee8177-107b-47dd-bcfd-30960ccc6e9c (Köln, Rhein), serie "W" de measurements.json.
"""
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import make_estacion
from fuentes import pegelonline
from modelo import FuenteError

FIX = Path(__file__).parent / "fixtures"
KOELN = (FIX / "pegelonline_koeln_w.json").read_text(encoding="utf-8")


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.cuerpo.encode("utf-8")


def est(id_="rhein-koeln", ref="a6ee8177-107b-47dd-bcfd-30960ccc6e9c"):
    return make_estacion(id=id_, fuente="pegelonline", ref=ref, pais="de", zona="rhine",
                         magnitud="altura", unidad="m", componente=None, muestreo_min=15)


def test_url_medidas():
    assert pegelonline.url_medidas("abc") == (
        "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/abc/W/measurements.json?start=P1D")


def test_parse_toma_el_punto_mas_reciente_en_metros_utc():
    assert pegelonline.parse(KOELN) == (0.67, datetime(2026, 10, 23, 20, 15, tzinfo=timezone.utc))


def test_parse_lista_vacia_devuelve_none():
    assert pegelonline.parse("[]") is None


def test_parse_sin_zona_horaria_devuelve_none():
    d = json.loads(KOELN)
    d[-1]["timestamp"] = "2026-10-23T22:15:00"
    assert pegelonline.parse(json.dumps(d)) is None


def test_parse_json_invalido_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        pegelonline.parse("no es json")


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
    abrir = abrir_fake({"stations/a6ee8177": KOELN})
    lecturas, umb = pegelonline.bajar_todo([est()], abrir=abrir, dormir=lambda s: None)
    assert umb == {}
    assert len(lecturas) == 1
    l = lecturas[0]
    assert (l.estacion_id, l.valor, l.unidad, l.fuente) == ("rhein-koeln", 0.67, "m", "pegelonline")
    assert l.t_utc == datetime(2026, 10, 23, 20, 15, tzinfo=timezone.utc)


def test_bajar_todo_ignora_estaciones_de_otra_fuente():
    abrir = abrir_fake({"stations/a6ee8177": KOELN})
    ests = [est(), make_estacion(id="otra", fuente="aca")]
    lecturas, _ = pegelonline.bajar_todo(ests, abrir=abrir, dormir=lambda s: None)
    assert [l.estacion_id for l in lecturas] == ["rhein-koeln"]


def test_bajar_todo_propaga_fuenteerror_si_todas_las_estaciones_fallan():
    abrir = abrir_fake({"stations/a6ee8177": urllib.error.URLError("caído")})
    with pytest.raises(FuenteError):
        pegelonline.bajar_todo([est()], abrir=abrir, dormir=lambda s: None)
