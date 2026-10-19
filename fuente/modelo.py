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
    unidad: str  # "m3s" | "cm"
    t_utc: datetime
    fuente: str


@dataclass(frozen=True)
class Estacion:
    id: str
    rio: str
    nombre: str
    cuenca: str
    fuente: str  # "aca" | "chj"
    muestreo_min: int
    umbrales: Umbrales
    componente: str | None  # código Sentilo
    id_cha: str | None  # fldTCodigo de la CHJ
    lat: float
    lon: float
    zona: str


@dataclass(frozen=True)
class Aviso:
    origen: str
    nivel: str  # "amarillo" | "naranja" | "rojo"
    zona: str
    descripcion: str
    t_utc: datetime
    region: str = ""  # "cat" | "val": a qué estaciones puede afectar; lo asigna quien arma la lista de avisos
