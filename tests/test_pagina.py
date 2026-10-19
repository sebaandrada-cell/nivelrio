import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "fuente"))

import armar_sitio  # noqa: E402

NODE = shutil.which("node")
TEXTOS = json.loads((RAIZ / "fuente" / "textos.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def html():
    return armar_sitio.armar()


def forma(x):
    if isinstance(x, dict):
        return {k: forma(v) for k, v in sorted(x.items())}
    if isinstance(x, list):
        return [forma(v) for v in x]
    return type(x).__name__


def test_index_sin_analitica(html):
    for marca in ("clarity.ms", "cloudflareinsights", "static.cloudflare", "googletagmanager", "google-analytics"):
        assert marca not in html


def test_index_sin_restos_del_proyecto_original(html):
    for marca in ("Resistencia", "Paraná", "apuratejose", "Barranqueras", "Río Negro"):
        assert marca not in html


def test_pie_en_es_y_ca():
    for lang in ("es", "ca"):
        pie = " ".join(TEXTOS[lang]["foot"])
        assert "Protecció Civil" in pie


def test_es_y_ca_tienen_las_mismas_claves():
    assert forma(TEXTOS["es"]) == forma(TEXTOS["ca"])


def test_creditos_incluyen_a_ambos_autores():
    for lang in ("es", "ca"):
        pie = " ".join(TEXTOS[lang]["foot"])
        assert "Pablo Dodda" in pie and "Sebastian Andrada" in pie


def test_html_incrusta_textos_y_logica(html):
    assert "window.Logica" in html or "root.Logica" in html
    assert '"foot"' in html
    assert "{{" not in html  # no quedan marcadores sin sustituir


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_scripts_pasan_node_check(html, tmp_path):
    bloques = re.findall(r"<script(?![^>]*\bsrc=)(?![^>]*type=\"application/json\")[^>]*>(.*?)</script>", html, re.S)
    assert bloques
    for i, b in enumerate(bloques):
        f = tmp_path / f"s{i}.js"
        f.write_text(b, encoding="utf-8")
        r = subprocess.run([NODE, "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_nivel_no_depende_solo_del_color():
    js = ("const L=require('./fuente/web/logica.js');"
          "const r=[];for(const l of ['es','ca']){for(let n=0;n<4;n++)r.push(L.nivelRotulo(n,false,l));r.push(L.nivelRotulo(0,true,l));}"
          "console.log(JSON.stringify(r))")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, cwd=RAIZ)
    rotulos = json.loads(r.stdout)
    assert all(x["simbolo"] and x["texto"] for x in rotulos)
    assert len({x["simbolo"] for x in rotulos}) == 5


def test_la_pagina_pinta_simbolo_junto_al_texto(html):
    assert "nivelRotulo(" in html


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_pruebas_de_logica_js_pasan():
    r = subprocess.run([NODE, "--test", "tests/web/logica.test.js"], capture_output=True, text=True, cwd=RAIZ)
    assert r.returncode == 0, r.stdout[-2000:]
