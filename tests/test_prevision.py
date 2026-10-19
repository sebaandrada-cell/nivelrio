import io
import json
import urllib.error
from pathlib import Path

import pytest

from conftest import make_estacion
from fuentes import prevision
from modelo import FuenteError, Umbrales

FIX = Path(__file__).parent / "fixtures"


def leer(nombre):
    return (FIX / nombre).read_text(encoding="utf-8")


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def abrir_con(respuestas):
    """`respuestas`: función url -> texto, o lanza URLError."""
    visto = []

    def abrir(req, timeout=None):
        url = req.full_url
        visto.append(url)
        return Resp(respuestas(url).encode("utf-8"))

    abrir.visto = visto
    return abrir


def sin_dormir(_):
    return None


def test_urls_llevan_coordenadas_y_parametros():
    u = prevision.url_lluvia(41.485, 2.19)
    assert u.startswith("https://api.open-meteo.com/v1/forecast?")
    assert "latitude=41.485" in u and "longitude=2.19" in u
    assert "precipitation_sum" in u and "precipitation_probability_max" in u
    assert "forecast_days=3" in u and "timezone=Europe%2FMadrid" in u
    c = prevision.url_caudal(41.485, 2.19)
    assert c.startswith("https://flood-api.open-meteo.com/v1/flood?")
    assert "river_discharge_max" in c and "forecast_days=3" in c


def test_parse_lluvia_tres_dias():
    dias = prevision.parse_lluvia(leer("openmeteo_forecast.json"))
    assert dias == [("2026-10-20", 0.4, 77), ("2026-10-21", 0.1, 6), ("2026-10-22", 2.3, 33)]


def test_parse_lluvia_nulos_son_cero():
    texto = json.dumps({"daily": {"time": ["2026-10-20", "2026-10-21"],
                                  "precipitation_sum": [None, 3.0],
                                  "precipitation_probability_max": [None, None]}})
    assert prevision.parse_lluvia(texto) == [("2026-10-20", 0.0, 0), ("2026-10-21", 3.0, 0)]


def test_parse_caudal_devuelve_min_y_max_de_tres_dias():
    # fixture real del Besòs: river_discharge [1.71, 3.57, 1.52], river_discharge_max [3.74, 8.71, 3.36]
    assert prevision.parse_caudal(leer("openmeteo_flood.json")) == (1.52, 8.71)


def test_parse_caudal_todo_nulo_es_none():
    texto = json.dumps({"daily": {"time": ["a", "b", "c"], "river_discharge": [None] * 3,
                                  "river_discharge_max": [None] * 3}})
    assert prevision.parse_caudal(texto) is None


def test_parse_caudal_sin_columna_max_usa_river_discharge():
    texto = json.dumps({"daily": {"time": ["a", "b"], "river_discharge": [2.0, 5.0]}})
    assert prevision.parse_caudal(texto) == (2.0, 5.0)


def test_parse_rechaza_respuesta_de_error():
    with pytest.raises(FuenteError):
        prevision.parse_lluvia(json.dumps({"error": True, "reason": "limite"}))
    with pytest.raises(FuenteError):
        prevision.parse_caudal("no es json")


def test_coherente_descarta_modelo_desproporcionado():
    assert prevision.coherente(20.0, 400.0) is False


def test_coherente_acepta_caudales_pequenos():
    assert prevision.coherente(2.0, 6.0) is True


def test_coherente_sin_observado_es_falso():
    assert prevision.coherente(None, 10.0) is False


def test_coherente_descarta_modelo_ridiculamente_bajo():
    # caso real: Llobregat en Sant Joan Despí, observado 41 m3/s y la malla de GloFAS da 2,5
    assert prevision.coherente(41.2, 2.5) is False


def test_nivel_posible():
    u = Umbrales(55.0, 160.0, 320.0, "estimado")
    assert prevision.nivel_posible(u, 170.0) == 2
    assert prevision.nivel_posible(u, 320.0) == 3
    assert prevision.nivel_posible(u, 30.0) == 0
    assert prevision.nivel_posible(u, 55.0) == 1


def test_en_estudio_no_etiqueta():
    assert prevision.nivel_posible(Umbrales(None, None, None, "en_estudio"), 9999.0) == 0


def respuestas_normales(url):
    return leer("openmeteo_flood.json") if "flood-api" in url else leer("openmeteo_forecast.json")


def test_bajar_una_peticion_por_par_lat_lon():
    e1 = make_estacion(id="a", lat=41.485, lon=2.19)
    e2 = make_estacion(id="b", lat=41.485, lon=2.19)
    e3 = make_estacion(id="c", lat=41.9, lon=2.7)
    abrir = abrir_con(respuestas_normales)
    res = prevision.bajar([e1, e2, e3], abrir=abrir, dormir=sin_dormir)
    assert len(abrir.visto) == 4  # 2 pares x (lluvia + caudal)
    assert res["a"] == res["b"]
    assert res["a"]["lluvia"][2] == ("2026-10-22", 2.3, 33)
    assert res["a"]["caudal"] == (1.52, 8.71)


def test_fallo_de_una_estacion_no_rompe_las_otras():
    buena = make_estacion(id="buena", lat=41.485, lon=2.19)
    mala = make_estacion(id="mala", lat=42.0, lon=3.0)

    def resp(url):
        if "latitude=42.0" in url:
            raise urllib.error.URLError("caido")
        return respuestas_normales(url)

    res = prevision.bajar([buena, mala], abrir=abrir_con(resp), dormir=sin_dormir)
    assert res["mala"] is None
    assert res["buena"]["caudal"] == (1.52, 8.71)


def test_fallo_del_caudal_conserva_la_lluvia():
    e = make_estacion(id="a")

    def resp(url):
        if "flood-api" in url:
            raise urllib.error.URLError("caido")
        return leer("openmeteo_forecast.json")

    res = prevision.bajar([e], abrir=abrir_con(resp), dormir=sin_dormir)
    assert res["a"]["caudal"] is None
    assert len(res["a"]["lluvia"]) == 3


def test_todas_fallan_lanza_fuenteerror():
    def resp(url):
        raise urllib.error.URLError("caido")

    with pytest.raises(FuenteError):
        prevision.bajar([make_estacion(id="a"), make_estacion(id="b", lat=42.0)],
                        abrir=abrir_con(resp), dormir=sin_dormir)
