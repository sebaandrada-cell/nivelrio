"""Umbrales estimados a partir de series históricas de caudal diario. No son umbrales oficiales.

Aproxima periodos de retorno con el máximo anual de la serie diaria: bajo ~ T=2 años (mediana de los
máximos anuales), medio ~ T=5 (percentil 80), alto ~ T=20 (percentil 95). Sesgo conocido: las medias
diarias subestiman los picos, y los ríos regulados no siguen la estadística natural.
"""
import math
import statistics
from datetime import date

from modelo import Umbrales

MIN_ANIOS = 5
MIN_DIAS_ANIO_COMPLETO = 300


def estimar(serie: list[tuple[date, float]]) -> Umbrales:
    """`serie` son pares (día, caudal medio diario en m3/s). Lanza ValueError si no se puede estimar."""
    por_anio: dict[int, list[float]] = {}
    for dia, q in serie:
        if q is not None and math.isfinite(q):
            por_anio.setdefault(dia.year, []).append(q)
    maximos = [max(v) for v in por_anio.values() if len(v) >= MIN_DIAS_ANIO_COMPLETO]
    if len(maximos) < MIN_ANIOS:
        raise ValueError(f"hacen falta al menos {MIN_ANIOS} años completos y hay {len(maximos)}")
    bajo = statistics.median(maximos)
    medio = statistics.quantiles(maximos, n=10, method="inclusive")[7]  # percentil 80
    alto = statistics.quantiles(maximos, n=20, method="inclusive")[18]  # percentil 95
    if not (0 < bajo < medio < alto):
        raise ValueError(f"umbrales no crecientes: {bajo}, {medio}, {alto}")
    return Umbrales(round(bajo, 3), round(medio, 3), round(alto, 3), "estimado")


def emparejar_por_utm(utm: tuple[float, float], candidatas: list[dict], radio_m: float = 150) -> dict | None:
    """Estación del dataset histórico más cercana (coordenadas UTM) dentro de `radio_m`, o None."""
    mejor, mejor_d = None, radio_m
    for c in candidatas:
        d = math.hypot(float(c["utm_x"]) - utm[0], float(c["utm_y"]) - utm[1])
        if d <= mejor_d:
            mejor, mejor_d = c, d
    return mejor
