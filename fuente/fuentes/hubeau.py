"""Cliente del API pública Hub'Eau - Hydrométrie (gobierno de Francia, hubeau.eaufrance.fr).

https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr?code_entite=<code>&grandeur_hydro=Q
&size=1&sort=desc devuelve la observación de caudal más reciente de una estación. `resultat_obs`
viene en L/s (se convierte a m3/s); `date_obs` ya es UTC con "Z". No hace falta clave ni registro.
"""
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from fuentes import red
from modelo import FuenteError, Lectura

URL_BASE = "https://hubeau.eaufrance.fr/api/v2/hydrometrie/observations_tr"


def url_ultima(code_entite: str, grandeur: str = "Q") -> str:
    q = urllib.parse.urlencode({
        "code_entite": code_entite, "grandeur_hydro": grandeur,
        "size": 1, "sort": "desc", "format": "json",
    })
    return f"{URL_BASE}?{q}"


def _num(x) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def parse(texto: str) -> tuple[float, datetime] | None:
    """(caudal en m3/s, t_utc) de la observación más reciente, o None si no hay ninguna."""
    try:
        d = json.loads(texto)
    except ValueError as e:
        raise FuenteError(f"Hub'Eau: JSON ilegible: {e}") from e
    filas = d.get("data") if isinstance(d, dict) else None
    if not filas:
        return None
    fila = filas[0]
    v = _num(fila.get("resultat_obs"))
    ts = fila.get("date_obs")
    if v is None or not ts:
        return None
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return v / 1000.0, t.astimezone(timezone.utc)  # L/s -> m3/s


def bajar(code_entite: str, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep) -> str:
    return red.get_texto(url_ultima(code_entite), fuente="Hub'Eau", abrir=abrir, intentos=intentos,
                         dormir=dormir, validar=json.loads, accept="application/json")


def bajar_todo(estaciones, abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep):
    """(lecturas, {}) para las estaciones con fuente == "hubeau". Una petición por estación."""
    ests = [e for e in estaciones if e.fuente == "hubeau" and e.ref]
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
            lecturas.append(Lectura(e.id, v, "m3s", t, "hubeau"))
    if not lecturas and ests and fallo is not None:
        raise fallo
    return lecturas, {}
