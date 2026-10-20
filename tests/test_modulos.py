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


def test_el_armado_copia_los_modulos_fuera_de_data_y_escribe_el_indice(tmp_path):
    src, destino = arbol(tmp_path), tmp_path / "modulos"
    indice = armar_sitio.copiar_modulos(src, destino)
    carpeta = destino / "ar" / "parana-barranqueras"
    for f in ("historicos.json", "pronostico_manual.json"):
        assert json.loads((carpeta / f).read_text(encoding="utf-8")) == cargar(f)
    esperado = {"ar": {"parana-barranqueras": ["historicos", "pronostico_manual"]}, "es": {}, "us": {}}
    assert indice == esperado
    assert json.loads((destino / "modulos.json").read_text(encoding="utf-8")) == esperado


def test_el_armado_escribe_en_modulos_y_no_en_data():
    # el destino por defecto de main() cuelga de la raíz del sitio y no de data/ (la caché de Actions restaura data/)
    fuente = (RAIZ / "fuente" / "armar_sitio.py").read_text(encoding="utf-8")
    assert 'os.path.join(RAIZ, "modulos")' in fuente
    assert 'os.path.join(RAIZ, "data")' not in fuente
    assert not list((RAIZ / "data").rglob("historicos.json")) and not list((RAIZ / "data").rglob("pronostico_manual.json"))
    assert not list((RAIZ / "data").rglob("modulos.json"))
    assert (RAIZ / "modulos" / "modulos.json").is_file()
    assert (RAIZ / "modulos" / "ar" / "parana-barranqueras" / "historicos.json").is_file()


def test_el_armado_no_toca_data_ni_el_pronostico_del_robot(tmp_path):
    src, destino = arbol(tmp_path), tmp_path / "modulos"
    robot = tmp_path / "data" / "ar" / "rios" / "parana-barranqueras"
    robot.mkdir(parents=True)
    (robot / "pronostico.json").write_text('{"fuente":"NWS"}', encoding="utf-8")
    armar_sitio.copiar_modulos(src, destino)
    assert sorted(p.name for p in robot.iterdir()) == ["pronostico.json"]
    assert (robot / "pronostico.json").read_text(encoding="utf-8") == '{"fuente":"NWS"}'


def test_el_armado_retira_copias_cuyo_origen_ya_no_existe(tmp_path):
    src, destino = arbol(tmp_path), tmp_path / "modulos"
    armar_sitio.copiar_modulos(src, destino)
    (src / "ar" / "rios" / "parana-barranqueras" / "pronostico_manual.json").unlink()
    indice = armar_sitio.copiar_modulos(src, destino)
    assert indice["ar"] == {"parana-barranqueras": ["historicos"]}
    assert not (destino / "ar" / "parana-barranqueras" / "pronostico_manual.json").exists()
    shutil.rmtree(src / "ar" / "rios")
    armar_sitio.copiar_modulos(src, destino)
    assert not (destino / "ar").exists()  # sin archivos de origen no queda ni la carpeta
    assert json.loads((destino / "modulos.json").read_text(encoding="utf-8")) == {"ar": {}, "es": {}, "us": {}}


def test_el_armado_rechaza_ids_y_archivos_desconocidos(tmp_path):
    src, data = arbol(tmp_path), tmp_path / "modulos"
    shutil.copytree(BARRANQUERAS, src / "ar" / "rios" / "no-existe")
    with pytest.raises(ValueError, match="no-existe"):
        armar_sitio.copiar_modulos(src, data)
    shutil.rmtree(src / "ar" / "rios" / "no-existe")
    (src / "ar" / "rios" / "parana-barranqueras" / "pronostico.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="pronostico.json"):
        armar_sitio.copiar_modulos(src, data)  # ese nombre es del robot: un archivo manual no puede suplantarlo


def test_el_armado_rechaza_un_archivo_con_esquema_malo(tmp_path):
    src, data = arbol(tmp_path), tmp_path / "modulos"
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
    src, data = arbol(tmp_path), tmp_path / "modulos"
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


def test_pronostico_manual_de_barranqueras_dice_de_donde_sale_y_cuando_se_emitio():
    # Según situacion.json de Pablo: pronóstico del INA emitido el 13 de octubre para el 20. El punto del 27 de octubre
    # no tiene origen declarado y no se incluye.
    d = cargar("pronostico_manual.json")
    assert d["fecha"] == "2026-10-13"
    assert "INA" in d["fuente"] and "13 de octubre" in d["fuente"] and d["fuente"].strip()
    assert "APA" not in d["fuente"].split("según")[0]
    assert [p[0][:10] for p in d["puntos"]] == ["2026-10-20"]
    assert d["puntos"][0][1:] == [6.75, 7.55]
