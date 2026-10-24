from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

RUTA = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "actualizar.yml"


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(RUTA.read_text(encoding="utf-8"))


def pasos(wf):
    return wf["jobs"]["actualizar"]["steps"]


def test_disparadores_cron_15_min_y_manual(wf):
    on = wf.get(True, wf.get("on"))  # PyYAML lee `on:` como True
    assert on["schedule"][0]["cron"] == "*/15 * * * *"
    assert "workflow_dispatch" in on


def test_permisos_minimos_y_sin_cancelar_ejecuciones(wf):
    assert wf["permissions"] == {"contents": "write", "issues": "write"}
    assert wf["concurrency"] == {"group": "actualizar-datos-multipais", "cancel-in-progress": False}


def test_los_pasos_de_red_tienen_timeout(wf):
    nombres = {p.get("id") or p.get("name"): p for p in pasos(wf)}
    for clave in ("actualizar", "publicar", "notificar"):
        assert "timeout-minutes" in nombres[clave], clave


def test_el_estado_se_conserva_entre_ejecuciones_sin_commit(wf):
    """Sin esto, los contadores de histéresis se pierden cuando no se publica y la subida a N1/N2 nunca se confirma."""
    usos = [p.get("uses", "") for p in pasos(wf)]
    assert any(u.startswith("actions/cache/restore@") for u in usos)
    assert any(u.startswith("actions/cache/save@") for u in usos)


def test_solo_se_hace_commit_de_data(wf):
    texto = RUTA.read_text(encoding="utf-8")
    assert "git add data" in texto
    assert "git add ." not in texto and "git add -A" not in texto


def test_nunca_usa_force_push(wf):
    assert "--force" not in RUTA.read_text(encoding="utf-8")


def test_notificar_corre_aunque_falle_la_publicacion(wf):
    """Si el push falla, el estado ya está en la caché: sin always() el aviso se perdería para siempre."""
    paso = next(p for p in pasos(wf) if p.get("id") == "notificar")
    assert "always()" in paso["if"]


def test_git_add_data_cubre_las_carpetas_por_pais(wf):
    """`git add data` incluye data/<pais>/ y data/paises.json; no hace falta listar países en el workflow."""
    texto = RUTA.read_text(encoding="utf-8")
    assert "git add data\n" in texto


def test_cache_con_prefijo_v2_para_no_resucitar_el_formato_plano(wf):
    """El caché antiguo (data-*) tiene data/*.json planos; extraído junto a data/es/ se commitearía."""
    restaurar = next(p for p in pasos(wf) if p.get("uses", "").startswith("actions/cache/restore@"))
    guardar = next(p for p in pasos(wf) if p.get("uses", "").startswith("actions/cache/save@"))
    assert restaurar["with"]["restore-keys"].strip().startswith("data-v2-")
    assert restaurar["with"]["key"].startswith("data-v2-")
    assert guardar["with"]["key"].startswith("data-v2-")


def test_actualizacion_manual_permite_seleccionar_pais_y_rio(wf):
    on = wf.get(True, wf.get("on"))
    inputs = on["workflow_dispatch"]["inputs"]
    assert inputs["pais"]["default"] == "todos"
    assert inputs["rio"]["default"] == "todos"
    paso = next(p for p in pasos(wf) if p.get("id") == "actualizar")
    assert paso["env"]["PAIS"] == "${{ inputs.pais || 'todos' }}"
    assert paso["env"]["RIO"] == "${{ inputs.rio || 'todos' }}"
    assert paso["run"] == 'python fuente/actualizar.py --pais "$PAIS" --rio "$RIO"'
