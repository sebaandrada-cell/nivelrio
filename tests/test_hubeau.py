"""Tests del adaptador Hub'Eau - Hydrométrie (Francia).

Fixture REAL del 2026-10-23 (sin tocar): hubeau_loire_orleans_q.json, estación K435001010
(La Loire à Orléans - Pont Royal), tal como la devuelve observations_tr?grandeur_hydro=Q&size=1.
"""
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import make_estacion
from fuentes import hubeau
from modelo import FuenteError

FIX = Path(__file__).parent / "fixtures"
ORLEANS = (FIX / "hubeau_loire_orleans_q.json").read_text(encoding="utf-8")


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.cuerpo.encode("utf-8")


def est(id_="loire-orleans", ref="K435001010"):
    return make_estacion(id=id_, fuente="hubeau", ref=ref, pais="fr", zona="loire",
                         magnitud="caudal", unidad="m3s", componente=None, muestreo_min=5)


def test_url_ultima():
    url = hubeau.url_ultima("K435001010")
    assert url.startswith("https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr?")
    assert "code_entite=K435001010" in url and "grandeur_hydro=Q" in url and "size=1" in url


def test_parse_convierte_l_s_a_m3s():
    assert hubeau.parse(ORLEANS) == (36.1, datetime(2026, 10, 23, 20, 15, tzinfo=timezone.utc))


def test_parse_sin_datos_devuelve_none():
    assert hubeau.parse('{"count": 0, "data": []}') is None


def test_parse_json_invalido_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        hubeau.parse("no es json")


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
    abrir = abrir_fake({"code_entite=K435001010": ORLEANS})
    lecturas, umb = hubeau.bajar_todo([est()], abrir=abrir, dormir=lambda s: None)
    assert umb == {}
    assert len(lecturas) == 1
    l = lecturas[0]
    assert (l.estacion_id, l.valor, l.unidad, l.fuente) == ("loire-orleans", 36.1, "m3s", "hubeau")
    assert l.t_utc == datetime(2026, 10, 23, 20, 15, tzinfo=timezone.utc)


def test_bajar_todo_ignora_estaciones_de_otra_fuente():
    abrir = abrir_fake({"code_entite=K435001010": ORLEANS})
    ests = [est(), make_estacion(id="otra", fuente="aca")]
    lecturas, _ = hubeau.bajar_todo(ests, abrir=abrir, dormir=lambda s: None)
    assert [l.estacion_id for l in lecturas] == ["loire-orleans"]


def test_bajar_todo_propaga_fuenteerror_si_todas_las_estaciones_fallan():
    abrir = abrir_fake({"code_entite=K435001010": urllib.error.URLError("caído")})
    with pytest.raises(FuenteError):
        hubeau.bajar_todo([est()], abrir=abrir, dormir=lambda s: None)
