import json
from datetime import datetime, timedelta, timezone

import pytest

import actualizar
from conftest import make_estacion, utc
from fuentes import agp, ina, usgs_nws
from modelo import FuenteError, Lectura


def ahora():
    return datetime.now(timezone.utc).replace(microsecond=0)


def est_barr():
    return make_estacion(id="parana-barranqueras", fuente="agp", pais="ar", zona="chaco-corrientes", ref="20",
                         magnitud="altura", unidad="m", componente=None, muestreo_min=1440)


def est_ina():
    return make_estacion(id="parana-corrientes", fuente="ina", pais="ar", zona="chaco-corrientes", ref="19",
                         magnitud="altura", unidad="m", componente=None, muestreo_min=1440)


def fila_ina(id_, valor, t):
    # fecha_actual está en hora de Argentina (UTC-3)
    local = (t - timedelta(hours=3)).strftime("%d/%m/%Y %H:%M")
    return {"estacion_id": id_, "vigente": True, "valor_actual": valor, "fecha_actual": local,
            "nivel_alerta": 6.5, "nivel_evacuacion": 7}


class ContadorIna(list):
    """Lista de llamadas a ina.bajar; `.filas` es lo que devuelve."""
    filas: list = []


@pytest.fixture
def contador_ina(monkeypatch):
    c = ContadorIna()
    c.filas = []

    def bajar(*a, **k):
        c.append(1)
        return c.filas
    monkeypatch.setattr(ina, "bajar", bajar)
    return c


def agp_ok(monkeypatch, texto_t):
    monkeypatch.setattr(agp, "bajar", lambda *a, **k: "x")
    monkeypatch.setattr(agp, "parse", lambda texto: texto_t)


def agp_falla(monkeypatch):
    def bajar(*a, **k):
        raise FuenteError("AGP: TLS")
    monkeypatch.setattr(agp, "bajar", bajar)


def test_claves_por_pais():
    assert set(actualizar._fuentes_reales("ar")) == {"ina", "agp", "prevision"}
    assert set(actualizar._fuentes_reales("us")) == {"usgs", "prevision", "pronostico_rio"}
    assert set(actualizar._fuentes_reales("es")) == {"aca", "aca_ventana", "chj", "avisos", "prevision"}
    assert set(actualizar._fuentes_reales("de")) == {"pegelonline", "prevision"}
    assert set(actualizar._fuentes_reales("fr")) == {"hubeau", "prevision"}
    assert set(actualizar._fuentes_reales("gb")) == {"ea_uk", "prevision"}
    assert set(actualizar._fuentes_reales("pl")) == {"imgw", "prevision"}
    for pais in ("it", "nl", "pt", "hu", "ru", "asia",
                 "centroamerica", "sudamerica", "oceania", "africa"):
        assert set(actualizar._fuentes_reales(pais)) == {"prevision"}
    assert actualizar._fuentes_reales("xx") == {}


def test_agp_elige_agp_si_es_reciente(monkeypatch, contador_ina):
    t = ahora() - timedelta(minutes=20)
    contador_ina.filas = [fila_ina(20, 6.1, ahora() - timedelta(hours=10))]
    agp_ok(monkeypatch, (t, 6.55))
    f = actualizar._fuentes_reales("ar")
    ls, vivos = f["agp"]([est_barr()])
    assert [(x.estacion_id, x.valor, x.unidad, x.fuente) for x in ls] == [("parana-barranqueras", 6.55, "m", "agp")]
    assert vivos == {}  # los umbrales APA del registro no se pisan


def test_agp_cae_al_ina_si_agp_falla_por_tls(monkeypatch, contador_ina):
    contador_ina.filas = [fila_ina(20, 6.1, ahora() - timedelta(hours=10))]
    agp_falla(monkeypatch)
    ls, vivos = actualizar._fuentes_reales("ar")["agp"]([est_barr()])
    assert [(x.estacion_id, x.valor, x.fuente) for x in ls] == [("parana-barranqueras", 6.1, "ina")]
    assert vivos == {}


def test_agp_viejo_cae_al_ina(monkeypatch, contador_ina):
    contador_ina.filas = [fila_ina(20, 6.1, ahora() - timedelta(hours=2))]
    agp_ok(monkeypatch, (ahora() - timedelta(hours=5), 6.9))
    ls, _ = actualizar._fuentes_reales("ar")["agp"]([est_barr()])
    assert [(x.valor, x.fuente) for x in ls] == [(6.1, "ina")]


def test_agp_sin_agp_ni_ina_lanza_fuente_error(monkeypatch, contador_ina):
    agp_falla(monkeypatch)
    contador_ina.filas = []  # el INA responde pero sin la estación 20
    with pytest.raises(FuenteError):
        actualizar._fuentes_reales("ar")["agp"]([est_barr()])


def test_agp_con_ambas_caidas_lanza_fuente_error(monkeypatch):
    agp_falla(monkeypatch)

    def ina_cae(*a, **k):
        raise FuenteError("INA caído")
    monkeypatch.setattr(ina, "bajar", ina_cae)
    with pytest.raises(FuenteError):
        actualizar._fuentes_reales("ar")["agp"]([est_barr()])


def test_ina_se_baja_una_sola_vez_para_ina_y_agp(monkeypatch, contador_ina):
    contador_ina.filas = [fila_ina(20, 6.1, ahora() - timedelta(hours=1)),
                          fila_ina(19, 7.27, ahora() - timedelta(hours=1))]
    agp_falla(monkeypatch)
    f = actualizar._fuentes_reales("ar")
    ls_ina, vivos = f["ina"]([est_ina()])
    ls_agp, _ = f["agp"]([est_barr()])
    assert len(contador_ina) == 1
    assert [(x.estacion_id, x.valor, x.fuente) for x in ls_ina] == [("parana-corrientes", 7.27, "ina")]
    assert vivos["parana-corrientes"].tipo == "oficial" and vivos["parana-corrientes"].medio == 6.5
    assert ls_agp[0].fuente == "ina"


def test_cache_de_ina_no_vive_entre_ejecuciones(monkeypatch, contador_ina):
    contador_ina.filas = [fila_ina(19, 7.0, ahora() - timedelta(hours=1))]
    actualizar._fuentes_reales("ar")["ina"]([est_ina()])
    actualizar._fuentes_reales("ar")["ina"]([est_ina()])
    assert len(contador_ina) == 2


def test_ina_caido_lanza_fuente_error_en_ambas(monkeypatch):
    llamadas = []

    def ina_cae(*a, **k):
        llamadas.append(1)
        raise FuenteError("INA caído")
    monkeypatch.setattr(ina, "bajar", ina_cae)
    agp_falla(monkeypatch)
    f = actualizar._fuentes_reales("ar")
    with pytest.raises(FuenteError):
        f["ina"]([est_ina()])
    with pytest.raises(FuenteError):
        f["agp"]([est_barr()])
    assert len(llamadas) == 1  # el fallo también se comparte


def test_usgs_delega_en_bajar_todo(monkeypatch):
    visto = []

    def bajar_todo(ests):
        visto.append(ests)
        return ["L"], {"x": "U"}
    monkeypatch.setattr(usgs_nws, "bajar_todo", bajar_todo)
    assert actualizar._fuentes_reales("us")["usgs"](["e"]) == (["L"], {"x": "U"})
    assert visto == [["e"]]


def est_us(id_="mississippi-st-louis", lid="EADM7"):
    return make_estacion(id=id_, fuente="usgs", pais="us", zona="mississippi", magnitud="altura", unidad="ft",
                         ref="07010000", lid=lid, componente=None, muestreo_min=60)


def test_pronostico_rio_arma_documentos_y_omite_vacios_y_fallos(monkeypatch):
    t0, t1 = utc(2026, 10, 21, 0, 0), utc(2026, 10, 21, 6, 0)

    def bajar_pronostico(lid):
        if lid == "VACIO":
            return []
        if lid == "FALLA":
            raise FuenteError("NWS caído")
        return [(t0, 8.5), (t1, 9.0)]
    monkeypatch.setattr(usgs_nws, "bajar_pronostico", bajar_pronostico)
    docs = actualizar._fuentes_reales("us")["pronostico_rio"](
        [est_us("a", "OK1"), est_us("b", "VACIO"), est_us("c", "FALLA"), est_us("d", "OK2")])
    assert set(docs) == {"a", "d"}
    d = docs["a"]
    assert d["fuente"] == "NWS" and d["manual"] is False
    assert d["puntos"] == [["2026-10-21T00:00:00Z", 8.5], ["2026-10-21T06:00:00Z", 9.0]]
    assert d["generado_utc"].endswith("Z")


def test_ejecutar_escribe_pronostico_por_estacion(tmp_path):
    a = ahora()
    e = est_us()
    doc = {"fuente": "NWS", "manual": False, "generado_utc": "2026-10-20T12:00:00Z", "puntos": [["2026-10-21T00:00:00Z", 8.5]]}
    f = {"usgs": lambda ests: ([Lectura(e.id, 8.0, "ft", a - timedelta(minutes=10), "usgs")], {}),
         "pronostico_rio": lambda ests: {e.id: doc, "otra": {"puntos": []}}}
    actualizar.ejecutar(a, [e], f, str(tmp_path))
    assert json.loads((tmp_path / "rios" / e.id / "pronostico.json").read_text()) == doc
    assert "pronostico_rio" not in json.loads((tmp_path / "latest.json").read_text())["fuentes_ok"]


def test_ejecutar_omite_pronostico_vacio(tmp_path):
    a = ahora()
    e = est_us()
    f = {"usgs": lambda ests: ([Lectura(e.id, 8.0, "ft", a - timedelta(minutes=10), "usgs")], {}),
         "pronostico_rio": lambda ests: {e.id: {"fuente": "NWS", "manual": False, "generado_utc": "x", "puntos": []}}}
    actualizar.ejecutar(a, [e], f, str(tmp_path))
    assert not (tmp_path / "rios" / e.id / "pronostico.json").exists()


def test_fallo_del_pronostico_no_toca_niveles_ni_fuentes_ok(tmp_path):
    a = ahora()
    e = est_us()
    base = {"usgs": lambda ests: ([Lectura(e.id, 8.0, "ft", a - timedelta(minutes=10), "usgs")], {})}
    actualizar.ejecutar(a, [e], base, str(tmp_path / "sin"))

    def roto(ests):
        raise RuntimeError("boom")
    cambios = actualizar.ejecutar(a, [e], {**base, "pronostico_rio": roto}, str(tmp_path / "con"))
    sin = json.loads((tmp_path / "sin" / "latest.json").read_text())
    con = json.loads((tmp_path / "con" / "latest.json").read_text())
    assert con["estaciones"] == sin["estaciones"] and con["fuentes_ok"] == sin["fuentes_ok"]
    assert cambios == []
    assert not (tmp_path / "con" / "rios").exists()
