"""Tipos de datos compartidos. Sin lógica ni E/S."""
from dataclasses import dataclass
from datetime import datetime


class FuenteError(Exception):
    """Una fuente de datos falló o devolvió algo que no se puede interpretar."""


@dataclass(frozen=True)
class Umbrales:
    bajo: float | None
    medio: float | None
    alto: float | None
    tipo: str  # "oficial" | "estimado" | "en_estudio"


@dataclass(frozen=True)
class Lectura:
    estacion_id: str
    valor: float
    unidad: str  # "m3s" | "m" | "ft"
    t_utc: datetime
    fuente: str


@dataclass(frozen=True)
class Estacion:
    id: str
    rio: str
    nombre: str
    cuenca: str
    fuente: str  # "aca" | "chj" | "ina" | "agp" | "usgs" | "glofas" (modelo, no observación)
    muestreo_min: int
    umbrales: Umbrales
    componente: str | None  # código Sentilo
    id_cha: str | None  # fldTCodigo de la CHJ
    lat: float
    lon: float
    zona: str
    pais: str = "es"  # "ar" | "es" | "us"
    magnitud: str = "caudal"  # "caudal" | "altura"
    unidad: str = "m3s"  # "m3s" | "m" | "ft"
    ref: str | None = None  # id en la fuente: INA estacion_id, USGS site
    lid: str | None = None  # NWS
    vel_subida_rapida: float | None = None  # por lectura, en la unidad de la estación; None = valor por defecto de la magnitud


@dataclass(frozen=True)
class Aviso:
    origen: str
    nivel: str  # "amarillo" | "naranja" | "rojo"
    zona: str
    descripcion: str
    t_utc: datetime
    region: str = ""  # "cat" | "val": a qué estaciones puede afectar; lo asigna quien arma la lista de avisos
