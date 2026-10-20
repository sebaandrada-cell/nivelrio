#!/usr/bin/env python3
"""Arma index.html con fuente/page.html, fuente/textos.json y fuente/web/logica.js.

La página es estática: lee data/paises.json y, del país activo, data/<pais>/{latest,prevision}.json y history/ con fetch.
Aquí no se incrustan datos. Uso, desde la raíz del repo: python3 fuente/armar_sitio.py
"""
import html
import json
import os

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
    ):
        if marca not in pagina:
            raise ValueError(f"page.html no tiene la marca {marca}")
        pagina = pagina.replace(marca, valor)
    return pagina


def main() -> None:
    with open(os.path.join(RAIZ, "index.html"), "w", encoding="utf-8") as f:
        f.write(armar())
    print("index.html listo")


if __name__ == "__main__":
    main()
