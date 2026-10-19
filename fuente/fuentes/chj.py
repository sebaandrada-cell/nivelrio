"""Cliente del SAIH de la Confederación Hidrográfica del Júcar.

La página https://saih.chj.es/mapa-aforos lleva los aforos como un array JavaScript
(`let aforos = [...]`) dentro del HTML. No es una API oficial: si la página cambia, el parseo
lanza FuenteError y las estaciones CHJ quedan en "sin datos".
"""
import http.client
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from modelo import FuenteError, Lectura, Umbrales

URL_AFOROS = "https://saih.chj.es/mapa-aforos"
USER_AGENT = "rius-catalunya/0.1 (+https://github.com/sebaandrada-cell/nivelrio)"


def extraer_array(html: str, nombre: str) -> list[dict]:
    """Localiza `let <nombre> = [` y devuelve el array como JSON (respeta cadenas con corchetes)."""
    marca = f"let {nombre} = ["
    i = html.find(marca)
    if i < 0:
        raise FuenteError(f"CHJ: no aparece '{marca}' en la página")
    try:
        arr, _ = json.JSONDecoder().raw_decode(html, i + len(marca) - 1)
    except ValueError as e:
        raise FuenteError(f"CHJ: el array '{nombre}' no es JSON válido: {e}") from e
    if not isinstance(arr, list):
        raise FuenteError(f"CHJ: '{nombre}' no es una lista")
    return arr


def _umbrales(a: dict) -> Umbrales:
    b, m, al = a.get("fldFUmbralBajo"), a.get("fldFUmbralMedio"), a.get("fldFUmbralAlto")
    if None in (b, m, al) or not (0 < b < m < al):
        return Umbrales(None, None, None, "en_estudio")
    return Umbrales(float(b), float(m), float(al), "oficial")


def _fecha_iso_z(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_aforos(html: str) -> dict[str, dict]:
    """fldTCodigo -> {"valor": float | None, "t_utc": datetime, "umbrales": Umbrales}.

    Solo cuentan los aforos de caudal (fldTTipo "Af"): algunos códigos se repiten en embalses.
    """
    res = {}
    for a in extraer_array(html, "aforos"):
        if a.get("fldTTipo") != "Af" or not a.get("fldTCodigo"):
            continue
        try:
            t = _fecha_iso_z(a["fldDFechaComunicacion"])
        except (KeyError, ValueError, TypeError):
            continue
        v = a.get("lastValue")
        res[a["fldTCodigo"]] = {
            "valor": float(v) if isinstance(v, (int, float)) else None,
            "t_utc": t,
            "umbrales": _umbrales(a),
        }
    return res


def lecturas_para(estaciones, aforos: dict[str, dict]) -> list[Lectura]:
    salida = []
    for est in estaciones:
        if est.fuente != "chj":
            continue
        a = aforos.get(est.id_cha)
        if a and a["valor"] is not None:
            salida.append(Lectura(est.id, a["valor"], "m3s", a["t_utc"], "chj"))
    return salida


def bajar_aforos(abrir=urllib.request.urlopen, intentos: int = 5, dormir=time.sleep) -> str:
    """GET de la página con reintentos: el servidor corta cerca de 1 de cada 3 conexiones."""
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(URL_AFOROS, headers={"User-Agent": USER_AGENT})
            with abrir(req, timeout=30) as r:
                html = r.read().decode("utf-8")
            if "let aforos = [" not in html:
                raise ValueError("la página no trae el array de aforos")
            return html
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError) as e:
            ultimo = e
            if i < intentos - 1:
                dormir(min(2 ** i, 8))
    raise FuenteError(f"CHJ: {URL_AFOROS} falló tras {intentos} intentos: {ultimo}")
