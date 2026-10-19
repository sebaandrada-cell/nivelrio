from datetime import date, timedelta

import pytest

from umbrales import emparejar_por_utm, estimar


def serie_sintetica(anios, dias_por_anio=365, base=0.5):
    """Un máximo anual conocido: el año k (1, 2, ...) tiene un pico de valor k."""
    filas = []
    for k, anio in enumerate(anios, start=1):
        for d in range(dias_por_anio):
            filas.append((date(anio, 1, 1) + timedelta(days=d), base))
        filas[-dias_por_anio + 100] = (filas[-dias_por_anio + 100][0], float(k))
    return filas


def test_estimar_serie_sintetica():
    u = estimar(serie_sintetica(range(2000, 2020)))  # máximos anuales 1..20
    assert u.bajo == pytest.approx(10.5)
    assert u.medio == pytest.approx(16.2)
    assert u.alto == pytest.approx(19.05)
    assert u.bajo < u.medio < u.alto


def test_menos_de_cinco_anios_falla():
    with pytest.raises(ValueError, match="5 años"):
        estimar(serie_sintetica(range(2000, 2004)))


def test_anio_incompleto_no_cuenta():
    # 4 años completos y uno con 100 días: no llegan a 5 años completos
    serie = serie_sintetica(range(2000, 2004)) + serie_sintetica([2010], dias_por_anio=100)
    with pytest.raises(ValueError, match="5 años"):
        estimar(serie)


def test_resultado_es_estimado():
    assert estimar(serie_sintetica(range(2000, 2020))).tipo == "estimado"


def test_serie_plana_no_da_umbrales_crecientes():
    plana = [(d, 1.0) for d, _ in serie_sintetica(range(2000, 2010))]
    with pytest.raises(ValueError, match="crecientes"):
        estimar(plana)


def test_emparejar_elige_la_mas_cercana_dentro_del_radio():
    cand = [{"codi_estacio": "A", "utm_x": 1000, "utm_y": 1000}, {"codi_estacio": "B", "utm_x": 1030, "utm_y": 1040}]
    assert emparejar_por_utm((1032, 1038), cand)["codi_estacio"] == "B"


def test_emparejar_fuera_del_radio_es_none():
    assert emparejar_por_utm((0, 0), [{"codi_estacio": "A", "utm_x": 1000, "utm_y": 1000}]) is None
