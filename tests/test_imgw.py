"""Tests del adaptador IMGW (Polonia).

Fixture REAL del 2026-10-23 (sin tocar): imgw_warszawa.json, estación 152210170
(Warszawa-Bulwary, Wisła), tal como la devuelve /api/data/hydro/id/152210170.
"""
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import make_estacion
from fuentes import imgw
from modelo import FuenteError

FIX = Path(__file__).parent / "fixtures"
WARSZAWA = (FIX / "imgw_warszawa.json").read_text(encoding="utf-8")


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.cuerpo.encode("utf-8")


def est(id_="vistula-varsovia", ref="152210170"):
    return make_estacion(id=id_, fuente="imgw", ref=ref, pais="pl", zona="vistula",
                         magnitud="altura", unidad="m", componente=None, muestreo_min=10)


def test_url_estacion():
    assert imgw.url_estacion("152210170") == "https://danepubliczne.imgw.pl/api/data/hydro/id/152210170"


def test_parse_lee_metros_y_hora_utc():
    assert imgw.parse(WARSZAWA, "152210170") == (1.08, datetime(2026, 10, 23, 19, 50, tzinfo=timezone.utc))


def test_parse_estacion_no_encontrada_devuelve_none():
    assert imgw.parse(WARSZAWA, "999999999") is None


def test_parse_sin_valor_numerico_devuelve_none():
    d = json.loads(WARSZAWA)
    d[0]["stan_wody"] = None
    assert imgw.parse(json.dumps(d), "152210170") is None


def test_parse_json_invalido_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        imgw.parse("no es json", "152210170")


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
    abrir = abrir_fake({"id/152210170": WARSZAWA})
    lecturas, umb = imgw.bajar_todo([est()], abrir=abrir, dormir=lambda s: None)
    assert umb == {}
    assert len(lecturas) == 1
    l = lecturas[0]
    assert (l.estacion_id, l.valor, l.unidad, l.fuente) == ("vistula-varsovia", 1.08, "m", "imgw")
    assert l.t_utc == datetime(2026, 10, 23, 19, 50, tzinfo=timezone.utc)


def test_bajar_todo_ignora_estaciones_de_otra_fuente():
    abrir = abrir_fake({"id/152210170": WARSZAWA})
    ests = [est(), make_estacion(id="otra", fuente="aca")]
    lecturas, _ = imgw.bajar_todo(ests, abrir=abrir, dormir=lambda s: None)
    assert [l.estacion_id for l in lecturas] == ["vistula-varsovia"]


def test_bajar_todo_sin_estaciones_imgw_no_llama_a_la_red():
    def abrir(req, timeout=None):
        raise AssertionError("no debería llamar a la red")
    lecturas, umb = imgw.bajar_todo([make_estacion(id="otra", fuente="aca")], abrir=abrir)
    assert lecturas == [] and umb == {}


def test_bajar_todo_propaga_fuenteerror_si_todas_las_estaciones_fallan():
    abrir = abrir_fake({"id/152210170": urllib.error.URLError("caído")})
    with pytest.raises(FuenteError):
        imgw.bajar_todo([est()], abrir=abrir, dormir=lambda s: None)


def test_bajar_todo_una_estacion_caida_no_tumba_las_demas():
    abrir = abrir_fake({"id/152210170": WARSZAWA, "id/000000000": urllib.error.URLError("caído")})
    ests = [est(), est("otra-pl", "000000000")]
    lecturas, _ = imgw.bajar_todo(ests, abrir=abrir, dormir=lambda s: None)
    assert [l.estacion_id for l in lecturas] == ["vistula-varsovia"]
