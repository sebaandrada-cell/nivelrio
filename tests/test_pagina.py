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
    # Paraná y Barranqueras ya son contenido legítimo de la pestaña de Argentina; el resto sigue sin aparecer.
    for marca in ("Resistencia", "apuratejose", "Río Negro"):
        assert marca not in html


def pie(lang, pais="es"):
    return " ".join(TEXTOS[lang]["foot"] + TEXTOS[lang]["paises"][pais]["foot"])


def test_pie_en_todos_los_idiomas():
    for lang in IDIOMAS:
        assert "Protecció Civil" in pie(lang)


IDIOMAS = ("es", "ca", "en")


def test_es_ca_y_en_tienen_las_mismas_claves():
    assert forma(TEXTOS["es"]) == forma(TEXTOS["ca"]) == forma(TEXTOS["en"])
    for k in ("tile_desc", "foot", "fuentes_nombres", "zonas", "paises"):
        assert k in TEXTOS["en"], k


def test_creditos_incluyen_a_ambos_autores():
    for lang in IDIOMAS:
        general = " ".join(TEXTOS[lang]["foot"])
        assert "Pablo Dodda" in general and "Sebastian Andrada" in general


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


def test_textos_no_prometen_mas_de_lo_que_hay():
    for lang in IDIOMAS:
        t = TEXTOS[lang]
        for desc in [t["desc"]] + [p["desc"] for p in t["paises"].values()]:
            assert "oficiales" not in desc and "oficials" not in desc and "official" not in desc
            assert "15" not in desc  # se publica cada hora salvo cambios
        assert "Segre" not in t["zonas"]["interior"]
        assert "Segre" in pie(lang) and "Poyo" in pie(lang)  # límites de cobertura y de cuencas rápidas


PAISES = ("ar", "es", "us")
CLAVES_PAIS = ("nombre", "titulo", "desc", "sub", "prev_note", "foot")


def test_pagina_tiene_pestanas_accesibles(html):
    assert 'role="tablist"' in html
    for p in PAISES:
        assert re.search(rf'<button[^>]*role="tab"[^>]*data-p="{p}"|<button[^>]*data-p="{p}"[^>]*role="tab"', html), p
    assert 'role="tabpanel"' in html
    assert "aria-selected" in html


def test_pagina_lee_los_datos_por_pais(html):
    assert "rutaDatos(" in html and "data/paises.json" in html
    for vieja in ('"data/latest.json"', '"data/prevision.json"', '"data/history/"'):
        assert vieja not in html


def test_textos_nuevos_en_todos_los_idiomas():
    for lang in IDIOMAS:
        t = TEXTOS[lang]
        for k in ("pais_sin_datos", "pais_desconocido", "tab_label"):
            assert t[k], (lang, k)
        assert set(t["paises"]) == set(PAISES)
        for p in PAISES:
            for k in CLAVES_PAIS:
                assert t["paises"][p][k], (lang, p, k)


def test_cada_zona_de_cada_pais_tiene_texto():
    for p in PAISES:
        registro = json.loads((RAIZ / "fuente" / "paises" / p / "estaciones.json").read_text(encoding="utf-8"))
        for e in registro:
            for lang in IDIOMAS:
                assert TEXTOS[lang]["zonas"].get(e["zona"]), (lang, p, e["zona"])


def test_cada_fuente_de_datos_tiene_nombre_para_el_aviso_de_caida():
    for lang in IDIOMAS:
        for k in ("aca", "chj", "ina", "agp", "usgs", "avisos", "prevision"):
            assert TEXTOS[lang]["fuentes_nombres"][k], (lang, k)


def _hojas(x, ruta=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _hojas(v, f"{ruta}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _hojas(v, f"{ruta}[{i}]")
    else:
        yield ruta, x


# Claves que pueden coincidir con el castellano porque son nombres propios, siglas o cifras.
def test_el_ingles_esta_traducido_de_verdad():
    es = dict(_hojas(TEXTOS["es"]))
    en = dict(_hojas(TEXTOS["en"]))
    assert set(es) == set(en)
    iguales = [k for k in es if es[k] == en[k]]
    distintas = len(es) - len(iguales)
    assert distintas / len(es) >= 0.9, iguales
    # lo que queda igual tiene que ser un nombre propio, una sigla o una cifra
    for k in iguales:
        assert not re.search(r"[a-záéíóúñ]{4,} [a-záéíóúñ]{3,}", es[k].replace("Red River of the North", "")), (k, es[k])


def test_el_ingles_no_arrastra_palabras_del_castellano():
    propios = ("Instituto Nacional del Agua", "Administración General de Puertos", "Administración Provincial del Agua del Chaco",
               "Confederación Hidrográfica del Júcar", "Agència Catalana de l'Aigua", "Protecció Civil de Catalunya", "Protecció Civil",
               "Defensa Civil", "Rambla del Poyo")
    palabras = re.compile(r"\b(el|los|las|del|para|con|una|por|que|sin|más|ríos?|caudal|nivel(?:es)?|aviso|peligro|hace|datos)\b", re.I)
    for ruta, v in _hojas(TEXTOS["en"]):
        texto = re.sub(r"<[^>]+>", "", str(v))
        for nombre in propios:
            texto = texto.replace(nombre, "")
        # «Nivel» no aparece en inglés; «Aviso» tampoco, salvo dentro de un nombre propio
        m = palabras.search(texto)
        assert not m, (ruta, m.group(0), texto)


def test_el_ingles_evita_las_muletillas_de_texto_generado():
    prohibidas = ("seamless", "leverage", "robust", "delve", "tapestry", "landscape", "cutting-edge",
                  "empower", "elevate", "unlock", "ensure", "comprehensive", "—")
    for ruta, v in _hojas(TEXTOS["en"]):
        baja = str(v).lower()
        for w in prohibidas:
            assert w not in baja, (ruta, w)


def test_el_ingles_usa_ortografia_de_ee_uu():
    for ruta, v in _hojas(TEXTOS["en"]):
        for w in ("colour", "metre", "kilometre", "centre", "organis"):
            assert w not in str(v).lower(), (ruta, w)


def test_selector_de_idioma_tiene_tres_opciones(html):
    bloque = re.search(r'<div class="seg" id="lang".*?</div>', html, re.S).group(0)
    assert set(re.findall(r'data-l="(\w+)"', bloque)) == {"es", "ca", "en"}


def test_la_pagina_formatea_valores_con_una_sola_funcion(html):
    # un único punto de formato por unidad: ni toFixed de valores de río ni «m³/s» a mano en la plantilla
    plantilla = (RAIZ / "fuente" / "page.html").read_text(encoding="utf-8")
    assert "m³/s" not in plantilla
    assert '" mm"' not in plantilla and " mm<" not in plantilla
    assert "formatoValor(" in plantilla
    assert 'lang === "ca" ? "ca-ES"' not in plantilla  # los idiomas salen de localeDe


def test_los_ejes_de_los_graficos_usan_el_formato_del_idioma():
    plantilla = (RAIZ / "fuente" / "page.html").read_text(encoding="utf-8")
    assert ".text((d) => d)" not in plantilla  # una marca de eje sin formato sale con punto en es/ca
    assert ".text((d) => num(d))" in plantilla


def test_umbrales_sin_unidad_se_tratan_como_caudal():
    plantilla = (RAIZ / "fuente" / "page.html").read_text(encoding="utf-8")
    assert 'val(u.alto, unidad || "m3s")' in plantilla
