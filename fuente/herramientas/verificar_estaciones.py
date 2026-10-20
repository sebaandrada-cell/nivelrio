#!/usr/bin/env python3
"""Comprueba que cada estación de estaciones.json existe en su fuente y da una lectura.

Herramienta manual (usa red). Imprime una línea por estación con los sensores que resuelve, el valor
actual y su edad. Sale con código 1 si alguna estación no se resuelve.
Uso, desde la raíz del repo: python3 fuente/herramientas/verificar_estaciones.py
"""
import os
import sys
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, ".."))

from estaciones import cargar  # noqa: E402
from fuentes import aca, chj  # noqa: E402

ESTACIONES = os.path.join(AQUI, "..", "paises", "es", "estaciones.json")


def main() -> int:
    ests = cargar(ESTACIONES, "es")  # valida zona, coordenadas, ids repetidos y umbrales
    ahora = datetime.now(timezone.utc)
    catalogo = aca.bajar(aca.URL_CATALOGO)
    ultimos = aca.parse_ultimos(aca.bajar(aca.URL_ULTIMOS))
    aforos = chj.parse_aforos(chj.bajar_aforos())
    mal = 0
    for e in ests:
        nombre = f"{e.rio} · {e.nombre}"
        if e.fuente == "aca":
            caudal, nivel = aca.resolver_sensores(catalogo, e.componente)
            if not (caudal or nivel):
                print(f"FALLA  {nombre}: el componente {e.componente} no existe en el catálogo")
                mal += 1
                continue
            sensor = caudal or nivel
            unidad = "m3/s" if caudal else "cm (sin caudal)"
            v, t = ultimos.get(sensor, (None, None))
            det = f"caudal={caudal} nivel={nivel}"
        else:
            a = aforos.get(e.id_cha)
            if not a:
                print(f"FALLA  {nombre}: el id_cha {e.id_cha} no está en la página de la CHJ")
                mal += 1
                continue
            v, t, unidad = a["valor"], a["t_utc"], "m3/s"
            det = f"umbrales={a['umbrales'].tipo}"
        edad = f"{int((ahora - t).total_seconds() // 60)} min" if t else "sin dato"
        aviso = "" if v is not None else "  (sin lectura ahora)"
        print(f"OK     {nombre}: {v} {unidad}, edad {edad}, {det}{aviso}")
    print(f"\n{len(ests)} estaciones, {mal} sin resolver")
    return 1 if mal else 0


if __name__ == "__main__":
    sys.exit(main())
