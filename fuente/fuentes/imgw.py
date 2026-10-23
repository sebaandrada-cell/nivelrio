"""Cliente del API pública de hidrología del IMGW-PIB (Instituto Meteorológico e Hidrológico de Polonia).

https://danepubliczne.imgw.pl/api/data/hydro/id/<id_stacji> devuelve una lista con un solo objeto
por estación: `stan_wody` (nivel, cm) y `przeplyw` (caudal, m3/s), cada uno con su propia fecha de
medición. Las fechas llegan como "YYYY-MM-DD HH:MM:SS" sin zona horaria; están en UTC (verificado
contra otras fuentes el 2026-10-23: no hay desfase horario, a diferencia de la hora local polaca).

IMGW publica umbrales oficiales por estación: `stan_ostrzegawczy` (aviso) y `stan_alarmowy`
(alarma), ambos en cm. Son solo dos niveles (no tres), así que no alcanzan para "oficial" en el
esquema de Umbrales de este proyecto (bajo/medio/alto); se guardan igual en el documento de
previsión informal más adelante si se decide usarlos, pero por ahora la estación entra como
"en_estudio" para no inventar un tercer umbral.
"""
import json
import time
import urllib.request
from datetime import datetime, timezone

from fuentes import red
from modelo import FuenteError, Lectura

URL_BASE = "https://danepubliczne.imgw.pl/api/data/hydro/id"


def url_estacion(id_stacji: str) -> str:
    return f"{URL_BASE}/{id_stacji}"


def _num(x) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _utc(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def parse(texto: str, id_stacji: str) -> tuple[float, datetime] | None:
    """(nivel en cm, t_utc) de la estación `id_stacji`, o None si no hay lectura numérica."""
    try:
        d = json.loads(texto)
    except ValueError as e:
        raise FuenteError(f"IMGW: JSON ilegible: {e}") from e
    filas = d if isinstance(d, list) else [d]
    fila = next((f for f in filas if str(f.get("id_stacji")) == str(id_stacji)), None)
    if fila is None:
        return None
    v = _num(fila.get("stan_wody"))
    t = fila.get("stan_wody_data_pomiaru")
    if v is None or not t:
        return None
    try:
        return v / 100.0, _utc(t)  # cm -> m, como el resto de las estaciones de "altura"
    except ValueError:
        return None


def bajar(id_stacji: str, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep) -> str:
    return red.get_texto(url_estacion(id_stacji), fuente="IMGW", abrir=abrir, intentos=intentos,
                         dormir=dormir, validar=json.loads, accept="application/json")


def bajar_todo(estaciones, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep):
    """(lecturas, {}) para las estaciones con fuente == "imgw". Cada una se consulta por separado:
    el API no ofrece un filtro por lista de ids y descargar las ~900 estaciones del país por una
    sola estación sería desproporcionado."""
    ests = [e for e in estaciones if e.fuente == "imgw" and e.ref]
    lecturas = []
    fallo = None
    for e in ests:
        try:
            texto = bajar(e.ref, abrir=abrir, intentos=intentos, dormir=dormir)
        except FuenteError as exc:
            fallo = exc
            continue
        par = parse(texto, e.ref)
        if par is not None:
            v, t = par
            lecturas.append(Lectura(e.id, v, "m", t, "imgw"))
    if not lecturas and ests and fallo is not None:
        raise fallo
    return lecturas, {}
