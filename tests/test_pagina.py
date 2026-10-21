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
    # Paraná, Barranqueras y Río Negro ya son contenido legítimo de la pestaña de Argentina. Lo que no debe aparecer son
    # los restos del sitio original: su dominio, su analítica y su ciudad.
    bajo = html.lower()
    for marca in ("apuratejose", "cloudflare", "clarity", "resistencia"):
        assert marca not in bajo, marca


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
        for desc in [t["desc"], t["region_default"]["desc"]] + [
            p.get("desc", t["region_default"]["desc"]) for p in t["paises"].values()
        ]:
            assert "oficiales" not in desc and "oficials" not in desc and "official" not in desc
            assert "15" not in desc  # se publica cada hora salvo cambios
        assert "Segre" not in t["zonas"]["interior"]
        assert "Segre" in pie(lang) and "Poyo" in pie(lang)  # límites de cobertura y de cuencas rápidas


PAISES = ("ar", "es", "us", "de", "fr", "gb", "it", "nl", "pl", "pt", "hu", "ru",
          "asia", "centroamerica", "sudamerica", "oceania", "africa")
CLAVES_PAIS = ("nombre",)


def test_pagina_tiene_pestanas_accesibles(html):
    assert 'role="tablist"' in html
    assert 'const claves = Object.keys(t().paises)' in html
    assert 'document.createElement("button")' in html
    assert 'b.setAttribute("role", "tab")' in html
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
        for k in ("titulo", "desc", "est_title", "sub", "prev_note", "model_only", "model_only_note", "foot"):
            assert t["region_default"][k], (lang, k)
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
        for k in ("aca", "chj", "ina", "agp", "usgs", "glofas", "avisos", "prevision"):
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
               "Defensa Civil", "Rambla del Poyo", "Río Negro")
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


def test_textos_de_modulos_en_todos_los_idiomas_con_los_mismos_marcadores():
    claves = [k for k in TEXTOS["es"] if k.startswith("mod_")]
    assert len(claves) >= 30
    for lang in IDIOMAS:
        assert [k for k in TEXTOS[lang] if k.startswith("mod_")] == claves
        for k in claves:
            assert TEXTOS[lang][k].strip(), (lang, k)
            assert set(re.findall(r"\{(\w+)\}", TEXTOS[lang][k])) == set(re.findall(r"\{(\w+)\}", TEXTOS["es"][k])), (lang, k)


def test_la_pagina_usa_todas_las_claves_de_modulos():
    plantilla = (RAIZ / "fuente" / "page.html").read_text(encoding="utf-8")
    logica = (RAIZ / "fuente" / "web" / "modulos.js").read_text(encoding="utf-8")
    for k in (k for k in TEXTOS["es"] if k.startswith("mod_")):
        assert k in plantilla or k in logica or re.fullmatch(r"mod_sim_n[0-3]", k), k  # mod_sim_nX lo arma simular()


def test_el_simulador_esta_etiquetado_y_anuncia_su_resultado(html):
    assert re.search(r'<label for="sim-', html)
    assert 'aria-live="polite"' in html and 'class="simout"' in html
    assert 'class="simin"' in html and 'inputmode="decimal"' in html
    assert "aria-describedby" in html  # el gráfico remite a su resumen en texto


def test_el_modulo_historico_depende_del_indice_de_archivos(html):
    # el contenedor solo se pinta si modulos/modulos.json lista historicos para esa estación
    assert 'modulos/modulos.json' in html
    assert 'includes("historicos")' in html and 'data-mod="historicas"' in html
    assert "parana-barranqueras" not in html  # ninguna estación va escrita a mano en la plantilla


def test_los_modulos_usan_d3_local_y_nada_externo(html):
    assert '<script src="d3.min.js"></script>' in html
    assert not re.search(r'<script[^>]+src="https?:', html)
    assert "cdn." not in html and "unpkg" not in html


def test_el_pronostico_no_se_mezcla_con_los_niveles(html):
    # el pronóstico solo se dibuja: la plantilla no lo pasa a nivelRotulo ni toca e.nivel
    assert "e.nivel =" not in html and "nivel:" not in html.split("function elegirPronostico", 1)[1].split("function grafico", 1)[0]


def test_la_pagina_nunca_pide_archivos_manuales_bajo_data():
    # data/ la restaura la caché de Actions: los archivos manuales se sirven desde modulos/
    plantilla = (RAIZ / "fuente" / "page.html").read_text(encoding="utf-8")
    assert '"modulos/modulos.json"' in plantilla and '"modulos/" + p' in plantilla
    assert "rios/modulos.json" not in plantilla
    for m in re.finditer(r"rutaDatos\([^)]*\)", plantilla):
        assert "historicos" not in m.group(0) and "pronostico_manual" not in m.group(0) and "modulos" not in m.group(0), m.group(0)
    # lo único que se pide bajo data/<pais>/rios/ es el pronóstico del robot
    pedidos = re.findall(r'robotDe\("([^"]+)"\)', plantilla)
    assert set(pedidos) == {"pronostico.json"}


# ---------- ficha del Paraná en Barranqueras (T10) ----------
FICHA = TEXTOS["es"]["ficha_barr"]


def test_textos_de_la_ficha_en_todos_los_idiomas_con_los_mismos_marcadores():
    for lang in IDIOMAS:
        t = TEXTOS[lang]["ficha_barr"]
        assert list(t) == list(FICHA), lang
        for k, v in t.items():
            assert v.strip(), (lang, k)
            assert set(re.findall(r"\{(\w+)\}", v)) == set(re.findall(r"\{(\w+)\}", FICHA[k])), (lang, k)


def test_el_modulo_de_la_ficha_usa_todos_sus_textos_y_no_pide_otros():
    js = (RAIZ / "fuente" / "web" / "ficha_barranqueras.js").read_text(encoding="utf-8")
    usados = set(re.findall(r"\bt\.([a-z_0-9]+)", js)) | {"corte_paso_" + str(n) for n in range(4)}
    assert usados <= set(FICHA), usados - set(FICHA)
    dinamicos = {"palabra_abiertas", "palabra_cerradas", "palabra_puede", "estado_abiertas", "estado_cerradas", "estado_puede"}  # se eligen por estado
    assert set(FICHA) <= usados | dinamicos, set(FICHA) - usados
    for k in dinamicos:
        assert f'"{k}"' in js or k in js, k


def test_el_esquema_se_declara_regla_de_la_apa_en_los_tres_idiomas():
    # el dibujo explica la regla; no puede pasar por el estado real de las compuertas
    esperado = {"es": ("regla de la APA", "no recibe el estado real"), "ca": ("regla de l'APA", "no rep l'estat real"), "en": ("APA rule", "does not receive the real state")}
    for lang, (regla, real) in esperado.items():
        t = TEXTOS[lang]["ficha_barr"]
        assert regla in t["regla_chip"] and regla in t["esquema_h"] and real in t["esquema_aviso"], lang
        assert "{palabra}" in t["regla_chip"]
    for lang in IDIOMAS:  # nada de «las compuertas están cerradas» sin la regla delante
        t = TEXTOS[lang]["ficha_barr"]
        for k in ("estado_abiertas", "estado_puede", "estado_cerradas"):
            assert re.search(r"APA", t[k]), (lang, k)


def test_el_corte_se_declara_ejemplo_en_los_tres_idiomas():
    for lang, palabra in {"es": "ejemplo", "ca": "exemple", "en": "example"}.items():
        t = TEXTOS[lang]["ficha_barr"]
        assert palabra in t["corte_aviso"].lower() and palabra in t["corte_lbl_parana"].lower() and palabra in t["corte_lbl_rn"].lower(), lang


def test_la_pagina_carga_la_ficha_solo_si_el_indice_la_pide(html):
    # ninguna estación escrita en la plantilla: el índice de módulos (ficha.json) dice qué estación lleva ficha y cuál
    assert 'includes("ficha")' in html and 'manualDe("ficha.json")' in html
    assert '"modulos/ficha_" + nombre + ".js"' in html
    assert "parana-barranqueras" not in html
    assert re.search(r'<script[^>]*src="[^"]*ficha', html) is None  # no va en la carga inicial
    assert "document.createElement(\"script\")" in html
    assert "[data-ficha]" in html and "window[\"Ficha\"" in html


def test_la_ficha_no_anima_si_la_persona_pide_menos_movimiento(html):
    css = html.split("<style>", 1)[1].split("</style>", 1)[0]
    ficha = css.split("Ficha especial del Paraná", 1)[1]
    fuera = re.sub(r"@media \(prefers-reduced-motion: no-preference\) \{.*?\n\}\n", "", ficha, flags=re.S)
    for marca in ("transition", "animation", "@keyframes"):
        assert marca not in fuera, marca
    assert "transition" in ficha and "animation" in ficha  # sí hay movimiento, pero solo dentro del permiso
    assert "prefers-reduced-motion: no-preference" in css


def test_el_svg_de_la_ficha_tiene_alternativa_en_texto():
    js = (RAIZ / "fuente" / "web" / "ficha_barranqueras.js").read_text(encoding="utf-8")
    assert 'role="img" aria-describedby="fb-desc"' in js and 'id="fb-desc"' in js
    assert 'aria-label="${esc(t.corte_desc)}"' in js and 'aria-live="polite"' in js


def test_la_ficha_sigue_citando_a_pablo_en_el_pie():
    for lang in IDIOMAS:
        assert "Pablo Dodda" in " ".join(TEXTOS[lang]["foot"])
