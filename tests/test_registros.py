import json
import os
from datetime import datetime, timedelta, timezone


import actualizar
from conftest import make_estacion
from estaciones import PAISES, ZONAS, cargar
from modelo import Lectura, Umbrales

PAISES_DIR = os.path.join(os.path.dirname(__file__), "..", "fuente", "paises")


def registro(pais):
    return cargar(os.path.join(PAISES_DIR, pais, "estaciones.json"), pais)


def test_registros_cargan_sin_error():
    for pais in PAISES:
        assert registro(pais), pais


def test_ids_unicos_entre_paises():
    ids = [e.id for p in PAISES for e in registro(p)]
    assert len(ids) == len(set(ids))


def test_ar_us_usan_unidades_de_su_fuente():
    for e in registro("ar"):
        assert e.fuente in ("ina", "agp") and e.unidad == "m" and e.magnitud == "altura" and e.pais == "ar"
    for e in registro("us"):
        assert e.fuente == "usgs" and e.unidad == "ft" and e.magnitud == "altura" and e.pais == "us"
        assert e.ref and e.muestreo_min == 60


def test_zonas_validas():
    for p in PAISES:
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
    assert ref == {"mississippi-st-louis": ("07010000", "EADM7"),
                   "missouri-kansas-city": ("06893000", None),
                   "ohio-cincinnati": ("03255000", None),
                   "colorado-colorado-utah": ("09163500", None),
                   "rio-grande-albuquerque": ("08330000", None)}


def test_cobertura_modelada_por_pais_y_region():
    """DE/FR/GB/PL ya tienen una estación real (ver test_estaciones_reales_de_fr_gb_pl); el resto de
    Europa y las demás regiones siguen solo con el modelo GloFAS porque no se encontró una fuente
    pública confiable para reemplazarlas."""
    europeos_sin_fuente_real = ("it", "nl", "pt", "hu", "ru")
    regiones = ("asia", "centroamerica", "sudamerica", "oceania", "africa")
    assert all(len(registro(p)) == 1 and registro(p)[0].fuente == "glofas" for p in europeos_sin_fuente_real)
    assert all(len(registro(p)) == 3 and all(e.fuente == "glofas" for e in registro(p)) for p in regiones)
    assert [e.id for e in registro("es") if e.fuente == "glofas"] == ["ebro-zaragoza-modelo"]


def test_estaciones_reales_de_fr_gb_pl():
    """Reemplazan al punto GloFAS sin lectura: una estación oficial real por país, con umbral
    "en_estudio" porque ninguna fuente publica los tres niveles bajo/medio/alto necesarios."""
    de = registro("de")
    assert len(de) == 1 and de[0].id == "rhine-cologne" and de[0].fuente == "pegelonline"
    assert de[0].ref == "a6ee8177-107b-47dd-bcfd-30960ccc6e9c" and de[0].magnitud == "altura" and de[0].unidad == "m"

    fr = registro("fr")
    assert len(fr) == 1 and fr[0].id == "loire-orleans" and fr[0].fuente == "hubeau"
    assert fr[0].ref == "K435001010" and fr[0].magnitud == "caudal" and fr[0].unidad == "m3s"

    gb = registro("gb")
    assert len(gb) == 1 and gb[0].id == "severn-shrewsbury" and gb[0].fuente == "ea_uk"
    assert gb[0].ref == "2077" and gb[0].magnitud == "altura" and gb[0].unidad == "m"

    pl = registro("pl")
    assert len(pl) == 1 and pl[0].id == "vistula-warsaw" and pl[0].fuente == "imgw"
    assert pl[0].ref == "152210170" and pl[0].magnitud == "altura" and pl[0].unidad == "m"

    for e in (de[0], fr[0], gb[0], pl[0]):
        assert e.umbrales == Umbrales(None, None, None, "en_estudio")


def test_glofas_no_se_publica_como_lectura_ni_alerta(tmp_path):
    est = registro("it")[0]  # "it" sigue sin fuente real; "de" ya tiene PEGELONLINE (ver arriba)
    ahora = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    bruto = {est.id: {"lluvia": [("2026-10-21", 1.0, 50)], "caudal": (10.0, 20.0)}}
    cambios = actualizar.ejecutar(ahora, [est], {"prevision": lambda _: bruto}, str(tmp_path))
    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    forecast = json.loads((tmp_path / "prevision.json").read_text(encoding="utf-8"))
    fila = latest["estaciones"][0]
    assert cambios == []
    assert fila["fuente"] == "glofas" and fila["valor"] is None and fila["t_utc"] is None
    assert fila["nivel"] == 0 and fila["sd"] is True
    assert forecast["estaciones"][est.id]["caudal"] is None


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
