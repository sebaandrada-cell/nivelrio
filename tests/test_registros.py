import os
from datetime import datetime, timedelta, timezone


import actualizar
from conftest import make_estacion
from estaciones import ZONAS, cargar
from modelo import Lectura, Umbrales

PAISES_DIR = os.path.join(os.path.dirname(__file__), "..", "fuente", "paises")


def registro(pais):
    return cargar(os.path.join(PAISES_DIR, pais, "estaciones.json"), pais)


def test_registros_cargan_sin_error():
    for pais in ("es", "ar", "us"):
        assert registro(pais), pais


def test_ids_unicos_entre_paises():
    ids = [e.id for p in ("es", "ar", "us") for e in registro(p)]
    assert len(ids) == len(set(ids))


def test_ar_us_usan_unidades_de_su_fuente():
    for e in registro("ar"):
        assert e.fuente in ("ina", "agp") and e.unidad == "m" and e.magnitud == "altura" and e.pais == "ar"
    for e in registro("us"):
        assert e.fuente == "usgs" and e.unidad == "ft" and e.magnitud == "altura" and e.pais == "us"
        assert e.ref and e.lid and e.muestreo_min == 60


def test_zonas_validas():
    for p in ("ar", "us"):
        for e in registro(p):
            assert e.zona in ZONAS[p]


def test_zonas_de_ar_segun_el_plan():
    z = {e.id: e.zona for e in registro("ar")}
    assert z == {"parana-barranqueras": "chaco-corrientes", "parana-corrientes": "chaco-corrientes",
                 "parana-santa-fe": "litoral-parana", "parana-parana": "litoral-parana",
                 "parana-rosario": "litoral-parana", "uruguay-concordia": "uruguay"}


def test_barranqueras_tiene_umbrales_apa():
    e = {x.id: x for x in registro("ar")}["parana-barranqueras"]
    assert e.fuente == "agp" and e.ref == "20" and e.muestreo_min == 1440
    assert e.umbrales == Umbrales(5.5, 6.0, 6.5, "oficial")


def test_ina_refs_y_muestreo():
    ref = {e.id: (e.fuente, e.ref, e.muestreo_min) for e in registro("ar")}
    assert ref == {"parana-barranqueras": ("agp", "20", 1440), "parana-corrientes": ("ina", "19", 1440),
                   "parana-santa-fe": ("ina", "30", 1440), "parana-parana": ("ina", "29", 1440),
                   "parana-rosario": ("ina", "34", 1440), "uruguay-concordia": ("ina", "79", 1440)}


def test_us_refs_verificados():
    ref = {e.id: (e.ref, e.lid) for e in registro("us")}
    assert ref == {"mississippi-st-louis": ("07010000", "EADM7")}


def test_ejecutar_recorre_fuentes_del_registro(tmp_path):
    ahora = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    ests = [make_estacion(id="r-ina", fuente="ina", pais="ar", zona="uruguay", magnitud="altura", unidad="m",
                          ref="79", componente=None, muestreo_min=1440),
            make_estacion(id="r-usgs", fuente="usgs", pais="us", zona="mississippi", magnitud="altura",
                          unidad="ft", ref="07010000", lid="EADM7", componente=None, muestreo_min=60)]
    f = {"ina": lambda e: ([Lectura("r-ina", 3.2, "m", ahora - timedelta(hours=1), "ina")], {}),
         "usgs": lambda e: ([Lectura("r-usgs", 8.0, "ft", ahora - timedelta(minutes=30), "usgs")], {})}
    actualizar.ejecutar(ahora, ests, f, str(tmp_path))
    import json
    filas = {x["id"]: x for x in json.loads((tmp_path / "latest.json").read_text())["estaciones"]}
    assert filas["r-ina"]["valor"] == 3.2 and filas["r-usgs"]["valor"] == 8.0
