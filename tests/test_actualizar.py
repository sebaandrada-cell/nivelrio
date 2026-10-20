import json
import os
from datetime import timedelta

import pytest

import actualizar
from conftest import make_estacion, utc
from modelo import Aviso, FuenteError, Lectura, Umbrales

AHORA = utc(2026, 10, 19, 20, 20)
HORA_EN_PUNTO = utc(2026, 10, 19, 20, 5)


def est_aca(**kw):
    return make_estacion(id=kw.pop("id", "a1"), **kw)


def est_chj(**kw):
    base = dict(id="c1", fuente="chj", componente=None, id_cha="X1", zona="valencia",
                umbrales=Umbrales(10.0, 20.0, 40.0, "oficial"))
    base.update(kw)
    return make_estacion(**base)


def lec(id_, valor, ahora=AHORA, minutos=5, unidad="m3s", fuente="aca"):
    return Lectura(id_, valor, unidad, ahora - timedelta(minutes=minutos), fuente)


def fuentes(aca=(), chj=(), avisos=(), prevision=None, ventana=None, chj_umbrales=None):
    def f_aca(ests):
        if isinstance(aca, Exception):
            raise aca
        return list(aca), {}

    def f_chj(ests):
        if isinstance(chj, Exception):
            raise chj
        return list(chj), dict(chj_umbrales or {})

    def f_avisos():
        if isinstance(avisos, Exception):
            raise avisos
        return list(avisos)

    def f_prev(ests):
        if isinstance(prevision, Exception):
            raise prevision
        return prevision if prevision is not None else {}

    return {"aca": f_aca, "chj": f_chj, "avisos": f_avisos, "prevision": f_prev,
            "aca_ventana": ventana or (lambda est, desde, hasta: [])}


def leer(d, nombre):
    return json.loads((d / nombre).read_text(encoding="utf-8"))


def latest(d):
    return {e["id"]: e for e in leer(d, "latest.json")["estaciones"]}


def correr(d, ests, f, ahora=AHORA):
    return actualizar.ejecutar(ahora, ests, f, str(d))


# ---- niveles y cambios ----

def test_cambio_de_nivel_se_reporta(tmp_path):
    ests = [est_aca()]
    cambios = correr(tmp_path, ests, fuentes(aca=[lec("a1", 25.0)]))
    assert cambios == [{"estacion_id": "a1", "nivel_antes": 0, "nivel_despues": 1, "sd": False, "elevado_por_aviso": False}]
    assert latest(tmp_path)["a1"]["nivel"] == 1


def test_primera_ejecucion_en_calma_no_reporta_nada(tmp_path):
    ests = [est_aca(), est_chj()]
    assert correr(tmp_path, ests, fuentes(aca=[lec("a1", 3.0)])) == []  # c1 sin dato: SD, pero es la línea base


def test_paso_a_sd_se_reporta(tmp_path):
    ests = [est_chj()]
    correr(tmp_path, ests, fuentes(chj=[lec("c1", 3.0, fuente="chj")]))
    cambios = correr(tmp_path, ests, fuentes(chj=FuenteError("caido")), ahora=AHORA + timedelta(minutes=15))
    assert [(c["estacion_id"], c["sd"]) for c in cambios] == [("c1", True)]


def test_fuente_que_falla_no_frena_a_las_demas(tmp_path):
    ests = [est_aca(), est_chj()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 25.0)], chj=FuenteError("caido")))
    d = latest(tmp_path)
    assert d["a1"]["nivel"] == 1 and d["a1"]["sd"] is False
    assert d["c1"]["sd"] is True
    ok = leer(tmp_path, "latest.json")["fuentes_ok"]
    assert ok["aca"] is True and ok["chj"] is False


def test_estado_persiste_entre_ejecuciones(tmp_path):
    ests = [est_aca()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 25.0)]))
    t2 = AHORA + timedelta(minutes=15)
    cambios = correr(tmp_path, ests, fuentes(aca=[lec("a1", 45.0, ahora=t2)]), ahora=t2)
    assert cambios[0]["nivel_antes"] == 1 and cambios[0]["nivel_despues"] == 3  # subida rápida


def test_umbrales_vivos_de_chj_se_aplican(tmp_path):
    ests = [est_chj(umbrales=Umbrales(None, None, None, "en_estudio"))]
    f = fuentes(chj=[lec("c1", 12.0, fuente="chj")], chj_umbrales={"c1": Umbrales(5.0, 10.0, 20.0, "oficial")})
    correr(tmp_path, ests, f)
    e = latest(tmp_path)["c1"]
    assert e["umbrales"]["tipo"] == "oficial" and e["nivel"] == 1


def test_latest_json_tiene_el_formato_acordado(tmp_path):
    correr(tmp_path, [est_aca()], fuentes(aca=[lec("a1", 25.0)]))
    doc = leer(tmp_path, "latest.json")
    assert set(doc) == {"generado_utc", "estaciones", "avisos", "fuentes_ok"}
    e = doc["estaciones"][0]
    assert set(e) == {"id", "rio", "nombre", "cuenca", "valor", "unidad", "t_utc", "edad_min", "nivel", "sd",
                      "umbrales", "elevado_por_aviso", "fuente", "zona", "pais"}
    assert e["valor"] == 25.0 and e["edad_min"] == 5 and e["t_utc"] == "2026-10-19T20:15:00Z"
    assert set(doc["fuentes_ok"]) == {"aca", "chj", "avisos", "prevision"}


def test_sd_conserva_el_ultimo_valor_conocido(tmp_path):
    ests = [est_aca()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 25.0)]))
    correr(tmp_path, ests, fuentes(aca=FuenteError("caido")), ahora=AHORA + timedelta(minutes=30))
    e = latest(tmp_path)["a1"]
    assert e["sd"] is True and e["valor"] == 25.0 and e["edad_min"] == 35 and e["nivel"] == 1


# ---- publicar ----

def test_debe_publicar_si_hay_cambios_o_nunca_se_publico():
    cambio = [{"estacion_id": "a", "nivel_antes": 0, "nivel_despues": 1, "sd": False, "elevado_por_aviso": False}]
    reciente = utc(2026, 10, 19, 20, 10)
    assert actualizar.debe_publicar([], utc(2026, 10, 19, 20, 20), ultima=reciente) is False
    assert actualizar.debe_publicar(cambio, utc(2026, 10, 19, 20, 20), ultima=reciente) is True
    assert actualizar.debe_publicar([], utc(2026, 10, 19, 20, 20)) is True  # primera vez


def test_debe_publicar_por_antiguedad_de_la_ultima_publicacion():
    """El cron de GitHub se retrasa: no se puede depender de que caiga en los minutos 0-14."""
    ahora = utc(2026, 10, 19, 20, 20)
    assert actualizar.debe_publicar([], ahora, ultima=utc(2026, 10, 19, 19, 20)) is True
    assert actualizar.debe_publicar([], ahora, ultima=utc(2026, 10, 19, 19, 50)) is False
    assert actualizar.debe_publicar([], utc(2026, 10, 19, 20, 5), ultima=utc(2026, 10, 19, 20, 0)) is False


def test_registrar_y_leer_ultima_publicacion(tmp_path):
    assert actualizar.ultima_publicacion(str(tmp_path)) is None
    actualizar.registrar_publicacion(str(tmp_path), utc(2026, 10, 19, 20, 20))
    assert actualizar.ultima_publicacion(str(tmp_path)) == utc(2026, 10, 19, 20, 20)


# ---- historial ----

def test_historial_guarda_maximo_horario(tmp_path):
    ests = [est_aca()]
    for minutos, valor in [(0, 12.0), (15, 30.0), (30, 20.0)]:
        t = utc(2026, 10, 19, 20, 0) + timedelta(minutes=minutos + 5)
        correr(tmp_path, ests, fuentes(aca=[lec("a1", valor, ahora=t)]), ahora=t)
    h = leer(tmp_path / "history", "2026-10.json")
    assert h["a1"] == [["2026-10-19T20:00:00Z", 30.0]]


# ---- escritura atómica ----

def test_escritura_atomica_no_deja_archivo_a_medias(tmp_path, monkeypatch):
    ruta = tmp_path / "x.json"
    actualizar.escribir_json(str(ruta), {"v": 1})

    def falla(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "replace", falla)
    with pytest.raises(OSError):
        actualizar.escribir_json(str(ruta), {"v": 2})
    assert json.loads(ruta.read_text()) == {"v": 1}
    assert os.listdir(tmp_path) == ["x.json"]  # el temporal se limpia


# ---- previsión: informativa ----

PREV = {"a1": {"lluvia": [("2026-10-20", 5.0, 80), ("2026-10-21", 10.0, 90), ("2026-10-22", 0.0, 10)],
               "caudal": (4.0, 400.0)}}


def test_prevision_no_modifica_niveles_ni_cambios(tmp_path):
    ests = [est_aca()]
    sin = tmp_path / "sin"
    con = tmp_path / "con"
    sin.mkdir(), con.mkdir()
    lecturas = [lec("a1", 5.0, ahora=HORA_EN_PUNTO)]
    c1 = correr(sin, ests, fuentes(aca=lecturas), ahora=HORA_EN_PUNTO)
    c2 = correr(con, ests, fuentes(aca=lecturas, prevision=PREV), ahora=HORA_EN_PUNTO)
    assert c1 == c2 == []
    assert latest(sin)["a1"]["nivel"] == latest(con)["a1"]["nivel"] == 0
    assert json.loads((con / "state.json").read_text()) == json.loads((sin / "state.json").read_text())


def test_fallo_de_prevision_no_frena_alertas(tmp_path):
    ests = [est_aca()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 5.0, ahora=HORA_EN_PUNTO)], prevision=PREV), ahora=HORA_EN_PUNTO)
    antes = leer(tmp_path, "prevision.json")
    t2 = HORA_EN_PUNTO + timedelta(hours=1)
    cambios = correr(tmp_path, ests, fuentes(aca=[lec("a1", 25.0, ahora=t2)], prevision=FuenteError("caido")), ahora=t2)
    assert cambios[0]["nivel_despues"] == 2  # 5 -> 25 m3/s: supera el umbral medio y sube
    assert leer(tmp_path, "latest.json")["fuentes_ok"]["prevision"] is False
    despues = leer(tmp_path, "prevision.json")
    assert despues["generado_utc"] == antes["generado_utc"]  # se conserva la última buena


def test_prevision_se_pide_cuando_tiene_mas_de_55_min_o_no_existe(tmp_path):
    llamadas = []
    f = fuentes(aca=[lec("a1", 5.0)])
    f["prevision"] = lambda ests: llamadas.append(1) or PREV
    correr(tmp_path, [est_aca()], f, ahora=AHORA)  # minuto 20 y sin archivo: se pide igual
    assert llamadas == [1]
    correr(tmp_path, [est_aca()], f, ahora=AHORA + timedelta(minutes=15))
    assert llamadas == [1]
    correr(tmp_path, [est_aca()], f, ahora=AHORA + timedelta(minutes=60))
    assert llamadas == [1, 1]


def test_cualquier_error_de_la_prevision_no_tumba_la_ejecucion(tmp_path):
    cambios = correr(tmp_path, [est_aca()], fuentes(aca=[lec("a1", 25.0)], prevision=ValueError("dato raro")), ahora=HORA_EN_PUNTO)
    assert latest(tmp_path)["a1"]["valor"] == 25.0
    assert leer(tmp_path, "latest.json")["fuentes_ok"]["prevision"] is False
    assert cambios == []


def test_prevision_json_formato_y_lluvia_48h(tmp_path):
    ests = [est_aca(), est_aca(id="a2")]
    prev = {"a1": PREV["a1"], "a2": {"lluvia": [("2026-10-20", 9.0, 50), ("2026-10-21", 1.0, 20), ("2026-10-22", 0.0, 0)],
                                     "caudal": None}}
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 5.0, ahora=HORA_EN_PUNTO)], prevision=prev), ahora=HORA_EN_PUNTO)
    doc = leer(tmp_path, "prevision.json")
    assert doc["fuente"] == "Open-Meteo (CC BY 4.0)"
    assert doc["estaciones"]["a1"]["lluvia_48h_mm"] == 15.0
    assert doc["estaciones"]["a2"]["lluvia_48h_mm"] == 10.0
    assert doc["estaciones"]["a2"]["caudal"] is None
    assert doc["zonas"]["barcelona"][0] == {"fecha": "2026-10-20", "mm": 9.0, "prob": 80}  # máximos entre estaciones


def test_puede_llegar_solo_si_supera_el_nivel_actual_y_es_coherente(tmp_path):
    ests = [est_aca()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 5.0, ahora=HORA_EN_PUNTO)], prevision=PREV), ahora=HORA_EN_PUNTO)
    assert leer(tmp_path, "prevision.json")["estaciones"]["a1"]["puede_llegar"] == 3
    # modelo incoherente con lo observado (la malla engancha otro río): no se etiqueta
    d2 = tmp_path / "otro"
    d2.mkdir()
    prev = {"a1": {"lluvia": PREV["a1"]["lluvia"], "caudal": (0.5, 400.0)}}
    correr(d2, ests, fuentes(aca=[lec("a1", 12.0, ahora=HORA_EN_PUNTO)], prevision=prev), ahora=HORA_EN_PUNTO)
    assert leer(d2, "prevision.json")["estaciones"]["a1"]["puede_llegar"] is None


def test_puede_llegar_se_recalcula_sin_volver_a_pedir_la_previsión(tmp_path):
    ests = [est_aca()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 5.0, ahora=HORA_EN_PUNTO)], prevision=PREV), ahora=HORA_EN_PUNTO)
    t2 = HORA_EN_PUNTO + timedelta(minutes=15)
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 45.0, ahora=t2)]), ahora=t2)  # ya está en N3
    doc = leer(tmp_path, "prevision.json")
    assert doc["estaciones"]["a1"]["puede_llegar"] is None
    assert doc["estaciones"]["a1"]["lluvia_48h_mm"] == 15.0


# ---- avisos ----

def aviso(origen, nivel, region="", zona="X"):
    return Aviso(origen, nivel, zona, "d", AHORA, region)


def test_inuncat_en_alerta_no_eleva_por_defecto(tmp_path):
    ests = [est_aca()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 3.0)], avisos=[aviso("INUNCAT", "naranja", "cat")]))
    e = latest(tmp_path)["a1"]
    assert e["nivel"] == 0 and e["elevado_por_aviso"] is False
    assert leer(tmp_path, "latest.json")["avisos"][0]["origen"] == "INUNCAT"  # pero el aviso se muestra


def test_inuncat_en_alerta_puede_elevar_si_se_activa(tmp_path, monkeypatch):
    monkeypatch.setattr(actualizar, "INUNCAT_ALERTA_ELEVA", True)
    ests = [est_aca(), est_chj()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 3.0)], chj=[lec("c1", 3.0, fuente="chj")],
                                   avisos=[aviso("INUNCAT", "naranja", "cat")]))
    d = latest(tmp_path)
    assert d["a1"]["nivel"] == 3 and d["a1"]["elevado_por_aviso"] is True
    assert d["c1"]["nivel"] == 0  # las valencianas no dependen de INUNCAT


def test_inuncat_emergencia_eleva_catalanas_pero_no_valencianas(tmp_path):
    ests = [est_aca(), est_chj()]
    cambios = correr(tmp_path, ests, fuentes(aca=[lec("a1", 3.0)], chj=[lec("c1", 3.0, fuente="chj")],
                                             avisos=[aviso("INUNCAT", "rojo", "cat")]))
    d = latest(tmp_path)
    assert d["a1"]["nivel"] == 3 and d["a1"]["elevado_por_aviso"] is True
    assert d["c1"]["nivel"] == 0
    assert [c["estacion_id"] for c in cambios] == ["a1"] and cambios[0]["elevado_por_aviso"] is True


def test_aviso_rojo_de_aemet_se_muestra_pero_no_eleva(tmp_path):
    """Spec §5, fase 1: las zonas de AEMET no están cruzadas con comarcas, así que solo se muestran."""
    ests = [est_aca(), est_chj()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 3.0)], chj=[lec("c1", 3.0, fuente="chj")],
                                   avisos=[aviso("AEMET", "rojo", "val"), aviso("AEMET", "rojo", "cat")]))
    d = latest(tmp_path)
    assert d["a1"]["nivel"] == 0 and d["c1"]["nivel"] == 0
    assert len(leer(tmp_path, "latest.json")["avisos"]) == 2


def test_aviso_naranja_de_aemet_no_eleva(tmp_path):
    correr(tmp_path, [est_aca()], fuentes(aca=[lec("a1", 3.0)], avisos=[aviso("AEMET", "naranja", "cat")]))
    assert latest(tmp_path)["a1"]["nivel"] == 0


def test_al_acabar_el_aviso_vuelve_al_nivel_propio(tmp_path):
    ests = [est_aca()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 3.0)], avisos=[aviso("INUNCAT", "rojo", "cat")]))
    t2 = AHORA + timedelta(minutes=15)
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 3.0, ahora=t2)], avisos=[]), ahora=t2)
    assert latest(tmp_path)["a1"]["nivel"] == 0


def test_fuente_de_avisos_caida_conserva_los_ultimos_avisos(tmp_path):
    ests = [est_aca()]
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 3.0)], avisos=[aviso("INUNCAT", "rojo", "cat")]))
    t2 = AHORA + timedelta(minutes=15)
    correr(tmp_path, ests, fuentes(aca=[lec("a1", 3.0, ahora=t2)], avisos=FuenteError("caido")), ahora=t2)
    doc = leer(tmp_path, "latest.json")
    assert doc["fuentes_ok"]["avisos"] is False
    assert doc["avisos"][0]["nivel"] == "rojo"
    assert latest(tmp_path)["a1"]["nivel"] == 3  # un aviso rojo vigente no desaparece porque se cayó la fuente


# ---- ventana ACA ----

def test_ventana_solo_para_estaciones_cerca_del_umbral(tmp_path):
    cerca, lejos = est_aca(id="cerca"), est_aca(id="lejos")
    pedidas = []

    def ventana(est, desde, hasta):
        pedidas.append(est.id)
        assert hasta - desde == timedelta(minutes=90)
        return [(AHORA - timedelta(minutes=40), 35.0), (AHORA - timedelta(minutes=5), 9.0)]

    f = fuentes(aca=[lec("cerca", 9.0), lec("lejos", 1.0)], ventana=ventana)
    correr(tmp_path, [cerca, lejos], f)
    assert pedidas == ["cerca"]
    d = latest(tmp_path)
    assert d["cerca"]["nivel"] == 1       # evaluó con el máximo de la ventana (35), no con el último valor (9)
    assert d["cerca"]["valor"] == 9.0     # pero muestra la lectura real
    assert d["lejos"]["nivel"] == 0


def test_ventana_que_falla_no_frena_la_evaluacion(tmp_path):
    def ventana(est, desde, hasta):
        raise FuenteError("caido")

    correr(tmp_path, [est_aca()], fuentes(aca=[lec("a1", 9.0)], ventana=ventana))
    assert latest(tmp_path)["a1"]["nivel"] == 0


def test_ventana_no_cuenta_dos_veces_la_misma_muestra(tmp_path):
    """Una muestra suelta dentro de la ventana de 90 min no puede valer como dos lecturas seguidas."""
    e = est_aca(umbrales=Umbrales(100.0, 200.0, 400.0, "estimado"))
    pico = lambda est, desde, hasta: [(AHORA - timedelta(minutes=10), 104.0)]  # noqa: E731
    t0 = AHORA - timedelta(minutes=15)
    correr(tmp_path, [e], fuentes(aca=[lec("a1", 80.0, ahora=t0)]), ahora=t0)
    correr(tmp_path, [e], fuentes(aca=[lec("a1", 80.0)], ventana=pico), ahora=AHORA)
    t2 = AHORA + timedelta(minutes=15)
    cambios = correr(tmp_path, [e], fuentes(aca=[lec("a1", 80.0, ahora=t2)], ventana=pico), ahora=t2)
    assert cambios == []
    assert latest(tmp_path)["a1"]["nivel"] == 0


# ---- multipaís ----

def est_ina(**kw):
    base = dict(id="i1", fuente="ina", componente=None, ref="42", zona="litoral-parana", pais="ar",
                magnitud="altura", unidad="m", umbrales=Umbrales(3.0, 4.0, 5.0, "oficial"))
    base.update(kw)
    return make_estacion(**base)


def fuentes_ar(lecturas=(), error=None):
    def f_ina(ests):
        if error:
            raise error
        return list(lecturas), {}
    return {"ina": f_ina}


def test_un_pais_roto_no_frena_a_los_demas(tmp_path, capsys):
    paises = {"es": [est_aca()], "ar": [est_ina()]}
    # estado previo de ar: debe quedar intacto
    (tmp_path / "ar").mkdir()
    (tmp_path / "ar" / "latest.json").write_text('{"previo": true}', encoding="utf-8")
    por_pais = {"es": fuentes(aca=[lec("a1", 25.0)]), "ar": fuentes_ar(error=RuntimeError("boom"))}
    por_pais["ar"]["ina"] = lambda ests: (_ for _ in ()).throw(RuntimeError("boom"))
    res = actualizar.ejecutar_todo(AHORA, paises, por_pais, str(tmp_path))
    assert "es" in res and "ar" not in res
    assert latest(tmp_path / "es")["a1"]["nivel"] == 1
    assert leer(tmp_path / "ar", "latest.json") == {"previo": True}
    assert "ar" in capsys.readouterr().err


def test_pais_sin_avisos_ni_prevision_no_los_pide(tmp_path):
    actualizar.ejecutar(AHORA, [est_ina()], fuentes_ar([lec("i1", 3.5, unidad="m", fuente="ina")]), str(tmp_path))
    ok = leer(tmp_path, "latest.json")["fuentes_ok"]
    assert ok == {"ina": True}
    assert leer(tmp_path, "latest.json")["avisos"] == []
    assert latest(tmp_path)["i1"]["nivel"] == 1
    assert latest(tmp_path)["i1"]["unidad"] == "m" and latest(tmp_path)["i1"]["pais"] == "ar"


def test_fuente_necesaria_ausente_marca_ok_falso(tmp_path):
    actualizar.ejecutar(AHORA, [est_ina()], {}, str(tmp_path))
    assert leer(tmp_path, "latest.json")["fuentes_ok"] == {"ina": False}
    assert latest(tmp_path)["i1"]["sd"] is True


def test_altura_no_genera_puede_llegar(tmp_path):
    e = est_ina()
    bruto = {"i1": {"lluvia": [("2026-10-20", 10.0, 80), ("2026-10-21", 5.0, 50)], "caudal": (1.0, 9999.0)}}
    f = fuentes_ar([lec("i1", 1.0, unidad="m", fuente="ina")])
    f["prevision"] = lambda ests: bruto
    actualizar.ejecutar(AHORA, [e], f, str(tmp_path))
    assert leer(tmp_path, "prevision.json")["estaciones"]["i1"]["puede_llegar"] is None


def test_primera_ejecucion_avisa_una_vez(tmp_path):
    ests = [est_aca(id="a1"), est_aca(id="a2")]
    f = fuentes(aca=[lec("a1", 3.0), lec("a2", 3.0)])
    f["aca"] = lambda e: ([lec("a1", 50.0), lec("a2", 3.0)], {})
    c1 = correr(tmp_path, ests, f)
    assert [(c["estacion_id"], c["nivel_despues"]) for c in c1] == [("a1", 3)]
    assert correr(tmp_path, ests, f) == []


def test_indice_de_paises(tmp_path):
    ests = [est_aca(id="a1"), est_aca(id="a2"), est_aca(id="a3")]
    f = fuentes(aca=[lec("a1", 25.0), lec("a2", 3.0)])
    actualizar.ejecutar_todo(AHORA, {"es": ests}, {"es": f}, str(tmp_path))
    idx = leer(tmp_path, "paises.json")
    assert idx["es"]["estaciones"] == 3 and idx["es"]["sd"] == 1
    assert idx["es"]["por_nivel"] == [2, 1, 0, 0]
    assert idx["es"]["generado_utc"] == "2026-10-19T20:20:00Z"
    assert idx["es"]["fuentes_ok"]["aca"] is True


def test_indice_conserva_entrada_del_pais_que_falla(tmp_path):
    actualizar.escribir_json(str(tmp_path / "paises.json"), {"ar": {"estaciones": 7}})
    paises = {"es": [est_aca()], "ar": [est_ina()]}
    por_pais = {"es": fuentes(aca=[lec("a1", 3.0)]), "ar": {"ina": lambda e: (_ for _ in ()).throw(RuntimeError("x"))}}
    actualizar.ejecutar_todo(AHORA, paises, por_pais, str(tmp_path))
    idx = leer(tmp_path, "paises.json")
    assert idx["ar"] == {"estaciones": 7} and idx["es"]["estaciones"] == 1


def test_fuentes_reales_por_pais():
    assert set(actualizar._fuentes_reales("ar")) == {"ina", "agp", "prevision"}
    assert set(actualizar._fuentes_reales("us")) == {"usgs", "prevision", "pronostico_rio"}
    assert set(actualizar._fuentes_reales("es")) == {"aca", "aca_ventana", "chj", "avisos", "prevision"}


def test_main_vacia_cambios_del_pais_que_falla(tmp_path, monkeypatch):
    """Un país que sigue fallando no puede dejar su cambios.json viejo: notificar lo reenviaría cada 15 min."""
    import estaciones
    (tmp_path / "ar").mkdir()
    (tmp_path / "es").mkdir()
    actualizar.escribir_json(str(tmp_path / "ar" / "cambios.json"), [{"estacion_id": "i1", "nivel_antes": 0, "nivel_despues": 3, "sd": False, "elevado_por_aviso": False}])
    monkeypatch.setattr(actualizar, "DIR_DATA", str(tmp_path))
    monkeypatch.setattr(actualizar, "_paises_con_registro", lambda *a: ["ar", "es"])
    monkeypatch.setattr(estaciones, "cargar", lambda ruta, pais: [est_ina()] if pais == "ar" else [est_aca()])
    monkeypatch.setattr(actualizar, "_fuentes_reales", lambda pais: (
        {"ina": lambda e: (_ for _ in ()).throw(RuntimeError("x"))} if pais == "ar" else fuentes(aca=[lec("a1", 3.0)])))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert actualizar.main() == 0
    assert leer(tmp_path / "ar", "cambios.json") == []
    assert leer(tmp_path / "es", "cambios.json") == []
