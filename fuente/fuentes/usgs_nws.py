"""Clientes de USGS (lecturas) y NWS/NWPS (umbrales y pronóstico) para EE. UU.

USGS NWIS IV: https://waterservices.usgs.gov/nwis/iv/ (parámetro 00065, altura en pies).
Cada valor trae su hora local con desfase UTC ("2026-10-20T14:30:00.000-05:00"), que se
convierte a UTC. Los valores centinela (-999999) o no numéricos se descartan.

NWS NWPS: https://api.water.noaa.gov/nwps/v1/gauges/<lid>. Las categorías de inundación
están en `flood.categories.{action,minor,moderate,major}.stage` (pies, `flood.stageUnits`);
-9999 significa "sin dato". Mapeo: action -> bajo, minor -> medio, moderate -> alto
(major no se usa). Si falta alguna, es -9999 o no son crecientes, quedan "en_estudio".

Pronóstico: .../gauges/<lid>/stageflow/forecast -> {"primaryUnits": "ft", "data":
[{"validTime": "...Z", "primary": pies, ...}]}. Es informativo, no entra en `evaluar`.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

from fuentes import red
from modelo import FuenteError, Lectura, Umbrales

_EN_ESTUDIO = Umbrales(None, None, None, "en_estudio")
_CENTINELAS = (-999999.0, -9999.0)


def url_usgs(sitios: list[str]) -> str:
    return ("https://waterservices.usgs.gov/nwis/iv/?format=json&sites=" + ",".join(sitios)
            + "&parameterCd=00065&siteStatus=all")


def url_nwps(lid: str) -> str:
    return f"https://api.water.noaa.gov/nwps/v1/gauges/{lid}"


def url_pronostico(lid: str) -> str:
    return f"https://api.water.noaa.gov/nwps/v1/gauges/{lid}/stageflow/forecast"


def _num(x) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _utc(s: str) -> datetime:
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("fecha sin zona horaria")
    return t.astimezone(timezone.utc)


def _json(texto: str, fuente: str):
    try:
        return json.loads(texto)
    except ValueError as e:
        raise FuenteError(f"{fuente}: JSON ilegible: {e}") from e


def parse_usgs(texto: str) -> dict[str, tuple[float, datetime]]:
    """site -> (pies, t_utc), con la última lectura válida de cada sitio."""
    d = _json(texto, "USGS")
    try:
        series = d["value"]["timeSeries"]
    except (KeyError, TypeError) as e:
        raise FuenteError("USGS: respuesta sin value.timeSeries") from e
    res = {}
    for s in series if isinstance(series, list) else []:
        try:
            sitio = str(s["sourceInfo"]["siteCode"][0]["value"])
            puntos = s["values"][0]["value"]
        except (KeyError, IndexError, TypeError):
            continue
        for p in reversed(puntos):  # el último punto válido
            try:
                v = _num(p["value"])
                if v is None or v in _CENTINELAS:
                    continue
                res[sitio] = (v, _utc(p["dateTime"]))
                break
            except (KeyError, ValueError, TypeError):
                continue
    return res


def parse_nwps(texto: str) -> Umbrales:
    try:
        d = json.loads(texto)
        flood = d["flood"]
        if flood.get("stageUnits") != "ft":
            return _EN_ESTUDIO
        cat = flood["categories"]
        v = [_num(cat[k]["stage"]) for k in ("action", "minor", "moderate")]
    except (ValueError, KeyError, TypeError, AttributeError):
        return _EN_ESTUDIO
    if any(x is None or x in _CENTINELAS for x in v) or not (v[0] < v[1] < v[2]):
        return _EN_ESTUDIO
    return Umbrales(v[0], v[1], v[2], "oficial")


def parse_pronostico(texto: str) -> list[tuple[datetime, float]]:
    try:
        d = json.loads(texto)
        if d.get("primaryUnits") != "ft":
            return []
        filas = d["data"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return []
    res = []
    for f in filas if isinstance(filas, list) else []:
        try:
            v = _num(f["primary"])
            if v is None or v in _CENTINELAS:
                continue
            res.append((_utc(f["validTime"]), v))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return res


def bajar_pronostico(lid: str, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep):
    texto = red.get_texto(url_pronostico(lid), fuente="NWS", abrir=abrir, intentos=intentos,
                          dormir=dormir, accept="application/json")
    return parse_pronostico(texto)


def bajar_todo(estaciones, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep):
    """(lecturas, {est.id: Umbrales}) para las estaciones con fuente == "usgs"."""
    ests = [e for e in estaciones if e.fuente == "usgs" and e.ref]
    if not ests:
        return [], {}
    sitios = sorted({e.ref for e in ests})
    texto = red.get_texto(url_usgs(sitios), fuente="USGS", abrir=abrir, intentos=intentos,
                          dormir=dormir, accept="application/json")
    leidas = parse_usgs(texto)
    lecturas, umbrales = [], {}
    for e in ests:
        if e.ref in leidas:
            v, t = leidas[e.ref]
            lecturas.append(Lectura(e.id, v, "ft", t, "usgs"))
        umbrales[e.id] = _EN_ESTUDIO
        if e.lid:
            try:
                umbrales[e.id] = parse_nwps(red.get_texto(
                    url_nwps(e.lid), fuente="NWS", abrir=abrir, intentos=intentos,
                    dormir=dormir, accept="application/json"))
            except FuenteError:
                pass
    return lecturas, umbrales
