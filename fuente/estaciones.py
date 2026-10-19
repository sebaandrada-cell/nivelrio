"""Carga y validación del catálogo de estaciones (fuente/estaciones.json)."""
import json

from modelo import Estacion, Umbrales

FUENTES = ("aca", "chj")
ZONAS = ("tarragona", "barcelona", "girona", "interior", "valencia")
TIPOS_UMBRAL = ("oficial", "estimado", "en_estudio")


def _umbrales(id_, d):
    if d.get("tipo") not in TIPOS_UMBRAL:
        raise ValueError(f"{id_}: tipo de umbral inválido: {d.get('tipo')!r}")
    u = Umbrales(d.get("bajo"), d.get("medio"), d.get("alto"), d["tipo"])
    if u.tipo != "en_estudio":
        if None in (u.bajo, u.medio, u.alto) or not (u.bajo < u.medio < u.alto):
            raise ValueError(f"{id_}: umbrales no crecientes: {u}")
    return u


def cargar(ruta: str) -> list[Estacion]:
    with open(ruta, encoding="utf-8") as f:
        crudo = json.load(f)
    vistos, salida = set(), []
    for d in crudo:
        id_ = d["id"]
        if id_ in vistos:
            raise ValueError(f"id repetido: {id_}")
        vistos.add(id_)
        if d["fuente"] not in FUENTES:
            raise ValueError(f"{id_}: fuente desconocida: {d['fuente']!r}")
        if d["fuente"] == "aca" and not d.get("componente"):
            raise ValueError(f"{id_}: falta componente")
        if d["fuente"] == "chj" and not d.get("id_cha"):
            raise ValueError(f"{id_}: falta id_cha")
        if d.get("zona") not in ZONAS:
            raise ValueError(f"{id_}: zona inválida: {d.get('zona')!r}")
        salida.append(Estacion(
            id=id_, rio=d["rio"], nombre=d["nombre"], cuenca=d["cuenca"], fuente=d["fuente"],
            muestreo_min=int(d["muestreo_min"]), umbrales=_umbrales(id_, d["umbrales"]),
            componente=d.get("componente"), id_cha=d.get("id_cha"),
            lat=float(d["lat"]), lon=float(d["lon"]), zona=d["zona"],
        ))
    return salida
