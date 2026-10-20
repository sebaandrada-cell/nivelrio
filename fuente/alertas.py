"""Máquina de estados de alertas N0-N3 y SD. Función pura, sin E/S.

Esquema propio de esta página, no oficial. Reglas en docs/superpowers/specs/ (sección 5).

`nivel` es el nivel que se muestra; `nivel_propio` es el que sale solo de los umbrales (con
histéresis). Se distinguen para que, al terminar un aviso oficial, la estación vuelva a su nivel real.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

from modelo import Estacion, Lectura

VEL_SUBIDA_RAPIDA = 0.25  # fracción del umbral bajo por lectura que cuenta como subida rápida. A calibrar con el historial.
HISTERESIS = 0.85
LECTURAS_PARA_BAJAR = 3
HORAS_PARA_BAJAR = 3
LECTURAS_PARA_SUBIR = 2
LIMITE_SD_CHJ_MIN = 25
MUESTREOS_PARA_SD_ACA = 3
MUESTREO_DIARIO_MIN = 1440  # desde aquí hay una lectura al día: una sola lectura confirma la subida


@dataclass(frozen=True)
class Estado:
    nivel: int  # 0..3, el que se muestra
    sd: bool
    ultimo_valor: float | None
    ultimo_t_utc: datetime | None
    cnt_sobre: int
    cnt_bajo: int
    bajo_desde: datetime | None
    elevado_por_aviso: bool
    nivel_propio: int = 0  # 0..3, el que sale de los umbrales


ESTADO_INICIAL = Estado(0, False, None, None, 0, 0, None, False, 0)


def _iso(d: datetime | None) -> str | None:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def _desde_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def estado_a_dict(e: Estado) -> dict:
    return {
        "nivel": e.nivel, "nivel_propio": e.nivel_propio, "sd": e.sd, "ultimo_valor": e.ultimo_valor,
        "ultimo_t_utc": _iso(e.ultimo_t_utc), "cnt_sobre": e.cnt_sobre, "cnt_bajo": e.cnt_bajo,
        "bajo_desde": _iso(e.bajo_desde), "elevado_por_aviso": e.elevado_por_aviso,
    }


def estado_desde_dict(d: dict) -> Estado:
    return Estado(
        nivel=int(d["nivel"]), sd=bool(d["sd"]), ultimo_valor=d.get("ultimo_valor"),
        ultimo_t_utc=_desde_iso(d.get("ultimo_t_utc")), cnt_sobre=int(d.get("cnt_sobre", 0)),
        cnt_bajo=int(d.get("cnt_bajo", 0)), bajo_desde=_desde_iso(d.get("bajo_desde")),
        elevado_por_aviso=bool(d.get("elevado_por_aviso", False)),
        nivel_propio=int(d.get("nivel_propio", d["nivel"])),
    )


def limite_sd(est: Estacion) -> timedelta:
    """Antigüedad máxima de la última lectura antes de pasar a «sin datos»."""
    if est.fuente == "chj":
        return timedelta(minutes=LIMITE_SD_CHJ_MIN)
    if est.muestreo_min >= MUESTREO_DIARIO_MIN:
        return timedelta(minutes=2 * est.muestreo_min)  # una lectura al día: 3 muestreos serían 3 días
    return timedelta(minutes=MUESTREOS_PARA_SD_ACA * est.muestreo_min)


def evaluar(prev: Estado, lectura: Lectura | None, est: Estacion, ahora: datetime, aviso_rojo: bool = False) -> Estado:
    def cerrar(**cambios) -> Estado:
        e = replace(prev, **cambios)
        return replace(e, nivel=3 if aviso_rojo else e.nivel_propio, elevado_por_aviso=aviso_rojo)

    # Sin datos: falta la lectura, está en otra unidad (los umbrales son de la unidad de la estación), viene del futuro o es vieja.
    if (lectura is None or lectura.unidad != est.unidad or lectura.t_utc > ahora
            or ahora - lectura.t_utc > limite_sd(est)):
        return cerrar(sd=True)

    u = est.umbrales
    v, t = lectura.valor, lectura.t_utc
    if u.tipo == "en_estudio" or None in (u.bajo, u.medio, u.alto):
        return cerrar(sd=False, ultimo_valor=v, ultimo_t_utc=t, nivel_propio=0, cnt_sobre=0, cnt_bajo=0, bajo_desde=None)

    if prev.ultimo_t_utc == t:  # misma lectura que la última: no cuenta como una nueva
        return cerrar(sd=False)

    vel = est.vel_subida_rapida
    if vel is None and est.magnitud == "caudal":
        vel = VEL_SUBIDA_RAPIDA * u.bajo
    para_subir = 1 if est.muestreo_min >= MUESTREO_DIARIO_MIN else LECTURAS_PARA_SUBIR
    entrada = (None, u.bajo, u.medio, u.alto)
    prev_v = prev.ultimo_valor

    def candidato(valor: float, sube: bool) -> int:
        c = 1 if valor >= u.bajo else 0
        if valor >= u.medio and (sube or prev.nivel_propio >= 2):
            c = 2  # N2 exige caudal subiendo, salvo que ya estuviera en N2 o más
        if valor >= u.alto:
            c = 3
        return c

    c = candidato(v, prev_v is not None and v > prev_v)
    nivel, cnt_sobre, cnt_bajo, bajo_desde = prev.nivel_propio, prev.cnt_sobre, prev.cnt_bajo, prev.bajo_desde

    if c > nivel:
        cnt_sobre += 1
        cnt_bajo, bajo_desde = 0, None
        rapido = vel is not None and prev_v is not None and (v - prev_v) >= vel
        if prev_v is None or rapido or para_subir <= 1:  # sin historial no hay con qué confirmar; subida rápida no espera
            nivel, cnt_sobre = c, 0
        elif cnt_sobre >= para_subir:
            objetivo = min(c, candidato(prev_v, True))  # el nivel que superaron las dos lecturas seguidas
            if objetivo > nivel:
                nivel, cnt_sobre = objetivo, 0
    else:
        cnt_sobre = 0
        if nivel > 0 and v < HISTERESIS * entrada[nivel]:
            cnt_bajo += 1
            bajo_desde = bajo_desde or t
            if cnt_bajo >= LECTURAS_PARA_BAJAR or t - bajo_desde >= timedelta(hours=HORAS_PARA_BAJAR):
                nivel -= 1  # un nivel por vez
                cnt_bajo, bajo_desde = 0, None
        else:
            cnt_bajo, bajo_desde = 0, None

    return cerrar(sd=False, ultimo_valor=v, ultimo_t_utc=t, nivel_propio=nivel,
                  cnt_sobre=cnt_sobre, cnt_bajo=cnt_bajo, bajo_desde=bajo_desde)
