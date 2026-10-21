import json
import pytest

from estaciones import cargar


def _est(**kw):
    base = {
        "id": "llobregat-sant-joan-despi", "rio": "Llobregat", "nombre": "Sant Joan Despí",
        "cuenca": "Llobregat", "fuente": "aca", "muestreo_min": 5, "componente": "082172-002",
        "id_cha": None, "lat": 41.37, "lon": 2.05, "zona": "barcelona",
        "umbrales": {"bajo": 10, "medio": 20, "alto": 40, "tipo": "estimado"},
        "pais": "es", "magnitud": "caudal", "unidad": "m3s",
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
    res = cargar(_escribir(tmp_path, [_est(), chj]), "es")
    assert len(res) == 2
    assert res[0].umbrales.tipo == "estimado"
    assert res[1].id_cha == "0O04"


def test_id_repetido_falla(tmp_path):
    with pytest.raises(ValueError, match="repetido"):
        cargar(_escribir(tmp_path, [_est(), _est()]), "es")


def test_aca_sin_componente_falla(tmp_path):
    with pytest.raises(ValueError, match="componente"):
        cargar(_escribir(tmp_path, [_est(componente=None)]), "es")


def test_umbrales_no_crecientes_falla(tmp_path):
    with pytest.raises(ValueError, match="crecientes"):
        cargar(_escribir(tmp_path, [_est(umbrales={"bajo": 20, "medio": 10, "alto": 40, "tipo": "estimado"})]), "es")


def test_umbral_en_estudio_acepta_none(tmp_path):
    res = cargar(_escribir(tmp_path, [_est(umbrales={"bajo": None, "medio": None, "alto": None, "tipo": "en_estudio"})]), "es")
    assert res[0].umbrales.bajo is None
    assert res[0].umbrales.tipo == "en_estudio"


def test_fuente_desconocida_falla(tmp_path):
    with pytest.raises(ValueError, match="fuente"):
        cargar(_escribir(tmp_path, [_est(fuente="otra")]), "es")


def test_chj_sin_id_cha_falla(tmp_path):
    with pytest.raises(ValueError, match="id_cha"):
        cargar(_escribir(tmp_path, [_est(fuente="chj", componente=None, id_cha=None)]), "es")


def test_zona_invalida_falla(tmp_path):
    with pytest.raises(ValueError, match="zona"):
        cargar(_escribir(tmp_path, [_est(zona="luna")]), "es")


def test_tipo_de_umbral_invalido_falla(tmp_path):
    with pytest.raises(ValueError, match="tipo"):
        cargar(_escribir(tmp_path, [_est(umbrales={"bajo": 1, "medio": 2, "alto": 3, "tipo": "raro"})]), "es")


def test_cargar_exige_pais_y_zona_del_pais(tmp_path):
    with pytest.raises(ValueError, match="zona"):
        cargar(_escribir(tmp_path, [_est(zona="mississippi")]), "es")
    with pytest.raises(ValueError, match="zona"):
        cargar(_escribir(tmp_path, [_est(pais="us")]), "us")
    with pytest.raises(ValueError, match="país"):
        cargar(_escribir(tmp_path, [_est()]), "fr")
    ar = _est(fuente="ina", componente=None, zona="uruguay", unidad="m", magnitud="altura", pais="ar")
    with pytest.raises(ValueError, match="ref"):
        cargar(_escribir(tmp_path, [ar]), "ar")
    assert cargar(_escribir(tmp_path, [dict(ar, ref="12")]), "ar")[0].ref == "12"
    agp = dict(ar, fuente="agp")
    with pytest.raises(ValueError, match="ref"):
        cargar(_escribir(tmp_path, [agp]), "ar")
    us = _est(fuente="usgs", componente=None, zona="mississippi", unidad="ft", magnitud="altura", pais="us")
    with pytest.raises(ValueError, match="ref"):
        cargar(_escribir(tmp_path, [dict(us, lid="MEMT1")]), "us")
    sin_lid = cargar(_escribir(tmp_path, [dict(us, ref="07032000")]), "us")[0]
    assert sin_lid.ref == "07032000" and sin_lid.lid is None
    ok = cargar(_escribir(tmp_path, [dict(us, ref="07032000", lid="MEMT1")]), "us")[0]
    assert (ok.ref, ok.lid, ok.pais) == ("07032000", "MEMT1", "us")
    with pytest.raises(ValueError, match="magnitud"):
        cargar(_escribir(tmp_path, [_est(magnitud="volumen")]), "es")
    with pytest.raises(ValueError, match="unidad"):
        cargar(_escribir(tmp_path, [_est(unidad="km")]), "es")
    with pytest.raises(ValueError, match="país"):
        cargar(_escribir(tmp_path, [_est(pais="ar")]), "es")


def test_registro_es_conserva_32_estaciones_de_observacion_y_ebro_modelado():
    import os
    ruta = os.path.join(os.path.dirname(__file__), "..", "fuente", "paises", "es", "estaciones.json")
    res = cargar(ruta, "es")
    assert len(res) == 33
    observadas = [e for e in res if e.fuente != "glofas"]
    ebro = [e for e in res if e.fuente == "glofas"]
    assert len(observadas) == 32
    assert all(e.unidad == "m3s" and e.magnitud == "caudal" and e.pais == "es" for e in observadas)
    assert len(ebro) == 1 and ebro[0].rio == "Ebro" and ebro[0].umbrales.tipo == "en_estudio"
