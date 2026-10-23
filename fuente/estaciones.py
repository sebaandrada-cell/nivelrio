"""Carga y validación del catálogo de estaciones (fuente/paises/<pais>/estaciones.json)."""
import json

from modelo import Estacion, Umbrales

FUENTES = ("aca", "chj", "ina", "agp", "usgs", "glofas", "pegelonline", "hubeau", "ea_uk", "imgw")
PAISES = ("ar", "es", "us", "de", "fr", "gb", "it", "nl", "pl", "pt", "hu", "ru",
          "asia", "centroamerica", "sudamerica", "oceania", "africa")
ZONAS = {
    "es": ("tarragona", "barcelona", "girona", "interior", "valencia", "ebro"),
    "ar": ("chaco-corrientes", "litoral-parana", "uruguay"),
    "us": ("mississippi", "missouri", "ohio", "colorado", "rio-grande"),
    "de": ("rhine",),
    "fr": ("loire",),
    "gb": ("severn",),
    "it": ("po",),
    "nl": ("meuse",),
    "pl": ("vistula",),
    "pt": ("tagus",),
    "hu": ("danube",),
    "ru": ("volga",),
    "asia": ("yangtze", "ganges", "mekong"),
    "centroamerica": ("san-juan", "usumacinta", "lempa"),
    "sudamerica": ("amazonas", "orinoco", "parana"),
    "oceania": ("murray", "sepik", "waikato"),
    "africa": ("nile", "congo", "niger"),
}
MAGNITUDES = ("caudal", "altura")
UNIDADES = ("m3s", "m", "ft")
TIPOS_UMBRAL = ("oficial", "estimado", "en_estudio")


def _umbrales(id_, d):
    if d.get("tipo") not in TIPOS_UMBRAL:
        raise ValueError(f"{id_}: tipo de umbral inválido: {d.get('tipo')!r}")
    u = Umbrales(d.get("bajo"), d.get("medio"), d.get("alto"), d["tipo"])
    if u.tipo != "en_estudio":
        if None in (u.bajo, u.medio, u.alto) or not (u.bajo < u.medio < u.alto):
            raise ValueError(f"{id_}: umbrales no crecientes: {u}")
    return u


def cargar(ruta: str, pais: str) -> list[Estacion]:
    if pais not in PAISES:
        raise ValueError(f"país desconocido: {pais!r}")
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
        if d["fuente"] in ("ina", "agp", "usgs", "pegelonline", "hubeau", "ea_uk", "imgw") and not d.get("ref"):
            raise ValueError(f"{id_}: falta ref")
        if d.get("pais", pais) != pais:
            raise ValueError(f"{id_}: país {d.get('pais')!r} no es {pais!r}")
        if d.get("zona") not in ZONAS[pais]:
            raise ValueError(f"{id_}: zona inválida para {pais}: {d.get('zona')!r}")
        if d.get("magnitud") not in MAGNITUDES:
            raise ValueError(f"{id_}: magnitud inválida: {d.get('magnitud')!r}")
        if d.get("unidad") not in UNIDADES:
            raise ValueError(f"{id_}: unidad inválida: {d.get('unidad')!r}")
        vel = d.get("vel_subida_rapida")
        salida.append(Estacion(
            id=id_, rio=d["rio"], nombre=d["nombre"], cuenca=d["cuenca"], fuente=d["fuente"],
            muestreo_min=int(d["muestreo_min"]), umbrales=_umbrales(id_, d["umbrales"]),
            componente=d.get("componente"), id_cha=d.get("id_cha"),
            lat=float(d["lat"]), lon=float(d["lon"]), zona=d["zona"],
            pais=pais, magnitud=d["magnitud"], unidad=d["unidad"], ref=d.get("ref"), lid=d.get("lid"),
            vel_subida_rapida=None if vel is None else float(vel),
        ))
    return salida
