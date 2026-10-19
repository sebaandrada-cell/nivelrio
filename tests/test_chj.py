import http.client
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import make_estacion
from fuentes import chj
from modelo import FuenteError, Umbrales

HTML = (Path(__file__).parent / "fixtures" / "chj_aforos.html").read_text(encoding="utf-8")


def test_extrae_array_con_corchetes_en_cadenas():
    arr = chj.extraer_array(HTML, "aforos")
    assert len(arr) == 7
    assert any("[CORCHETES] ]" in a["fldTNombre"] for a in arr)


def test_extrae_array_ignora_texto_posterior():
    arr = chj.extraer_array('<script>let xs = [{"a": 1}, {"a": 2}]; let ys = [1];</script>', "xs")
    assert arr == [{"a": 1}, {"a": 2}]


def test_aforo_con_umbrales_validos_es_oficial():
    a = chj.parse_aforos(HTML)["0O04"]
    assert a["umbrales"] == Umbrales(30.0, 70.0, 150.0, "oficial")
    assert a["valor"] == 0.0


def test_umbrales_cero_son_en_estudio():
    # punto ciego 3: nunca N1 por comparar contra 0
    assert chj.parse_aforos(HTML)["TEST-CERO"]["umbrales"] == Umbrales(None, None, None, "en_estudio")


def test_umbrales_no_crecientes_son_en_estudio():
    assert chj.parse_aforos(HTML)["TEST-NOCRE"]["umbrales"].tipo == "en_estudio"


def test_sin_array_lanza_fuenteerror():
    # punto ciego 4: la CHJ cambia su HTML
    with pytest.raises(FuenteError):
        chj.parse_aforos("<html><body>mantenimiento</body></html>")


def test_array_roto_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        chj.extraer_array("let aforos = [{\"a\": ", "aforos")


def test_fecha_iso_z_a_utc():
    assert chj.parse_aforos(HTML)["0O04"]["t_utc"] == datetime(2026, 10, 19, 22, 20, tzinfo=timezone.utc)


def test_solo_cuentan_los_aforos_de_caudal():
    # el código 0O04 también aparece como "Em" con valor 99: no debe pisar al aforo
    assert chj.parse_aforos(HTML)["0O04"]["valor"] == 0.0


def test_lecturas_para_estaciones_chj():
    est = make_estacion(id="poyo", fuente="chj", componente=None, id_cha="0O04")
    otra = make_estacion(id="aca1", fuente="aca")
    lecs = chj.lecturas_para([est, otra], chj.parse_aforos(HTML))
    assert len(lecs) == 1
    assert (lecs[0].estacion_id, lecs[0].unidad, lecs[0].fuente) == ("poyo", "m3s", "chj")


def test_aforo_sin_valor_no_genera_lectura():
    est = make_estacion(id="sv", fuente="chj", componente=None, id_cha="TEST-SINVALOR")
    assert chj.lecturas_para([est], chj.parse_aforos(HTML)) == []


class _Resp:
    def __init__(self, cuerpo):
        self._c = cuerpo

    def read(self):
        return self._c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_bajar_aforos_reintenta_hasta_tener_el_array():
    intentos = []

    def abrir(req, timeout=None):
        intentos.append(1)
        if len(intentos) == 1:
            raise urllib.error.URLError("corte")
        if len(intentos) == 2:
            raise http.client.IncompleteRead(b"<html>")
        return _Resp(HTML.encode("utf-8"))

    assert "let aforos" in chj.bajar_aforos(abrir=abrir, dormir=lambda s: None)
    assert len(intentos) == 3


def test_bajar_aforos_falla_con_fuenteerror():
    def abrir(req, timeout=None):
        raise urllib.error.URLError("caído")

    with pytest.raises(FuenteError):
        chj.bajar_aforos(abrir=abrir, intentos=2, dormir=lambda s: None)


def test_bajar_aforos_pagina_sin_array_cuenta_como_fallo():
    with pytest.raises(FuenteError):
        chj.bajar_aforos(abrir=lambda req, timeout=None: _Resp(b"<html>mantenimiento</html>"), intentos=2, dormir=lambda s: None)
