#!/usr/bin/env python3
"""Crea un issue de GitHub por cada cambio relevante de nivel. Quien sigue el repositorio recibe el aviso.

Solo notifica subidas de nivel y entradas en «sin datos» de estaciones en N2 o N3; las bajadas no crean issue.
Necesita GH_TOKEN en el entorno (en Actions, `secrets.GITHUB_TOKEN` con permiso issues: write).
"""
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
DIR_DATA = os.path.join(AQUI, "..", "data")
SITIO_DEFECTO = "https://sebaandrada-cell.github.io/nivelrio/"

NIVELES = {0: "Normal", 1: "Vigilancia", 2: "Aviso", 3: "Peligro"}
FUENTES = {"aca": "ACA (Agència Catalana de l'Aigua)", "chj": "CHJ (SAIH Júcar)",
           "ina": "INA (Instituto Nacional del Agua)", "agp": "AGP (Administración General de Puertos)",
           "usgs": "USGS (U.S. Geological Survey)"}
UNIDADES = {"m3s": "m³/s", "cm": "cm", "m": "m", "ft": "ft"}
_PIE_BASE = "Informativo, esquema propio y no oficial. Siga siempre las instrucciones de {quien} y de las autoridades. Emergencias: {tel}."
PIES = {
    "es": _PIE_BASE.format(quien="Protecció Civil", tel="112"),
    "ar": _PIE_BASE.format(quien="Protección Civil y el INA", tel="911"),
    "us": _PIE_BASE.format(quien="su oficina local del NWS (weather.gov) y emergencias locales", tel="911"),
}
PIE = PIES["es"]


def _sitio() -> str:
    return os.environ.get("SITIO") or SITIO_DEFECTO


def _sube(c: dict) -> bool:
    return c["nivel_despues"] > c["nivel_antes"]


def seleccionar(cambios: list[dict]) -> list[dict]:
    return [c for c in cambios if _sube(c) or (c["sd"] and c["nivel_despues"] >= 2)]


def redactar_issue(cambio: dict, estacion_nombre: str, rio: str, valor, unidad: str, edad_min,
                   *, fuente: str = "", tipo_umbral: str = "", pais: str = "") -> tuple[str, str]:
    n = cambio["nivel_despues"]
    solo_sd = cambio["sd"] and not _sube(cambio)
    titulo = (f"[{pais.upper()}] " if pais else "") + f"{rio} · {estacion_nombre}: " + ("sin datos" if solo_sd else f"nivel N{n} ({NIVELES[n]})")

    u = UNIDADES.get(unidad, unidad)
    lineas = []
    if solo_sd:
        lineas.append(f"La estación dejó de enviar datos. Se mantiene el último nivel conocido: N{n} ({NIVELES[n]}).")
    else:
        lineas.append(f"Nivel N{n} ({NIVELES[n]}), antes N{cambio['nivel_antes']} ({NIVELES[cambio['nivel_antes']]}).")
    if cambio["elevado_por_aviso"]:
        lineas.append("El nivel lo eleva un aviso oficial vigente (AEMET o INUNCAT), no solo el caudal medido.")
    if valor is not None:
        lineas.append(f"Último valor: {valor:g} {u}.")
    if edad_min is not None:
        lineas.append(f"Último dato hace {edad_min} min.")
    if fuente:
        lineas.append(f"Fuente: {FUENTES.get(fuente, fuente)}.")
    if tipo_umbral == "oficial":
        lineas.append("Umbrales: oficiales.")
    elif tipo_umbral == "estimado":
        lineas.append("Umbrales: estimado, no oficial.")
    enlace = _sitio() + (f"#{pais}" if pais else "")
    lineas += ["", f"Ver el estado actual: {enlace}", "", PIES.get(pais, PIE)]
    return titulo, "\n".join(lineas)


def _paises_con_cambios(dir_data: str) -> list[str]:
    try:
        return sorted(p for p in os.listdir(dir_data) if os.path.isfile(os.path.join(dir_data, p, "cambios.json")))
    except OSError:
        return []


def main(argv: list[str]) -> int:
    seco = "--dry-run" in argv
    fallos = 0
    for pais in _paises_con_cambios(DIR_DATA):
        try:
            with open(os.path.join(DIR_DATA, pais, "cambios.json"), encoding="utf-8") as f:
                cambios = seleccionar(json.load(f))
            with open(os.path.join(DIR_DATA, pais, "latest.json"), encoding="utf-8") as f:
                por_id = {e["id"]: e for e in json.load(f)["estaciones"]}
        except (OSError, ValueError, KeyError) as exc:
            fallos += 1
            print(f"{pais}: no se pudieron leer los datos: {exc!r}", file=sys.stderr)
            continue
        for c in cambios:
            e = por_id.get(c["estacion_id"])
            if not e:
                continue
            titulo, cuerpo = redactar_issue(c, e["nombre"], e["rio"], e["valor"], e["unidad"], e["edad_min"],
                                            fuente=e["fuente"], tipo_umbral=e["umbrales"]["tipo"], pais=pais)
            if seco:
                print(f"[dry-run] {titulo}\n{cuerpo}\n")
                continue
            r = subprocess.run(["gh", "issue", "create", "--title", titulo, "--body", cuerpo], capture_output=True, text=True)
            if r.returncode != 0:
                fallos += 1
                print(f"gh issue create falló para {c['estacion_id']}: {r.stderr.strip()}", file=sys.stderr)
            else:
                print(r.stdout.strip())
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
