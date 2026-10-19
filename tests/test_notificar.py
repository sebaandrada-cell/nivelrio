import notificar


def cambio(antes=0, despues=2, sd=False, aviso=False, id_="x"):
    return {"estacion_id": id_, "nivel_antes": antes, "nivel_despues": despues, "sd": sd, "elevado_por_aviso": aviso}


def test_titulo_incluye_nivel_y_rio():
    t, _ = notificar.redactar_issue(cambio(), "Sant Joan Despí", "Llobregat", 140.0, "m3s", 5)
    assert t == "Llobregat · Sant Joan Despí: nivel N2 (Aviso)"


def test_titulo_sin_datos():
    t, _ = notificar.redactar_issue(cambio(2, 2, sd=True), "Girona", "Ter", 80.0, "m3s", 40)
    assert t == "Ter · Girona: sin datos"


def test_cuerpo_incluye_valor_edad_fuente_y_pie():
    _, c = notificar.redactar_issue(cambio(), "Sant Joan Despí", "Llobregat", 140.0, "m3s", 5,
                                    fuente="aca", tipo_umbral="estimado")
    assert "140" in c and "m³/s" in c
    assert "5 min" in c
    assert "ACA" in c
    assert "estimado, no oficial" in c
    assert "Informativo" in c and "Protecció Civil" in c


def test_umbral_oficial_se_rotula_como_oficial():
    _, c = notificar.redactar_issue(cambio(), "Manises", "Túria", 90.0, "m3s", 3, fuente="chj", tipo_umbral="oficial")
    assert "CHJ" in c and "oficial" in c and "estimado" not in c


def test_sd_en_n3_menciona_ultimo_dato():
    _, c = notificar.redactar_issue(cambio(3, 3, sd=True), "Girona", "Ter", 310.0, "m3s", 55)
    assert "último dato hace 55 min" in c.lower()
    assert "N3" in c and "se mantiene" in c.lower()


def test_cuerpo_menciona_aviso_oficial_si_eleva_un_aviso():
    _, c = notificar.redactar_issue(cambio(0, 3, aviso=True), "Girona", "Ter", 5.0, "m3s", 3)
    assert "aviso oficial" in c.lower()


def test_sin_valor_no_rompe():
    t, c = notificar.redactar_issue(cambio(2, 2, sd=True), "Girona", "Ter", None, "m3s", None)
    assert "sin datos" in t and "Informativo" in c


def test_solo_notifica_subidas_y_sd_en_n2_n3():
    cs = [
        cambio(0, 1),                 # subida a N1: sí
        cambio(2, 1),                 # bajada: no
        cambio(3, 3, sd=True),        # SD en N3: sí
        cambio(2, 2, sd=True),        # SD en N2: sí
        cambio(1, 1, sd=True),        # SD en N1: no
        cambio(0, 0, sd=True),        # SD en N0: no
        cambio(1, 1, sd=False),       # vuelve de SD: no
    ]
    sel = notificar.seleccionar(cs)
    assert sel == [cs[0], cs[2], cs[3]]
