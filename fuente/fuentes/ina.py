"""Cliente del Instituto Nacional del Agua (INA, Argentina): alturas hidrométricas del Paraná y afluentes.

Fuente: https://www.hidraulica.gob.ar/ina/ajax.estaciones.json.php (JSON que alimenta el mapa
del INA; no es una API documentada, así que si cambia el formato se lanza FuenteError).

Las alturas vienen en metros. `fecha_actual` ("20/10/2026 00:00") es hora de Argentina, UTC-3
fijo (sin horario de verano), y se convierte a UTC.

Umbrales: el INA publica `nivel_alerta` y `nivel_evacuacion`. El N2 (medio) es el nivel de
alerta y el N3 (alto) el de evacuación. El N1 (bajo) NO es oficial: es regla propia del
proyecto, 90 % del nivel de alerta. Si falta alguno o no cumple 0 < alerta < evacuación,
los umbrales quedan "en_estudio".
"""
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from fuentes import red
from modelo import FuenteError, Lectura, Umbrales

URL = "https://www.hidraulica.gob.ar/ina/ajax.estaciones.json.php"

_ARGENTINA = timezone(timedelta(hours=-3))
_FORMATO_FECHA = "%d/%m/%Y %H:%M"


def _num(x) -> float | None:
    """Acepta número o texto numérico; bool, None o basura -> None."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def umbrales(fila: dict) -> Umbrales:
    alerta, evac = _num(fila.get("nivel_alerta")), _num(fila.get("nivel_evacuacion"))
    if alerta is None or evac is None or not (0 < alerta < evac):
        return Umbrales(None, None, None, "en_estudio")
    return Umbrales(round(0.9 * alerta, 3), alerta, evac, "oficial")


def _fecha_utc(s: str) -> datetime:
    return datetime.strptime(s, _FORMATO_FECHA).replace(tzinfo=_ARGENTINA).astimezone(timezone.utc)


def parse(filas: list[dict]) -> dict[str, dict]:
    """estacion_id (texto) -> {"valor": float, "t_utc": datetime, "umbrales": Umbrales}.

    Se descartan las filas no vigentes, sin valor o con fecha ilegible.
    """
    res = {}
    for f in filas:
        if not isinstance(f, dict) or f.get("vigente") is not True or f.get("estacion_id") is None:
            continue
        v = _num(f.get("valor_actual"))
        if v is None:
            continue
        try:
            t = _fecha_utc(f["fecha_actual"])
        except (KeyError, ValueError, TypeError):
            continue
        res[str(f["estacion_id"])] = {"valor": v, "t_utc": t, "umbrales": umbrales(f)}
    return res


def lecturas_para(estaciones, parseadas: dict[str, dict]) -> list[Lectura]:
    salida = []
    for est in estaciones:
        if est.fuente != "ina" or est.ref is None:
            continue
        p = parseadas.get(str(est.ref))
        if p:
            salida.append(Lectura(est.id, p["valor"], "m", p["t_utc"], "ina"))
    return salida


def _es_lista_json(texto: str) -> None:
    if not isinstance(json.loads(texto), list):  # JSONDecodeError es ValueError
        raise ValueError("la respuesta no es una lista JSON")


def bajar(abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep) -> list[dict]:
    texto = red.get_texto(URL, fuente="INA", abrir=abrir, intentos=intentos, dormir=dormir,
                          validar=_es_lista_json, accept="application/json")
    return json.loads(texto)
