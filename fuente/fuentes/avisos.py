"""Avisos oficiales: AEMET (feeds RSS de avisos CAP) y plan INUNCAT de Protecció Civil.

El RSS de AEMET lista un ítem por aviso, con el nivel en el título y el periodo en la descripción
("de 19:00 19-10-2026 CEST (UTC+2) a 23:59 19-10-2026 CEST (UTC+2)"). El feed puede traer avisos que
ya terminaron: se descartan aquí. Solo se conservan Lluvias y Tormentas; Costeros, Viento, etc. no
son avisos de crecida.
"""
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fuentes import red
from modelo import Aviso, FuenteError

URL_CAP = {
    "cat": "https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAC69_RSS.xml",
    "val": "https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAC77_RSS.xml",
}
URL_INUNCAT = "https://analisi.transparenciacatalunya.cat/resource/wj9c-j6vf.json"
FENOMENOS = ("Lluvias", "Tormentas")

_TITULO = re.compile(r"^Aviso\. Nivel (amarillo|naranja|rojo)\. ([^.]+)\. (.+)$")
_PERIODO = re.compile(
    r"de (\d\d):(\d\d) (\d\d)-(\d\d)-(\d{4}) \S+ \(UTC([+-]\d+)\) "
    r"a (\d\d):(\d\d) (\d\d)-(\d\d)-(\d{4}) \S+ \(UTC([+-]\d+)\)"
)


def _utc(hh, mm, dd, mo, yyyy, off) -> datetime:
    local = datetime(int(yyyy), int(mo), int(dd), int(hh), int(mm), tzinfo=timezone(timedelta(hours=int(off))))
    return local.astimezone(timezone.utc)


def _pubdate(item) -> datetime | None:
    txt = item.findtext("pubDate")
    try:
        return datetime.fromisoformat(txt).astimezone(timezone.utc) if txt else None
    except ValueError:
        return None


def parse_cap(xml: str, ahora: datetime | None = None) -> list[Aviso]:
    """Avisos vigentes (los que no han terminado) de Lluvias y Tormentas de un feed RSS de AEMET."""
    ahora = ahora or datetime.now(timezone.utc)
    try:
        canal = ET.fromstring(xml).find("channel")
    except ET.ParseError as e:
        raise FuenteError(f"AEMET: XML inválido: {e}") from e
    if canal is None:
        raise FuenteError("AEMET: el documento no es un feed RSS (falta <channel>)")
    salida = []
    for it in canal.findall("item"):
        m = _TITULO.match((it.findtext("title") or "").strip())
        if not m or m.group(2) not in FENOMENOS:
            continue
        nivel, fenomeno, zona = m.groups()
        desc = (it.findtext("description") or "").strip()
        p = _PERIODO.search(desc)
        if p:
            g = p.groups()
            inicio, fin = _utc(g[0], g[1], g[2], g[3], g[4], g[5]), _utc(g[6], g[7], g[8], g[9], g[10], g[11])
            if fin < ahora:
                continue
        else:  # periodo ilegible: un aviso oficial no se descarta en silencio
            inicio = _pubdate(it) or ahora
        salida.append(Aviso("AEMET", nivel, zona, f"{fenomeno}: {desc}", inicio))
    return salida


def _normalizar(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").upper().strip()


_FASES = {"PREALERTA": "amarillo", "ALERTA": "naranja", "EMERGENCIA": "rojo"}


def parse_inuncat(filas: list[dict]) -> Aviso | None:
    """Fase activa del plan INUNCAT (dataset wj9c-j6vf), o None si no hay ninguna activada."""
    for f in filas:
        if _normalizar(f.get("plaacronim", "")) != "INUNCAT" or _normalizar(f.get("plaactivat", "")) != "SI":
            continue
        fase = _normalizar(f.get("plafase", ""))
        if fase not in _FASES:
            raise FuenteError(f"INUNCAT: fase desconocida {f.get('plafase')!r}")
        try:
            t = datetime.strptime(f["fasedatahora"], "%d/%m/%Y %H:%M").replace(tzinfo=ZoneInfo("Europe/Madrid"))
        except (KeyError, ValueError) as e:
            raise FuenteError(f"INUNCAT: fecha ilegible {f.get('fasedatahora')!r}") from e
        return Aviso("INUNCAT", _FASES[fase], "Catalunya", (f.get("descripcio") or "").strip(), t.astimezone(timezone.utc))
    return None


def bajar_cap(clave: str, **kw) -> str:
    return red.get_texto(URL_CAP[clave], fuente="AEMET", accept="application/rss+xml, text/xml", **kw)


def bajar_inuncat(**kw) -> list[dict]:
    texto = red.get_texto(URL_INUNCAT, fuente="INUNCAT", accept="application/json", **kw)
    try:
        return json.loads(texto)
    except ValueError as e:
        raise FuenteError(f"INUNCAT: respuesta no es JSON: {e}") from e
