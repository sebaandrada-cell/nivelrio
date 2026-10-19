"""Previsión informativa: lluvia (Open-Meteo) y caudal esperado (GloFAS vía Open-Meteo).

Regla de diseño: nada de este módulo entra en la máquina de alertas. Solo alimenta la etiqueta
«Podría llegar a …» y las tablas de lluvia. Datos: Open-Meteo.com (CC BY 4.0, uso no comercial).
"""
import json
import time
import urllib.parse
import urllib.request

from fuentes import red
from modelo import FuenteError, Umbrales

URL_LLUVIA = "https://api.open-meteo.com/v1/forecast"
URL_CAUDAL = "https://flood-api.open-meteo.com/v1/flood"

DIFERENCIA_MINIMA_M3S = 5.0   # por debajo de esta diferencia el modelo se acepta aunque el cociente sea feo
COCIENTE_MIN, COCIENTE_MAX = 0.2, 5.0


def url_lluvia(lat: float, lon: float) -> str:
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "daily": "precipitation_sum,precipitation_probability_max",
        "forecast_days": 3, "timezone": "Europe/Madrid",
    })
    return f"{URL_LLUVIA}?{q}"


def url_caudal(lat: float, lon: float) -> str:
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "daily": "river_discharge,river_discharge_max", "forecast_days": 3,
    })
    return f"{URL_CAUDAL}?{q}"


def _daily(texto: str) -> dict:
    try:
        datos = json.loads(texto)
    except ValueError as e:
        raise FuenteError(f"Open-Meteo: respuesta que no es JSON: {e}") from e
    if not isinstance(datos, dict) or datos.get("error") or not isinstance(datos.get("daily"), dict):
        motivo = datos.get("reason") if isinstance(datos, dict) else "formato inesperado"
        raise FuenteError(f"Open-Meteo: respuesta sin datos diarios ({motivo})")
    return datos["daily"]


def parse_lluvia(texto: str) -> list[tuple[str, float, int]]:
    d = _daily(texto)
    fechas = d.get("time") or []
    mm = d.get("precipitation_sum") or []
    prob = d.get("precipitation_probability_max") or []
    out = []
    for i, fecha in enumerate(fechas):
        m = mm[i] if i < len(mm) and mm[i] is not None else 0.0
        p = prob[i] if i < len(prob) and prob[i] is not None else 0
        out.append((fecha, float(m), int(p)))
    return out


def parse_caudal(texto: str):
    d = _daily(texto)
    medias = [v for v in (d.get("river_discharge") or []) if v is not None]
    maximos = [v for v in (d.get("river_discharge_max") or []) if v is not None]
    if not maximos:
        maximos = medias
    if not medias:
        medias = maximos
    if not medias:
        return None
    return float(min(medias)), float(max(maximos))


def coherente(q_observado, q_modelo: float) -> bool:
    """La malla de ~5 km a veces engancha otro río: se descarta si no se parece al caudal observado."""
    if q_observado is None:
        return False
    if abs(q_observado - q_modelo) <= DIFERENCIA_MINIMA_M3S:
        return True
    if q_observado <= 0:
        return False
    return COCIENTE_MIN <= q_modelo / q_observado <= COCIENTE_MAX


def nivel_posible(umbrales: Umbrales, q_max: float) -> int:
    if umbrales.tipo == "en_estudio":
        return 0
    if q_max >= umbrales.alto:
        return 3
    if q_max >= umbrales.medio:
        return 2
    if q_max >= umbrales.bajo:
        return 1
    return 0


def bajar(estaciones, abrir=urllib.request.urlopen, dormir=time.sleep) -> dict:
    """estacion_id -> {"lluvia": [...], "caudal": (min, max) | None}, o None si falló la lluvia.
    Una petición por cada par lat,lon. Si fallan todas las estaciones lanza FuenteError."""
    por_punto: dict = {}
    resultado: dict = {}
    for e in estaciones:
        clave = (round(e.lat, 4), round(e.lon, 4))
        if clave not in por_punto:
            por_punto[clave] = _bajar_punto(e.lat, e.lon, abrir, dormir)
        resultado[e.id] = por_punto[clave]
    if estaciones and all(v is None for v in resultado.values()):
        raise FuenteError("Open-Meteo: falló la previsión de todas las estaciones")
    return resultado


def _bajar_punto(lat, lon, abrir, dormir):
    try:
        lluvia = parse_lluvia(red.get_texto(url_lluvia(lat, lon), fuente="Open-Meteo", abrir=abrir,
                                            intentos=2, dormir=dormir, accept="application/json"))
    except FuenteError:
        return None
    try:
        caudal = parse_caudal(red.get_texto(url_caudal(lat, lon), fuente="Open-Meteo (GloFAS)", abrir=abrir,
                                            intentos=2, dormir=dormir, accept="application/json"))
    except FuenteError:
        caudal = None
    return {"lluvia": lluvia, "caudal": caudal}
