import json
import pytest

from estaciones import cargar


def _est(**kw):
    base = {
        "id": "llobregat-sant-joan-despi", "rio": "Llobregat", "nombre": "Sant Joan Despí",
        "cuenca": "Llobregat", "fuente": "aca", "muestreo_min": 5, "componente": "082172-002",
        "id_cha": None, "lat": 41.37, "lon": 2.05, "zona": "barcelona",
        "umbrales": {"bajo": 10, "medio": 20, "alto": 40, "tipo": "estimado"},
    }
    base.update(kw)
    return base


def _escribir(tmp_path, estaciones):
    ruta = tmp_path / "estaciones.json"
    ruta.write_text(json.dumps(estaciones), encoding="utf-8")
    return str(ruta)


def test_carga_catalogo_valido(tmp_path):
    chj = _est(id="poyo-n-iii", rio="Poyo", nombre="N-III", cuenca="Júcar", fuente="chj",
               componente=None, id_cha="0O04", zona="valencia", muestreo_min=15,
               umbrales={"bajo": 30, "medio": 70, "alto": 150, "tipo": "oficial"})
    res = cargar(_escribir(tmp_path, [_est(), chj]))
    assert len(res) == 2
    assert res[0].umbrales.tipo == "estimado"
    assert res[1].id_cha == "0O04"


def test_id_repetido_falla(tmp_path):
    with pytest.raises(ValueError, match="repetido"):
        cargar(_escribir(tmp_path, [_est(), _est()]))


def test_aca_sin_componente_falla(tmp_path):
    with pytest.raises(ValueError, match="componente"):
        cargar(_escribir(tmp_path, [_est(componente=None)]))


def test_umbrales_no_crecientes_falla(tmp_path):
    with pytest.raises(ValueError, match="crecientes"):
        cargar(_escribir(tmp_path, [_est(umbrales={"bajo": 20, "medio": 10, "alto": 40, "tipo": "estimado"})]))


def test_umbral_en_estudio_acepta_none(tmp_path):
    res = cargar(_escribir(tmp_path, [_est(umbrales={"bajo": None, "medio": None, "alto": None, "tipo": "en_estudio"})]))
    assert res[0].umbrales.bajo is None
    assert res[0].umbrales.tipo == "en_estudio"


def test_fuente_desconocida_falla(tmp_path):
    with pytest.raises(ValueError, match="fuente"):
        cargar(_escribir(tmp_path, [_est(fuente="otra")]))


def test_chj_sin_id_cha_falla(tmp_path):
    with pytest.raises(ValueError, match="id_cha"):
        cargar(_escribir(tmp_path, [_est(fuente="chj", componente=None, id_cha=None)]))


def test_zona_invalida_falla(tmp_path):
    with pytest.raises(ValueError, match="zona"):
        cargar(_escribir(tmp_path, [_est(zona="luna")]))


def test_tipo_de_umbral_invalido_falla(tmp_path):
    with pytest.raises(ValueError, match="tipo"):
        cargar(_escribir(tmp_path, [_est(umbrales={"bajo": 1, "medio": 2, "alto": 3, "tipo": "raro"})]))
