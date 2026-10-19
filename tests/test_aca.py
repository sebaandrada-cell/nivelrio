import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from conftest import make_estacion, utc
from fuentes import aca
from modelo import FuenteError

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def datos():
    return json.loads((FIX / "sentilo_data.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def catalogo():
    return json.loads((FIX / "sentilo_catalogo.json").read_text(encoding="utf-8"))


def test_parse_ultimos_lee_valor_y_utc(datos):
    ult = aca.parse_ultimos(datos)
    valor, t = ult["CALC001261"]
    assert valor == pytest.approx(41.174)
    assert t == datetime(2026, 10, 19, 22, 15, tzinfo=timezone.utc)


def test_observacion_vacia_se_ignora(datos):
    assert "TEST-VACIO-01" not in aca.parse_ultimos(datos)


def test_valor_nan_se_ignora(datos):
    assert "TEST-NAN-01" not in aca.parse_ultimos(datos)


def test_resolver_sensores_por_tipo(catalogo):
    assert aca.resolver_sensores(catalogo, "082172-002") == ("CALC001261", "082172-002-ANA010")


def test_resolver_componente_desconocido(catalogo):
    assert aca.resolver_sensores(catalogo, "999999-999") == (None, None)


def test_lecturas_usa_caudal_en_m3s(datos, catalogo):
    est = make_estacion(id="llobregat", componente="082172-002")
    lecs = aca.lecturas_para([est], aca.parse_ultimos(datos), catalogo)
    assert len(lecs) == 1
    assert (lecs[0].estacion_id, lecs[0].unidad, lecs[0].fuente) == ("llobregat", "m3s", "aca")
    assert lecs[0].valor == pytest.approx(41.174)


def test_sin_caudal_usa_nivel_en_cm(datos, catalogo):
    ult = aca.parse_ultimos(datos)
    ult.pop("CALC001261")
    est = make_estacion(id="llobregat", componente="082172-002")
    lecs = aca.lecturas_para([est], ult, catalogo)
    assert (lecs[0].unidad, lecs[0].valor) == ("cm", pytest.approx(65.178))


def test_estacion_sin_lectura_no_genera_lectura(datos, catalogo):
    # punto ciego 1: sensor con observación vacía o NAN no se interpreta como 0
    ests = [make_estacion(id="vacia", componente="TEST-VACIO"), make_estacion(id="nan", componente="TEST-NAN")]
    assert aca.lecturas_para(ests, aca.parse_ultimos(datos), catalogo) == []


def test_lecturas_ignora_estaciones_chj(datos, catalogo):
    est = make_estacion(id="poyo", fuente="chj", componente=None, id_cha="0O04")
    assert aca.lecturas_para([est], aca.parse_ultimos(datos), catalogo) == []


class _Resp:
    def __init__(self, cuerpo):
        self._c = cuerpo

    def read(self):
        return self._c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_bajar_devuelve_json_y_envia_user_agent():
    vistos = {}

    def abrir(req, timeout=None):
        vistos["ua"] = req.get_header("User-agent")
        vistos["timeout"] = timeout
        return _Resp(b'{"sensors": []}')

    assert aca.bajar("https://x.test/a", abrir=abrir) == {"sensors": []}
    assert "rius" in vistos["ua"].lower()
    assert vistos["timeout"] == 30


def test_bajar_reintenta_y_falla_con_fuenteerror():
    llamadas = []

    def abrir(req, timeout=None):
        llamadas.append(1)
        raise urllib.error.URLError("caído")

    with pytest.raises(FuenteError):
        aca.bajar("https://x.test/a", abrir=abrir, intentos=3, dormir=lambda s: None)
    assert len(llamadas) == 3


def test_bajar_json_roto_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        aca.bajar("https://x.test/a", abrir=lambda req, timeout=None: _Resp(b"<html>"), intentos=1, dormir=lambda s: None)


def test_url_ventana_formatea_fechas_utc():
    u = aca.url_ventana("CALC001261", utc(2026, 10, 19, 18, 0, 0), utc(2026, 10, 19, 19, 30, 0))
    assert u == aca.URL_ULTIMOS + "/CALC001261?limit=30&from=19/10/2026T18:00:00&to=19/10/2026T19:30:00"


def test_parse_ventana_devuelve_pares_mas_nueva_primero():
    doc = {"sensors": [{"sensor": "S", "observations": [
        {"value": "3.5", "timestamp": "19/10/2026T19:25:00"},
        {"value": "NAN", "timestamp": "19/10/2026T19:20:00"},
        {"value": "", "timestamp": "19/10/2026T19:15:00"},
        {"value": "2.0", "timestamp": "19/10/2026T19:10:00"},
    ]}]}
    assert aca.parse_ventana(doc) == [(utc(2026, 10, 19, 19, 25), 3.5), (utc(2026, 10, 19, 19, 10), 2.0)]


def test_parse_ventana_ordena_aunque_llegue_al_reves():
    doc = {"sensors": [{"sensor": "S", "observations": [
        {"value": "1", "timestamp": "19/10/2026T19:00:00"},
        {"value": "2", "timestamp": "19/10/2026T19:05:00"},
    ]}]}
    assert [v for _, v in aca.parse_ventana(doc)] == [2.0, 1.0]
