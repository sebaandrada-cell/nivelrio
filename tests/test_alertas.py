import json
from dataclasses import replace
from datetime import timedelta

import pytest

from alertas import ESTADO_INICIAL, VEL_SUBIDA_RAPIDA, Estado, estado_a_dict, estado_desde_dict, evaluar
from conftest import make_estacion, utc
from modelo import Lectura, Umbrales

T0 = utc(2026, 10, 19, 12, 0)
ACA = make_estacion(id="a", fuente="aca", muestreo_min=5)  # umbrales 10/20/40


def correr(valores, est=ACA, prev=ESTADO_INICIAL, paso_min=5, inicio=T0, unidad="m3s"):
    """Aplica evaluar a una serie de lecturas frescas. Devuelve la lista de estados."""
    estados = []
    for i, v in enumerate(valores):
        t = inicio + timedelta(minutes=paso_min * i)
        prev = evaluar(prev, Lectura(est.id, v, unidad, t, est.fuente), est, ahora=t)
        estados.append(prev)
    return estados


def niveles(estados):
    return [e.nivel for e in estados]


def desde_nivel(n, ultimo=None):
    return replace(ESTADO_INICIAL, nivel=n, nivel_propio=n, ultimo_valor=ultimo)


def test_subida_lenta_pasa_por_n1_con_dos_lecturas():
    assert niveles(correr([9, 11, 12])) == [0, 0, 1]


def test_pico_de_una_lectura_escala_si_es_rapido():
    # subida de 13 >= 0,25 * umbral bajo (2,5)
    assert VEL_SUBIDA_RAPIDA == 0.25
    assert niveles(correr([1, 14])) == [0, 1]


def test_primera_lectura_extrema_escala_de_inmediato():
    # sin historial no hay con qué confirmar; mostrar es más seguro que esperar 15 minutos
    assert niveles(correr([50])) == [3]


def test_n2_no_se_alcanza_con_caudal_bajando():
    assert niveles(correr([28, 26, 24], prev=desde_nivel(1, ultimo=30))) == [1, 1, 1]


def test_n2_se_alcanza_subiendo_con_dos_lecturas():
    assert niveles(correr([21, 22, 23], prev=desde_nivel(1, ultimo=20))) == [1, 2, 2]


def test_n3_por_umbral_alto_sin_exigir_tendencia():
    assert niveles(correr([41, 42], prev=desde_nivel(2, ultimo=45))) == [2, 3]


def test_oscilacion_en_el_umbral_no_parpadea():
    # el 85 % de 10 es 8,5: 9 no baja el nivel
    assert niveles(correr([11, 9, 11, 9, 11, 9], prev=desde_nivel(1, ultimo=11))) == [1] * 6


def test_entre_el_85_y_el_100_por_ciento_el_nivel_se_mantiene():
    assert niveles(correr([9] * 8, prev=desde_nivel(1, ultimo=9))) == [1] * 8


def test_bajada_escalonada():
    # 30 queda bajo el 85 % del umbral alto (34): tras 3 lecturas baja a N2 y ahí se queda (30 > 17)
    estados = niveles(correr([30] * 7, prev=desde_nivel(3, ultimo=30)))
    assert estados == [3, 3, 2, 2, 2, 2, 2]
    assert 0 not in estados


def test_una_lectura_sobre_el_85_reinicia_la_cuenta_de_bajada():
    assert niveles(correr([30, 30, 36, 30, 30, 30], prev=desde_nivel(3, ultimo=30))) == [3, 3, 3, 3, 3, 2]


def test_bajada_por_tiempo_tres_horas():
    estados = correr([5, 5], prev=desde_nivel(1, ultimo=5), paso_min=181)
    assert niveles(estados) == [1, 0]


def test_misma_lectura_dos_veces_no_cuenta_doble():
    # el cron corre cada 15 min y el sensor publica cada 5: la misma lectura puede verse dos veces
    prev = replace(ESTADO_INICIAL, ultimo_valor=9.0, ultimo_t_utc=T0 - timedelta(minutes=5))
    lec = Lectura("a", 11, "m3s", T0, "aca")
    e1 = evaluar(prev, lec, ACA, T0 + timedelta(minutes=1))
    e2 = evaluar(e1, lec, ACA, T0 + timedelta(minutes=10))
    assert (e1.nivel, e1.cnt_sobre) == (0, 1)
    assert (e2.nivel, e2.cnt_sobre) == (0, 1)


def test_sd_en_n3_mantiene_alerta():
    prev = replace(desde_nivel(3, ultimo=55), ultimo_t_utc=T0 - timedelta(minutes=60))
    lec = Lectura("a", 55, "m3s", T0, "aca")
    e = evaluar(prev, lec, ACA, T0 + timedelta(minutes=40))
    assert e.sd and e.nivel == 3 and e.ultimo_valor == 55


def test_sin_lectura_es_sd_y_conserva_nivel():
    e = evaluar(desde_nivel(2, ultimo=25), None, ACA, T0)
    assert e.sd and e.nivel == 2 and e.ultimo_valor == 25


def test_aviso_rojo_con_sd_escala_a_n3():
    e = evaluar(ESTADO_INICIAL, None, ACA, T0, aviso_rojo=True)
    assert (e.sd, e.nivel, e.elevado_por_aviso) == (True, 3, True)


def test_aviso_rojo_termina_y_vuelve_al_nivel_propio():
    lec = Lectura("a", 3, "m3s", T0, "aca")
    e1 = evaluar(desde_nivel(1, ultimo=3), lec, ACA, T0, aviso_rojo=True)
    assert (e1.nivel, e1.elevado_por_aviso) == (3, True)
    lec2 = Lectura("a", 3, "m3s", T0 + timedelta(minutes=5), "aca")
    e2 = evaluar(e1, lec2, ACA, T0 + timedelta(minutes=5), aviso_rojo=False)
    assert (e2.nivel, e2.elevado_por_aviso) == (1, False)


def test_timestamp_futuro_es_sd():
    # punto ciego 2: reloj de la fuente adelantado
    lec = Lectura("a", 5, "m3s", T0 + timedelta(minutes=10), "aca")
    e = evaluar(ESTADO_INICIAL, lec, ACA, T0)
    assert e.sd


def test_umbrales_none_nunca_alertan():
    est = make_estacion(umbrales=Umbrales(None, None, None, "en_estudio"))
    estados = correr([1000, 1000, 1000], est=est)
    assert niveles(estados) == [0, 0, 0] and not any(e.sd for e in estados)


def test_lectura_en_cm_se_trata_como_sin_datos():
    # los umbrales están en m3/s: comparar centímetros contra ellos no tiene sentido
    e = correr([500], unidad="cm", prev=desde_nivel(2, ultimo=25))[0]
    assert e.sd and e.nivel == 2


@pytest.mark.parametrize("edad_min,esperado", [(24, False), (25, False), (26, True)])
def test_chj_sd_a_los_26_minutos_y_no_a_los_24(edad_min, esperado):
    chj = make_estacion(id="c", fuente="chj", componente=None, id_cha="0O04", muestreo_min=15)
    lec = Lectura("c", 1, "m3s", T0, "chj")
    assert evaluar(ESTADO_INICIAL, lec, chj, T0 + timedelta(minutes=edad_min)).sd is esperado


@pytest.mark.parametrize("edad_min,esperado", [(15, False), (16, True)])
def test_aca_limite_son_tres_muestreos(edad_min, esperado):
    lec = Lectura("a", 1, "m3s", T0, "aca")
    assert evaluar(ESTADO_INICIAL, lec, ACA, T0 + timedelta(minutes=edad_min)).sd is esperado


def test_estado_ida_y_vuelta_a_dict():
    e = Estado(nivel=3, sd=True, ultimo_valor=41.5, ultimo_t_utc=T0, cnt_sobre=1, cnt_bajo=2,
               bajo_desde=T0 + timedelta(minutes=5), elevado_por_aviso=True, nivel_propio=2)
    d = estado_a_dict(e)
    assert json.loads(json.dumps(d)) == d
    assert d["ultimo_t_utc"] == "2026-10-19T12:00:00Z"
    assert estado_desde_dict(d) == e
    assert estado_desde_dict(estado_a_dict(ESTADO_INICIAL)) == ESTADO_INICIAL
