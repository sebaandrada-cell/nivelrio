"""Cliente del API pública Real Time flood-monitoring de la Environment Agency (Reino Unido).

https://environment.data.gov.uk/flood-monitoring/id/stations/<id>/readings.json?_sorted&_limit=1
devuelve la última lectura de nivel de la estación, en metros ("mASD": sobre el datum de la
estación, no sobre el nivel del mar) y con hora UTC en "dateTime". No hace falta clave ni registro.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

from fuentes import red
from modelo import FuenteError, Lectura

URL_BASE = "https://environment.data.gov.uk/flood-monitoring/id/stations"


def url_lectura(station_id: str) -> str:
    return f"{URL_BASE}/{station_id}/readings.json?_sorted&_limit=1"


def _num(x) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def parse(texto: str) -> tuple[float, datetime] | None:
    """(nivel en m, t_utc) de la lectura más reciente, o None si la lista viene vacía."""
    try:
        d = json.loads(texto)
    except ValueError as e:
        raise FuenteError(f"Environment Agency: JSON ilegible: {e}") from e
    items = d.get("items") if isinstance(d, dict) else None
    if not items:
        return None
    fila = items[0]
    v = _num(fila.get("value"))
    ts = fila.get("dateTime")
    if v is None or not ts:
        return None
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return v, t.astimezone(timezone.utc)


def bajar(station_id: str, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep) -> str:
    return red.get_texto(url_lectura(station_id), fuente="Environment Agency", abrir=abrir,
                         intentos=intentos, dormir=dormir, validar=json.loads, accept="application/json")


def bajar_todo(estaciones, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep):
    """(lecturas, {}) para las estaciones con fuente == "ea_uk". Una petición por estación."""
    ests = [e for e in estaciones if e.fuente == "ea_uk" and e.ref]
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
            lecturas.append(Lectura(e.id, v, "m", t, "ea_uk"))
    if not lecturas and ests and fallo is not None:
        raise fallo
    return lecturas, {}
