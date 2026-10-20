#!/usr/bin/env python3
"""Arma index.html con fuente/page.html, fuente/textos.json y fuente/web/logica.js.

La página es estática: lee data/paises.json y, del país activo, data/<pais>/{latest,prevision}.json y history/ con fetch.
Aquí no se incrustan datos. Uso, desde la raíz del repo: python3 fuente/armar_sitio.py
"""
import html
import json
import os
import re
from datetime import datetime

F = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(F)


def _leer(*partes: str) -> str:
    with open(os.path.join(F, *partes), encoding="utf-8") as f:
        return f.read()


def armar() -> str:
    textos = json.loads(_leer("textos.json"))
    # "</" dentro de un <script> cerraría el bloque antes de tiempo
    textos_json = json.dumps(textos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    pagina = _leer("page.html")
    for marca, valor in (
        ("{{DESC_ES}}", html.escape(textos["es"]["desc"], quote=True)),
        ("{{TEXTOS_JSON}}", textos_json),
        ("{{LOGICA_JS}}", _leer("web", "logica.js")),
        ("{{MODULOS_JS}}", _leer("web", "modulos.js")),
    ):
        if marca not in pagina:
            raise ValueError(f"page.html no tiene la marca {marca}")
        pagina = pagina.replace(marca, valor)
    return pagina


# ---------- módulos por río ----------
# Los archivos manuales viven en fuente/paises/<pais>/rios/<id>/ (en el repo) y el armado los valida y copia a
# data/<pais>/rios/<id>/. Así no dependen de la caché de Actions que restaura data/, y el robot (que escribe
# pronostico.json) no los toca ni ellos a él.
ARCHIVOS_MODULOS = ("historicos", "pronostico_manual")
IDIOMAS = ("es", "ca", "en")
UNIDADES = ("m3s", "m", "ft")
TIPOS_HISTORICO = ("crecida", "defensa")


def _texto(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def _numero(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def _en_tres_idiomas(x, donde: str, vacio_ok: bool = False) -> None:
    if isinstance(x, str) and (vacio_ok or x.strip()):
        return
    if isinstance(x, dict) and set(x) == set(IDIOMAS) and all(_texto(x[l]) for l in IDIOMAS):
        return
    raise ValueError(f"{donde}: debe ser un texto o un objeto con {', '.join(IDIOMAS)}")


def validar_historicos(d) -> None:
    if not isinstance(d, dict):
        raise ValueError("historicos: debe ser un objeto")
    if not _texto(d.get("estacion")):
        raise ValueError("historicos: falta estacion")
    if d.get("unidad") not in UNIDADES:
        raise ValueError(f"historicos: unidad inválida: {d.get('unidad')!r}")
    if not _texto(d.get("fuente")):
        raise ValueError("historicos: falta fuente (crédito de quien aporta los datos)")
    if "aviso" in d:
        if not (isinstance(d["aviso"], dict) and set(d["aviso"]) == set(IDIOMAS) and all(_texto(d["aviso"][l]) for l in IDIOMAS)):
            raise ValueError("historicos: aviso debe traer es, ca y en")
    eventos = d.get("eventos")
    if not isinstance(eventos, list) or not eventos:
        raise ValueError("historicos: eventos debe ser una lista no vacía")
    for i, e in enumerate(eventos):
        if not isinstance(e, dict):
            raise ValueError(f"historicos: eventos[{i}] debe ser un objeto")
        if not _texto(e.get("evento")):
            raise ValueError(f"historicos: eventos[{i}] sin nombre")
        if e.get("tipo") not in TIPOS_HISTORICO:
            raise ValueError(f"historicos: eventos[{i}] tipo inválido: {e.get('tipo')!r}")
        if not _numero(e.get("valor")):
            raise ValueError(f"historicos: eventos[{i}] valor no numérico: {e.get('valor')!r}")
        if "nota" not in e:
            raise ValueError(f"historicos: eventos[{i}] sin nota (puede ir vacía)")
        _en_tres_idiomas(e["nota"], f"historicos: eventos[{i}].nota", vacio_ok=True)


def _fecha_utc(s) -> datetime:
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError(f"fecha UTC inválida: {s!r}")
    try:
        return datetime.fromisoformat(s[:-1] + "+00:00")
    except ValueError:
        raise ValueError(f"fecha UTC inválida: {s!r}") from None


def validar_pronostico_manual(d) -> None:
    if not isinstance(d, dict):
        raise ValueError("pronostico_manual: debe ser un objeto")
    if d.get("manual") is not True:
        raise ValueError("pronostico_manual: manual debe ser true (el pronóstico automático lo escribe el robot)")
    if not isinstance(d.get("fecha"), str) or not re.fullmatch(r"\d{4}-\d\d-\d\d", d["fecha"]):
        raise ValueError(f"pronostico_manual: fecha inválida (AAAA-MM-DD): {d.get('fecha')!r}")
    try:
        datetime.fromisoformat(d["fecha"])
    except ValueError:
        raise ValueError(f"pronostico_manual: fecha inválida: {d['fecha']!r}") from None
    if not _texto(d.get("fuente")):
        raise ValueError("pronostico_manual: falta fuente")
    if "unidad" in d and d["unidad"] not in UNIDADES:
        raise ValueError(f"pronostico_manual: unidad inválida: {d['unidad']!r}")
    puntos = d.get("puntos")
    if not isinstance(puntos, list) or not puntos:
        raise ValueError("pronostico_manual: puntos debe ser una lista no vacía")
    for i, p in enumerate(puntos):
        if not isinstance(p, list) or len(p) not in (2, 3):
            raise ValueError(f"pronostico_manual: puntos[{i}] debe ser [fecha, valor] o [fecha, mín, máx]")
        _fecha_utc(p[0])
        if not all(_numero(v) for v in p[1:]):
            raise ValueError(f"pronostico_manual: puntos[{i}] con valores no numéricos")
        if len(p) == 3 and p[1] > p[2]:
            raise ValueError(f"pronostico_manual: puntos[{i}] con mínimo mayor que el máximo")


_VALIDADORES = {"historicos": validar_historicos, "pronostico_manual": validar_pronostico_manual}


def _leer_modulos(src: str):
    """{pais: {id: {archivo: documento}}} validado. Falla con ValueError si algo no cuadra."""
    salida = {}
    for cc in sorted(os.listdir(src)):
        reg = os.path.join(src, cc, "estaciones.json")
        if not os.path.isfile(reg):
            continue
        with open(reg, encoding="utf-8") as f:
            estaciones = {e["id"]: e for e in json.load(f)}
        salida[cc] = {}
        base = os.path.join(src, cc, "rios")
        for id_ in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            carpeta = os.path.join(base, id_)
            if not os.path.isdir(carpeta):
                continue
            if id_ not in estaciones:
                raise ValueError(f"{cc}/rios/{id_}: no es una estación del registro")
            docs = {}
            for nombre in sorted(os.listdir(carpeta)):
                clave = nombre[:-5] if nombre.endswith(".json") else None
                if clave not in _VALIDADORES:
                    raise ValueError(f"{cc}/rios/{id_}/{nombre}: archivo no admitido (solo {', '.join(a + '.json' for a in ARCHIVOS_MODULOS)})")
                with open(os.path.join(carpeta, nombre), encoding="utf-8") as f:
                    try:
                        doc = json.load(f)
                    except ValueError as e:
                        raise ValueError(f"{cc}/rios/{id_}/{nombre}: JSON ilegible: {e}") from None
                try:
                    _VALIDADORES[clave](doc)
                    if "unidad" in doc and doc["unidad"] != estaciones[id_]["unidad"]:
                        raise ValueError(f"unidad {doc['unidad']!r} distinta de la de la estación ({estaciones[id_]['unidad']!r})")
                    if "estacion" in doc and doc["estacion"] != id_:
                        raise ValueError(f"estacion {doc['estacion']!r} no es {id_!r}")
                except ValueError as e:
                    raise ValueError(f"{cc}/rios/{id_}/{nombre}: {e}") from None
                docs[clave] = doc
            if docs:
                salida[cc][id_] = docs
    return salida


def indice_modulos(src: str) -> dict:
    """{pais: {id: [archivos]}}: qué ríos tienen módulos (valida de paso)."""
    return {cc: {i: [a for a in ARCHIVOS_MODULOS if a in docs] for i, docs in rios.items()}
            for cc, rios in _leer_modulos(str(src)).items()}


def copiar_modulos(src: str, data: str) -> dict:
    """Valida y copia los archivos de módulos a data/<pais>/rios/<id>/ y escribe data/<pais>/rios/modulos.json.

    No toca pronostico.json (es del robot). Retira las copias cuyo origen ya no existe."""
    src, data = str(src), str(data)
    modulos = _leer_modulos(src)
    indice = {}
    for cc, rios in modulos.items():
        base = os.path.join(data, cc, "rios")
        for id_, docs in rios.items():
            os.makedirs(os.path.join(base, id_), exist_ok=True)
            for clave, doc in docs.items():
                with open(os.path.join(base, id_, clave + ".json"), "w", encoding="utf-8") as f:
                    json.dump(doc, f, ensure_ascii=False, indent=2)
                    f.write("\n")
        # copias huérfanas de archivos manuales (nunca pronostico.json)
        if os.path.isdir(base):
            for id_ in os.listdir(base):
                for clave in ARCHIVOS_MODULOS:
                    ruta = os.path.join(base, id_, clave + ".json")
                    if os.path.isfile(ruta) and clave not in rios.get(id_, {}):
                        os.remove(ruta)
        os.makedirs(base, exist_ok=True)
        indice[cc] = {i: [a for a in ARCHIVOS_MODULOS if a in docs] for i, docs in rios.items()}
        with open(os.path.join(base, "modulos.json"), "w", encoding="utf-8") as f:
            json.dump(indice[cc], f, ensure_ascii=False, indent=2)
            f.write("\n")
    return indice


def main() -> None:
    copiar_modulos(os.path.join(F, "paises"), os.path.join(RAIZ, "data"))
    with open(os.path.join(RAIZ, "index.html"), "w", encoding="utf-8") as f:
        f.write(armar())
    print("index.html listo")


if __name__ == "__main__":
    main()
