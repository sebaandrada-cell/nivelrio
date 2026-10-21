"""Tests del adaptador AGP (Paraná en Barranqueras).

Fixture tests/fixtures/agp_barranqueras.dat: SINTÉTICO. Se escribió a partir del formato que
documenta el parser de Pablo Dodda (4 líneas de cabecera; columnas TIMESTAMP, RECORD,
NIvel_Avg, Altura_Avg, Offset): 6 filas válidas, una `NAN` y una fuera de rango (0 < h < 15).
La última válida del fixture es 2026-10-20 14:00 (Argentina) = 17:00 UTC, 7,13 m.
"""
import subprocess
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import make_estacion
from fuentes import agp
from modelo import FuenteError, Lectura

TEXTO = (Path(__file__).parent / "fixtures" / "agp_barranqueras.dat").read_text(encoding="utf-8")
T_AGP = datetime(2026, 10, 20, 17, 0, tzinfo=timezone.utc)


class Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.cuerpo.encode("utf-8")


def test_parse_devuelve_la_ultima_valida():
    assert agp.parse(TEXTO) == (T_AGP, 7.13)


def test_parse_ignora_nan_y_fuera_de_rango():
    # las dos últimas filas son NAN y 99.9: la última válida sigue siendo la de las 14:00
    cabecera = "\n".join(TEXTO.splitlines()[:4])
    solo_malas = cabecera + '\n"2026-10-20 15:00:00",1,"NAN","NAN",0\n"2026-10-20 16:00:00",2,0,0,0\n"2026-10-20 17:00:00",3,9,15,0\n'
    assert agp.parse(solo_malas) is None
    assert agp.parse(TEXTO)[1] == 7.13


def test_parse_sin_filas_devuelve_none():
    assert agp.parse("") is None
    assert agp.parse("\n".join(TEXTO.splitlines()[:4])) is None


def test_bajar_devuelve_el_texto():
    assert agp.bajar(abrir=lambda req, timeout: Resp(TEXTO), dormir=lambda s: None) == TEXTO


def test_error_tls_usa_curl_con_verificacion_predeterminada():
    kwargs = []

    def abrir(req, **kw):
        kwargs.append(kw)
        raise urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate")

    llamadas = []

    def ejecutar(args, **kw):
        llamadas.append((args, kw))
        return SimpleNamespace(stdout=TEXTO)

    assert agp.bajar(abrir=abrir, intentos=1, dormir=lambda s: None, ejecutar=ejecutar) == TEXTO
    assert kwargs and all("context" not in kw for kw in kwargs)
    args, opciones = llamadas[0]
    assert args[:5] == ["curl", "--fail", "--silent", "--show-error", "--location"]
    assert args[-1] == agp.URL
    assert "--insecure" not in args and opciones["check"] is True


def test_error_de_red_no_tls_no_activa_curl():
    def abrir(req, **kw):
        raise urllib.error.URLError("connection refused")

    def ejecutar(*args, **kwargs):
        pytest.fail("curl solo debe usarse para errores de verificación TLS")

    with pytest.raises(FuenteError, match="AGP"):
        agp.bajar(abrir=abrir, intentos=1, dormir=lambda s: None, ejecutar=ejecutar)


def test_error_de_curl_tls_se_informa():
    def abrir(req, **kw):
        raise urllib.error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate")

    def ejecutar(*args, **kwargs):
        raise subprocess.CalledProcessError(60, args[0], stderr="certificate verify failed")

    with pytest.raises(FuenteError, match="TLS verificado"):
        agp.bajar(abrir=abrir, intentos=1, dormir=lambda s: None, ejecutar=ejecutar)


def test_lecturas_para_solo_estaciones_agp():
    est = make_estacion(id="parana-barranqueras", fuente="agp", pais="ar", magnitud="altura", unidad="m")
    otra = make_estacion(id="otra", fuente="ina", ref="20")
    res = agp.lecturas_para([est, otra], (T_AGP, 7.13))
    assert res == [Lectura("parana-barranqueras", 7.13, "m", T_AGP, "agp")]
    assert agp.lecturas_para([est], None) == []


AHORA = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)


def lec(fuente, t):
    return Lectura("parana-barranqueras", 7.0, "m", t, fuente)


def test_respaldo_ina_si_agp_pasa_de_3h():
    vieja = lec("agp", AHORA - timedelta(hours=3, minutes=1))
    ina_ = lec("ina", AHORA - timedelta(hours=5))
    assert agp.elegir(vieja, ina_, AHORA) is ina_


def test_elegir_prefiere_agp_vigente():
    a = lec("agp", AHORA - timedelta(hours=3))  # justo en el límite: sigue valiendo
    i = lec("ina", AHORA - timedelta(minutes=10))
    assert agp.elegir(a, i, AHORA) is a


def test_elegir_con_faltantes():
    i = lec("ina", AHORA - timedelta(hours=1))
    a = lec("agp", AHORA - timedelta(hours=1))
    assert agp.elegir(None, i, AHORA) is i
    assert agp.elegir(a, None, AHORA) is a
    assert agp.elegir(lec("agp", AHORA - timedelta(hours=9)), None, AHORA) is None
    assert agp.elegir(None, None, AHORA) is None


def test_elegir_ignora_lectura_del_futuro():
    futura = lec("agp", AHORA + timedelta(minutes=1))
    i = lec("ina", AHORA - timedelta(hours=1))
    assert agp.elegir(futura, i, AHORA) is i
