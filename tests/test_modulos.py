"""Archivos de módulos por río (fuente/paises/<cc>/rios/<id>/) y su copia validada a data/ en el armado del sitio."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "fuente"))

import armar_sitio  # noqa: E402

BARRANQUERAS = RAIZ / "fuente" / "paises" / "ar" / "rios" / "parana-barranqueras"
NODE = shutil.which("node")


def cargar(nombre):
    return json.loads((BARRANQUERAS / nombre).read_text(encoding="utf-8"))


def test_historicos_de_barranqueras_llevan_los_valores_de_pablo():
    d = cargar("historicos.json")
    assert d["estacion"] == "parana-barranqueras" and d["unidad"] == "m"
    assert "Pablo Dodda" in d["fuente"]
    valores = {e["evento"]: e["valor"] for e in d["eventos"]}
    assert valores == {"1983": 8.6, "1992": 8.25, "2013": 7.09, "Tope de las defensas": 9.5}
    assert {e["evento"]: e["tipo"] for e in d["eventos"]}["Tope de las defensas"] == "defensa"
    assert all("nota" in e for e in d["eventos"])
    # el cero de la escala histórica no está comprobado y el archivo lo dice en los tres idiomas
    assert set(d["aviso"]) == {"es", "ca", "en"}
    armar_sitio.validar_historicos(d)


def test_pronostico_manual_de_barranqueras_esta_etiquetado_y_fechado():
    d = cargar("pronostico_manual.json")
    assert d["manual"] is True and d["fecha"] and d["fuente"]
    armar_sitio.validar_pronostico_manual(d)


def test_la_estacion_de_los_archivos_existe_en_el_registro():
    registro = json.loads((RAIZ / "fuente" / "paises" / "ar" / "estaciones.json").read_text(encoding="utf-8"))
    assert "parana-barranqueras" in {e["id"] for e in registro}
    m = [e for e in registro if e["id"] == "parana-barranqueras"][0]
    assert m["unidad"] == "m"


@pytest.mark.parametrize("cambio", [
    lambda d: d.pop("eventos"),
    lambda d: d.update(eventos=[]),
    lambda d: d["eventos"][0].update(valor="8,6"),
    lambda d: d["eventos"][0].update(tipo="otra"),
    lambda d: d["eventos"][0].pop("nota"),
    lambda d: d["eventos"][0].update(nota={"es": "solo castellano"}),
    lambda d: d.update(unidad="furlong"),
    lambda d: d.pop("fuente"),
    lambda d: d.update(aviso={"es": "x"}),
])
def test_historicos_invalidos_se_rechazan(cambio):
    d = cargar("historicos.json")
    cambio(d)
    with pytest.raises(ValueError):
        armar_sitio.validar_historicos(d)


@pytest.mark.parametrize("cambio", [
    lambda d: d.update(manual=False),
    lambda d: d.pop("fecha"),
    lambda d: d.update(fecha="20/10/2026"),
    lambda d: d.update(puntos=[]),
    lambda d: d.update(puntos=[["2026-10-20T12:00:00Z", "6"]]),
    lambda d: d.update(puntos=[["ayer", 6.5]]),
    lambda d: d.update(puntos=[["2026-10-20T12:00:00Z", 7.5, 6.5]]),
    lambda d: d.pop("fuente"),
])
def test_pronostico_manual_invalido_se_rechaza(cambio):
    d = cargar("pronostico_manual.json")
    cambio(d)
    with pytest.raises(ValueError):
        armar_sitio.validar_pronostico_manual(d)


def arbol(tmp_path):
    """Copia mínima del repo: registro de estaciones + archivos de módulos, para probar el armado sin tocar data/."""
    src = tmp_path / "fuente" / "paises"
    for cc in ("ar", "es", "us"):
        (src / cc).mkdir(parents=True)
        shutil.copy(RAIZ / "fuente" / "paises" / cc / "estaciones.json", src / cc / "estaciones.json")
    shutil.copytree(BARRANQUERAS, src / "ar" / "rios" / "parana-barranqueras")
    return src


def test_el_armado_copia_los_modulos_a_data_y_escribe_el_indice(tmp_path):
    src, data = arbol(tmp_path), tmp_path / "data"
    indice = armar_sitio.copiar_modulos(src, data)
    destino = data / "ar" / "rios" / "parana-barranqueras"
    for f in ("historicos.json", "pronostico_manual.json"):
        assert json.loads((destino / f).read_text(encoding="utf-8")) == cargar(f)
    assert indice == {"ar": {"parana-barranqueras": ["historicos", "pronostico_manual"]}, "es": {}, "us": {}}
    for cc, esperado in indice.items():
        assert json.loads((data / cc / "rios" / "modulos.json").read_text(encoding="utf-8")) == esperado


def test_el_armado_no_toca_el_pronostico_del_robot(tmp_path):
    src, data = arbol(tmp_path), tmp_path / "data"
    robot = data / "ar" / "rios" / "parana-barranqueras"
    robot.mkdir(parents=True)
    (robot / "pronostico.json").write_text('{"fuente":"NWS"}', encoding="utf-8")
    armar_sitio.copiar_modulos(src, data)
    assert (robot / "pronostico.json").read_text(encoding="utf-8") == '{"fuente":"NWS"}'


def test_el_armado_retira_copias_cuyo_origen_ya_no_existe(tmp_path):
    src, data = arbol(tmp_path), tmp_path / "data"
    armar_sitio.copiar_modulos(src, data)
    (src / "ar" / "rios" / "parana-barranqueras" / "pronostico_manual.json").unlink()
    indice = armar_sitio.copiar_modulos(src, data)
    assert indice["ar"] == {"parana-barranqueras": ["historicos"]}
    assert not (data / "ar" / "rios" / "parana-barranqueras" / "pronostico_manual.json").exists()


def test_el_armado_rechaza_ids_y_archivos_desconocidos(tmp_path):
    src, data = arbol(tmp_path), tmp_path / "data"
    shutil.copytree(BARRANQUERAS, src / "ar" / "rios" / "no-existe")
    with pytest.raises(ValueError, match="no-existe"):
        armar_sitio.copiar_modulos(src, data)
    shutil.rmtree(src / "ar" / "rios" / "no-existe")
    (src / "ar" / "rios" / "parana-barranqueras" / "pronostico.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="pronostico.json"):
        armar_sitio.copiar_modulos(src, data)  # ese nombre es del robot: un archivo manual no puede suplantarlo


def test_el_armado_rechaza_un_archivo_con_esquema_malo(tmp_path):
    src, data = arbol(tmp_path), tmp_path / "data"
    f = src / "ar" / "rios" / "parana-barranqueras" / "historicos.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["eventos"][0]["valor"] = "mucho"
    f.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="historicos.json"):
        armar_sitio.copiar_modulos(src, data)


def test_en_el_repo_solo_barranqueras_tiene_archivos_de_modulos():
    indice = armar_sitio.indice_modulos(RAIZ / "fuente" / "paises")
    assert indice == {"ar": {"parana-barranqueras": ["historicos", "pronostico_manual"]}, "es": {}, "us": {}}


@pytest.mark.skipif(NODE is None, reason="node no está instalado")
def test_pruebas_de_modulos_js_pasan():
    r = subprocess.run([NODE, "--test", "tests/web/modulos.test.js"], capture_output=True, text=True, cwd=RAIZ)
    assert r.returncode == 0, r.stdout[-2000:]


def test_el_archivo_debe_ser_de_su_estacion_y_su_unidad(tmp_path):
    src, data = arbol(tmp_path), tmp_path / "data"
    f = src / "ar" / "rios" / "parana-barranqueras" / "historicos.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["unidad"] = "ft"
    f.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="unidad"):
        armar_sitio.copiar_modulos(src, data)
    d["unidad"] = "m"
    d["estacion"] = "parana-corrientes"
    f.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="estacion"):
        armar_sitio.copiar_modulos(src, data)
