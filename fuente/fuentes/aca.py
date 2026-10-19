"""Cliente de la API Sentilo de la Agència Catalana de l'Aigua (aforaments).

Los timestamps de Sentilo (dd/mm/yyyyThh:mi:ss) vienen en UTC (verificado contra el campo
`time` en milisegundos). Los valores son cadenas; un sensor sin lectura reciente trae la lista
de observaciones vacía o el valor "NAN".
"""
import http.client
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from modelo import FuenteError, Lectura

URL_ULTIMOS = "https://aplicacions.aca.gencat.cat/sdim2/apirest/data/AFORAMENT-EST"
URL_CATALOGO = "https://aplicacions.aca.gencat.cat/sdim2/apirest/catalog?componentType=aforament"
USER_AGENT = "rius-catalunya/0.1 (+https://github.com/sebaandrada-cell/nivelrio)"
TIPO_CAUDAL = "0014"
TIPO_NIVEL = "0019"
FMT = "%d/%m/%YT%H:%M:%S"


def _fecha(s: str) -> datetime:
    return datetime.strptime(s, FMT).replace(tzinfo=timezone.utc)


def _numero(texto) -> float | None:
    try:
        v = float(texto)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None  # descarta NaN/inf


def _obs_validas(sensor: dict) -> list[tuple[datetime, float]]:
    salida = []
    for o in sensor.get("observations") or []:
        v = _numero(o.get("value"))
        try:
            t = _fecha(o["timestamp"])
        except (KeyError, ValueError, TypeError):
            continue
        if v is not None:
            salida.append((t, v))
    return salida


def parse_ultimos(doc: dict) -> dict[str, tuple[float, datetime]]:
    """sensor_id -> (valor, t_utc) con la observación más reciente válida."""
    res = {}
    for s in doc.get("sensors", []):
        obs = _obs_validas(s)
        if obs:
            t, v = max(obs)
            res[s["sensor"]] = (v, t)
    return res


def parse_ventana(doc: dict) -> list[tuple[datetime, float]]:
    """Observaciones válidas de un solo sensor, la más nueva primero."""
    sensores = doc.get("sensors", [])
    if not sensores:
        return []
    return sorted(_obs_validas(sensores[0]), reverse=True)


def resolver_sensores(catalogo: dict, componente: str) -> tuple[str | None, str | None]:
    """(sensor_caudal, sensor_nivel) de un componente, buscando por tipo."""
    caudal = nivel = None
    for prov in catalogo.get("providers", []):
        for s in prov.get("sensors", []):
            if s.get("component") != componente:
                continue
            if s.get("type") == TIPO_CAUDAL and caudal is None:
                caudal = s["sensor"]
            elif s.get("type") == TIPO_NIVEL and nivel is None:
                nivel = s["sensor"]
    return caudal, nivel


def lecturas_para(estaciones, ultimos: dict, catalogo: dict) -> list[Lectura]:
    """Una lectura por estación ACA: caudal en m3s; si no hay, nivel en cm; si no, ninguna."""
    salida = []
    for est in estaciones:
        if est.fuente != "aca":
            continue
        caudal, nivel = resolver_sensores(catalogo, est.componente)
        if caudal in ultimos:
            v, t = ultimos[caudal]
            salida.append(Lectura(est.id, v, "m3s", t, "aca"))
        elif nivel in ultimos:
            v, t = ultimos[nivel]
            salida.append(Lectura(est.id, v, "cm", t, "aca"))
    return salida


def url_ventana(sensor: str, desde: datetime, hasta: datetime) -> str:
    f = lambda d: d.astimezone(timezone.utc).strftime(FMT)  # noqa: E731
    return f"{URL_ULTIMOS}/{sensor}?limit=30&from={f(desde)}&to={f(hasta)}"


def bajar(url: str, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep) -> dict:
    """GET con reintentos y espera creciente. Lanza FuenteError al agotar los intentos."""
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with abrir(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError) as e:
            ultimo = e
            if i < intentos - 1:
                dormir(2 ** i)
    raise FuenteError(f"ACA: {url} falló tras {intentos} intentos: {ultimo}")
