#!/usr/bin/env python3
"""Calibra los umbrales estimados de las estaciones ACA con la serie histórica de Socrata.

Herramienta manual (usa red, no se ejecuta en el cron). Para cada estación ACA de estaciones.json que
no tenga umbrales oficiales:
  1. busca su estación en el dataset hprm-xuw7 (caudales diarios medios desde 2000) emparejando por
     coordenadas UTM, porque los códigos de Sentilo y de Socrata son distintos;
  2. compara el caudal actual de Sentilo con la última media diaria del dataset (misma magnitud) para
     aceptar la equivalencia;
  3. estima los umbrales con umbrales.estimar.

Uso:  python3 fuente/herramientas/calibrar_umbrales.py            (solo informa)
      python3 fuente/herramientas/calibrar_umbrales.py --escribir (reescribe estaciones.json)
"""
import json
import os
import sys
import urllib.parse
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, ".."))

from fuentes import aca, red  # noqa: E402
from modelo import FuenteError  # noqa: E402
from umbrales import emparejar_por_utm, estimar  # noqa: E402

SOCRATA = "https://analisi.transparenciacatalunya.cat/resource/hprm-xuw7.json"
ESTACIONES = os.path.join(AQUI, "..", "paises", "es", "estaciones.json")
FACTOR_EQUIVALENCIA = 4.0  # el caudal actual y la media diaria pueden diferir, pero no en otro orden de magnitud


def soql(**params) -> list[dict]:
    q = urllib.parse.urlencode({"$" + k: v for k, v in params.items()})
    return json.loads(red.get_texto(f"{SOCRATA}?{q}", fuente="Socrata", intentos=3, timeout=90))


def utm_de_componente(catalogo: dict, componente: str):
    for prov in catalogo.get("providers", []):
        for s in prov.get("sensors", []):
            if s.get("component") == componente:
                info = s.get("componentAdditionalInfo") or {}
                try:
                    return float(info["Coordenada X (UTM ETRS89)"]), float(info["Coordenada Y (UTM ETRS89)"])
                except (KeyError, ValueError):
                    continue
    return None


def serie_diaria(codi_estacio: str) -> list[tuple]:
    filas = soql(select="codi_variable,count(*)", where=f"codi_estacio='{codi_estacio}' AND tipus_variable='Cabal riu'",
                 group="codi_variable")
    if not filas:
        return []
    variable = max(filas, key=lambda f: int(f["count"]))["codi_variable"]  # la variable de caudal con más historia
    datos = soql(select="dia,valor", where=f"codi_estacio='{codi_estacio}' AND codi_variable='{variable}'",
                 order="dia", limit=50000)
    return [(datetime.fromisoformat(d["dia"]).date(), float(d["valor"])) for d in datos if d.get("valor") not in (None, "")]


def main(escribir: bool) -> int:
    with open(ESTACIONES, encoding="utf-8") as f:
        estaciones = json.load(f)
    print("Descargando catálogo y últimos valores de Sentilo...")
    catalogo = aca.bajar(aca.URL_CATALOGO)
    ultimos = aca.parse_ultimos(aca.bajar(aca.URL_ULTIMOS))
    candidatas = soql(select="codi_estacio,estacio,utm_x,utm_y", where="tipus_variable='Cabal riu'",
                      group="codi_estacio,estacio,utm_x,utm_y", limit=5000)
    cambios = 0
    for e in estaciones:
        if e["fuente"] != "aca" or e["umbrales"]["tipo"] == "oficial":
            continue
        nombre = f'{e["rio"]} · {e["nombre"]}'
        utm = utm_de_componente(catalogo, e["componente"])
        par = emparejar_por_utm(utm, candidatas) if utm else None
        if not par:
            print(f"- {nombre}: sin estación equivalente en Socrata (se queda en estudio)")
            continue
        try:
            serie = serie_diaria(par["codi_estacio"])
            u = estimar(serie)
        except (ValueError, FuenteError) as ex:
            print(f"- {nombre} ({par['codi_estacio']}): no se puede estimar: {ex}")
            continue
        caudal, _ = aca.resolver_sensores(catalogo, e["componente"])
        actual = ultimos.get(caudal, (None, None))[0]
        ultima = serie[-1][1]
        ok = actual is not None and ultima > 0 and 1 / FACTOR_EQUIVALENCIA <= (actual / ultima if ultima else 0) <= FACTOR_EQUIVALENCIA
        marca = "OK" if ok else "REVISAR"
        print(f"- {nombre} ({par['codi_estacio']}, {len(serie)} días desde {serie[0][0]}): "
              f"V {u.bajo} · A {u.medio} · P {u.alto} m3/s | Sentilo ahora {actual} vs media diaria {ultima} → {marca}")
        if ok and escribir:
            e["umbrales"] = {"bajo": u.bajo, "medio": u.medio, "alto": u.alto, "tipo": "estimado"}
            cambios += 1
    print("\nAviso: las medias diarias subestiman los picos, y los ríos regulados (Llobregat, Ter) no siguen la "
          "estadística natural. Son umbrales estimados, no oficiales.")
    if escribir:
        with open(ESTACIONES, "w", encoding="utf-8") as f:
            json.dump(estaciones, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"estaciones.json actualizado: {cambios} estaciones con umbrales estimados.")
    return 0


if __name__ == "__main__":
    sys.exit(main("--escribir" in sys.argv))
