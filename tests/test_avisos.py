import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fuentes import avisos
from modelo import FuenteError

FIX = Path(__file__).parent / "fixtures"
CAP = (FIX / "cap_afac69.xml").read_text(encoding="utf-8")
INUNCAT = json.loads((FIX / "inuncat.json").read_text(encoding="utf-8"))
AHORA = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)  # 22:00 CEST


def _por_zona(lista):
    return {(a.zona, a.nivel): a for a in lista}


def test_cap_nivel_sale_del_titulo():
    res = _por_zona(avisos.parse_cap(CAP, AHORA))
    assert res[("Litoral sur de Tarragona", "naranja")].origen == "AEMET"
    assert ("Litoral de Barcelona", "amarillo") in res


def test_cap_solo_lluvias_y_tormentas():
    # Costeros y el fichero tar.gz no son avisos de crecida
    zonas = {a.zona for a in avisos.parse_cap(CAP, AHORA)}
    assert "Ampurdán" in zonas  # por el aviso de Lluvias
    assert all("tar.gz" not in a.descripcion for a in avisos.parse_cap(CAP, AHORA))
    assert not any("costeros" in a.descripcion.lower() for a in avisos.parse_cap(CAP, AHORA))


def test_cap_hora_local_se_convierte_a_utc():
    a = _por_zona(avisos.parse_cap(CAP, AHORA))[("Litoral sur de Tarragona", "naranja")]
    assert a.t_utc == datetime(2026, 10, 19, 17, 0, tzinfo=timezone.utc)  # 19:00 CEST


def test_cap_caducado_se_ignora():
    # a las 10:00 CEST del 20/10 ya terminó todo lo que acababa a las 23:59 y a las 08:59
    tarde = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)
    res = _por_zona(avisos.parse_cap(CAP, tarde))
    assert ("Litoral sur de Tarragona", "naranja") not in res
    assert ("Litoral de Barcelona", "amarillo") not in res
    assert ("Ampurdán", "amarillo") in res  # acaba a las 11:59 CEST


def test_cap_aviso_futuro_se_conserva():
    res = _por_zona(avisos.parse_cap(CAP, AHORA))
    assert ("Prelitoral de Barcelona", "amarillo") in res  # empieza a las 00:00 CEST


def test_cap_sin_periodo_legible_se_conserva():
    res = _por_zona(avisos.parse_cap(CAP, AHORA))
    assert ("Zona de prueba sin periodo", "rojo") in res


def test_cap_xml_roto_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        avisos.parse_cap("<rss><channel>", AHORA)


def test_cap_sin_canal_lanza_fuenteerror():
    with pytest.raises(FuenteError):
        avisos.parse_cap("<html><body>mantenimiento</body></html>", AHORA)


def test_inuncat_vacio_devuelve_none():
    assert avisos.parse_inuncat([]) is None


def test_inuncat_alerta_es_naranja():
    a = avisos.parse_inuncat(INUNCAT)
    assert (a.origen, a.nivel) == ("INUNCAT", "naranja")
    assert a.t_utc == datetime(2026, 10, 15, 17, 6, tzinfo=timezone.utc)  # 19:06 CEST
    assert "40 mm" in a.descripcion


def _fila(**kw):
    base = dict(INUNCAT[0])
    base.update(kw)
    return [base]


def test_inuncat_prealerta_es_amarillo():
    assert avisos.parse_inuncat(_fila(plafase="PREALERTA")).nivel == "amarillo"


def test_inuncat_emergencia_es_rojo():
    assert avisos.parse_inuncat(_fila(plafase="EMERGÈNCIA")).nivel == "rojo"


def test_inuncat_no_activado_devuelve_none():
    assert avisos.parse_inuncat(_fila(plaactivat="NO")) is None


def test_inuncat_ignora_otros_planes():
    assert avisos.parse_inuncat(_fila(plaacronim="PROCICAT")) is None


def test_inuncat_fase_desconocida_lanza_fuenteerror():
    # un aviso oficial nunca se descarta en silencio
    with pytest.raises(FuenteError):
        avisos.parse_inuncat(_fila(plafase="SUPERALERTA"))


def test_urls():
    assert avisos.URL_CAP["cat"].endswith("CAP_AFAC69_RSS.xml")
    assert avisos.URL_CAP["val"].endswith("CAP_AFAC77_RSS.xml")
    assert "wj9c-j6vf" in avisos.URL_INUNCAT
