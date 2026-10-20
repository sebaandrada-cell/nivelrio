"""Tests del adaptador USGS + NWS.

Fixtures REALES del 2026-10-20 (recortados, valores sin tocar):
- usgs_iv_07010000.json: respuesta completa de USGS NWIS IV para St. Louis (00065).
- nwps_EADM7.json: respuesta NWPS de EADM7 conservando lid, usgsId, name, state y
  flood.{stageUnits,flowUnits,categories}; se borró el resto (crests, lro, impacts...).
- nwps_EADM7_forecast.json: respuesta de .../stageflow/forecast con los primeros 6 puntos.
Los casos de centinela y sin categorías se derivan de esos fixtures dentro de cada test.
"""
import copy
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import make_estacion
from fuentes import usgs_nws
from modelo import FuenteError, Umbrales

FIX = Path(__file__).parent / "fixtures"
USGS = (FIX / "usgs_iv_07010000.json").read_text(encoding="utf-8")
NWPS = (FIX / "nwps_EADM7.json").read_text(encoding="utf-8")
PRON = (FIX / "nwps_EADM7_forecast.json").read_text(encoding="utf-8")
EN_ESTUDIO = Umbrales(None, None, None, "en_estudio")


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.cuerpo.encode("utf-8")


def est(id_="stl", ref="07010000", lid="EADM7"):
    return make_estacion(id=id_, fuente="usgs", ref=ref, lid=lid, pais="us", magnitud="altura", unidad="ft")


def test_parse_usgs_lee_pies_y_hora_utc():
    r = usgs_nws.parse_usgs(USGS)
    assert r == {"07010000": (7.99, datetime(2026, 10, 20, 19, 30, tzinfo=timezone.utc))}


def test_parse_usgs_descarta_valores_centinela():
    d = json.loads(USGS)
    v = d["value"]["timeSeries"][0]["values"][0]["value"][0]
    v["value"] = "-999999.00"
    assert usgs_nws.parse_usgs(json.dumps(d)) == {}
    v["value"] = "Ice"
    assert usgs_nws.parse_usgs(json.dumps(d)) == {}


def test_parse_nwps_st_louis():
    assert usgs_nws.parse_nwps(NWPS) == Umbrales(28, 30, 35, "oficial")


def test_nwps_sin_categorias_es_en_estudio():
    assert usgs_nws.parse_nwps("{}") == EN_ESTUDIO
    d = json.loads(NWPS)
    d["flood"]["categories"]["action"]["stage"] = -9999
    assert usgs_nws.parse_nwps(json.dumps(d)) == EN_ESTUDIO
    d = json.loads(NWPS)
    d["flood"]["categories"]["minor"]["stage"] = 27  # no creciente
    assert usgs_nws.parse_nwps(json.dumps(d)) == EN_ESTUDIO
    d = json.loads(NWPS)
    del d["flood"]["categories"]["moderate"]
    assert usgs_nws.parse_nwps(json.dumps(d)) == EN_ESTUDIO


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


def test_url_usgs_y_nwps():
    assert usgs_nws.url_usgs(["1", "2"]) == (
        "https://waterservices.usgs.gov/nwis/iv/?format=json&sites=1,2&parameterCd=00065&siteStatus=all")
    assert usgs_nws.url_nwps("EADM7") == "https://api.water.noaa.gov/nwps/v1/gauges/EADM7"
    assert usgs_nws.url_pronostico("EADM7") == "https://api.water.noaa.gov/nwps/v1/gauges/EADM7/stageflow/forecast"


def test_una_nwps_caida_no_tumba_las_demas():
    ests = [est("a", "07010000", "EADM7"), est("b", "07010000", "MALO1")]
    abrir = abrir_fake({"usgs.gov": USGS, "gauges/EADM7": NWPS,
                        "gauges/MALO1": urllib.error.URLError("caído")})
    lecturas, umb = usgs_nws.bajar_todo(ests, abrir=abrir, dormir=lambda s: None)
    assert umb["a"] == Umbrales(28, 30, 35, "oficial")
    assert umb["b"] == EN_ESTUDIO
    assert [l.estacion_id for l in lecturas] == ["a", "b"]


def test_usgs_caido_lanza_fuenteerror():
    abrir = abrir_fake({"usgs.gov": urllib.error.URLError("caído"), "gauges": NWPS})
    with pytest.raises(FuenteError):
        usgs_nws.bajar_todo([est()], abrir=abrir, dormir=lambda s: None)


def test_lecturas_en_pies():
    ests = [est(), make_estacion(id="otra", fuente="aca")]
    abrir = abrir_fake({"usgs.gov": USGS, "gauges/EADM7": NWPS})
    lecturas, umb = usgs_nws.bajar_todo(ests, abrir=abrir, dormir=lambda s: None)
    assert len(lecturas) == 1 and set(umb) == {"stl"}
    l = lecturas[0]
    assert (l.estacion_id, l.valor, l.unidad, l.fuente) == ("stl", 7.99, "ft", "usgs")
    assert l.t_utc == datetime(2026, 10, 20, 19, 30, tzinfo=timezone.utc)


def test_parse_pronostico_lee_puntos_en_pies():
    pts = usgs_nws.parse_pronostico(PRON)
    assert len(pts) == 6
    assert pts[0] == (datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc), 8.1)
    assert pts[1] == (datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc), 8.0)


def test_pronostico_vacio_devuelve_lista_vacia():
    assert usgs_nws.parse_pronostico("{}") == []
    assert usgs_nws.parse_pronostico('{"primaryUnits":"ft","data":[]}') == []
    d = json.loads(PRON)
    d["primaryUnits"] = "kcfs"  # no son pies: no se publica
    assert usgs_nws.parse_pronostico(json.dumps(d)) == []
