"""Estación automática del puerto de Barranqueras (Administración General de Puertos, AGP): altura del Paraná.

Fuente: https://hidrografia2.agpse.gob.ar/histdat/Barranqueras.dat (archivo de datalogger: 4 líneas
de cabecera y luego columnas TIMESTAMP, RECORD, NIvel_Avg, Altura_Avg, Offset). Se toma Altura_Avg,
en metros. El TIMESTAMP es hora de Argentina, UTC-3 fijo, y se convierte a UTC.

Basado en `bajar` y `agp` de fuente/agp_update.py de Pablo Dodda (apuratejose, licencia MIT).

TLS: siempre se verifica el certificado. El servidor del puerto no envía la cadena completa (falta
el certificado intermedio), de modo que desde algunos entornos la verificación falla. Pablo reintenta
sin verificar para ese host; acá NO: desactivar la verificación permite a cualquiera en la ruta
inyectar alturas falsas en un panel de alertas de inundación. Un error de certificado termina en
FuenteError y la estación se cubre con la lectura del INA (misma estación, ver `elegir`).
"""
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from fuentes import red
from modelo import Lectura

URL = "https://hidrografia2.agpse.gob.ar/histdat/Barranqueras.dat"

_ARGENTINA = timezone(timedelta(hours=-3))
_CABECERA = 4
_FECHA = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d")


def parse(texto: str) -> tuple[datetime, float] | None:
    """Última lectura válida como (t_utc, altura en m), o None si no hay ninguna.

    Se descartan las filas sin fecha legible, con altura NAN o ilegible y las fuera de 0 < h < 15.
    """
    ultima = None
    for linea in texto.splitlines()[_CABECERA:]:
        c = [x.strip().strip('"') for x in linea.split(",")]
        if len(c) < 4 or not _FECHA.match(c[0]):
            continue
        try:
            h = float(c[3])
        except ValueError:
            continue  # NAN
        if not 0 < h < 15:  # también descarta inf/nan numéricos
            continue
        t = datetime.strptime(c[0][:16], "%Y-%m-%d %H:%M").replace(tzinfo=_ARGENTINA)
        ultima = (t.astimezone(timezone.utc), round(h, 2))
    return ultima


def bajar(abrir=urllib.request.urlopen, intentos: int = 3, dormir=time.sleep) -> str:
    return red.get_texto(URL, fuente="AGP", abrir=abrir, intentos=intentos, dormir=dormir,
                         accept="text/plain,*/*")


def lecturas_para(estaciones, ultima: tuple[datetime, float] | None) -> list[Lectura]:
    if ultima is None:
        return []
    t_utc, h = ultima
    return [Lectura(e.id, h, "m", t_utc, "agp") for e in estaciones if e.fuente == "agp"]


def elegir(lectura_agp: Lectura | None, lectura_ina: Lectura | None, ahora: datetime,
           max_horas: float = 3) -> Lectura | None:
    """AGP si existe y tiene como mucho `max_horas`; si no, la del INA; si no, None.

    Una lectura con fecha posterior a `ahora` se ignora (reloj o dato corrupto).
    """
    limite = timedelta(hours=max_horas)
    if lectura_agp is not None and timedelta(0) <= ahora - lectura_agp.t_utc <= limite:
        return lectura_agp
    if lectura_ina is not None and ahora - lectura_ina.t_utc >= timedelta(0):
        return lectura_ina
    return None
