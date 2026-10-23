"""Cliente del API pública PEGELONLINE de la WSV (Wasserstraßen- und Schifffahrtsverwaltung, Alemania).

https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/<uuid>/W/measurements.json?start=P1D
devuelve el nivel de agua (serie "W", en cm) de las últimas 24 h, con hora local alemana y desfase
explícito (se convierte a UTC). No hace falta clave ni registro.

La estación también ofrece una serie de caudal ("Q"), pero PEGELONLINE advierte que no puede
calcularse por debajo de 50 cm de nivel (aguas bajas): por eso se usa el nivel ("W"), que no tiene
ese hueco y además es más sensible para detectar tanto crecidas como sequías de caudal bajo.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

from fuentes import red
from modelo import FuenteError, Lectura

URL_BASE = "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations"


def url_medidas(uuid: str) -> str:
    return f"{URL_BASE}/{uuid}/W/measurements.json?start=P1D"


def _num(x) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def parse(texto: str) -> tuple[float, datetime] | None:
    """(nivel en m, t_utc) de la medición más reciente, o None si la lista viene vacía."""
    try:
        d = json.loads(texto)
    except ValueError as e:
        raise FuenteError(f"PEGELONLINE: JSON ilegible: {e}") from e
    if not isinstance(d, list) or not d:
        return None
    ultima = max(d, key=lambda m: m.get("timestamp", ""))
    v = _num(ultima.get("value"))
    ts = ultima.get("timestamp")
    if v is None or not ts:
        return None
    try:
        t = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if t.tzinfo is None:
        return None
    return v / 100.0, t.astimezone(timezone.utc)  # cm -> m


def bajar(uuid: str, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep) -> str:
    return red.get_texto(url_medidas(uuid), fuente="PEGELONLINE", abrir=abrir, intentos=intentos,
                         dormir=dormir, validar=json.loads, accept="application/json")


def bajar_todo(estaciones, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep):
    """(lecturas, {}) para las estaciones con fuente == "pegelonline". Una petición por estación:
    el API no ofrece un endpoint combinado por lista de estaciones."""
    ests = [e for e in estaciones if e.fuente == "pegelonline" and e.ref]
    lecturas = []
    fallo = None
    for e in ests:
        try:
            texto = bajar(e.ref, abrir=abrir, intentos=intentos, dormir=dormir)
        except FuenteError as exc:
            fallo = exc
            continue
        par = parse(texto)
        if par is not None:
            v, t = par
            lecturas.append(Lectura(e.id, v, "m", t, "pegelonline"))
    if not lecturas and ests and fallo is not None:
        raise fallo
    return lecturas, {}
