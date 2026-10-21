#!/usr/bin/env python3
"""Orquestador: descarga las fuentes, evalúa las alertas, escribe data/*.json y avisa si hay que publicar.

Cada fuente se llama dentro de try/except FuenteError: una fuente caída deja sus estaciones en «sin datos»
y no frena a las demás. La previsión es solo informativa y nunca entra en `evaluar` ni en `cambios`.
"""
import json
import os
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from alertas import ESTADO_INICIAL, estado_a_dict, estado_desde_dict, evaluar
from modelo import Aviso, FuenteError

# INUNCAT en ALERTA es el estado habitual de Catalunya durante episodios largos: si forzara N3, todas las
# estaciones saltarían a «Peligro» con caudales normales. Por defecto solo EMERGÈNCIA (rojo) eleva.
INUNCAT_ALERTA_ELEVA = False
PERIODO_HORARIO = timedelta(minutes=55)  # el cron de GitHub se retrasa: se mide el tiempo, no el minuto del reloj
VENTANA_MIN = 90          # minutos de historia de Sentilo que se miran para no perder picos entre ejecuciones
CERCA_DEL_UMBRAL = 0.8    # fracción del umbral bajo desde la que se pide la ventana

AQUI = os.path.dirname(os.path.abspath(__file__))
DIR_PAISES = os.path.join(AQUI, "paises")
DIR_DATA = os.path.join(AQUI, "..", "data")
FUENTES_DATOS = ("aca", "chj", "ina", "agp", "usgs")  # contrato: callable(estaciones) -> (lecturas, umbrales_vivos)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _desde_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def escribir_json(ruta: str, obj) -> None:
    """Escritura atómica: temporal en el mismo directorio y os.replace. Si falla, el original queda intacto."""
    carpeta = os.path.dirname(os.path.abspath(ruta))
    os.makedirs(carpeta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=carpeta, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
            f.write("\n")
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _leer(ruta: str, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def _aviso_a_dict(a: Aviso) -> dict:
    return {"origen": a.origen, "nivel": a.nivel, "zona": a.zona, "descripcion": a.descripcion,
            "t_utc": _iso(a.t_utc), "region": a.region}


def _aviso_desde_dict(d: dict) -> Aviso:
    return Aviso(d["origen"], d["nivel"], d["zona"], d["descripcion"], _desde_iso(d["t_utc"]), d.get("region", ""))


def _eleva(avisos: list[Aviso], est) -> bool:
    """Spec §5, fase 1: solo INUNCAT eleva. Los avisos de AEMET se muestran pero no tocan los niveles,
    porque sus zonas todavía no están cruzadas con las comarcas de cada río."""
    region = "val" if est.zona == "valencia" else "cat"
    for a in avisos:
        if a.origen == "INUNCAT" and region == "cat" and (a.nivel == "rojo" or (INUNCAT_ALERTA_ELEVA and a.nivel == "naranja")):
            return True
    return False


def _lectura_para_evaluar(est, lectura, prev, ahora, ventana):
    """Para estaciones ACA cerca del umbral, el máximo de la ventana sustituye al último valor."""
    u = est.umbrales
    if ventana is None or lectura is None or lectura.unidad != "m3s" or est.fuente != "aca" or u.bajo is None:
        return lectura
    if not (prev.nivel >= 1 or lectura.valor >= CERCA_DEL_UMBRAL * u.bajo):
        return lectura
    try:
        puntos = ventana(est, ahora - timedelta(minutes=VENTANA_MIN), ahora)
    except FuenteError:
        return lectura
    # Solo cuentan las muestras posteriores a la última ya evaluada: cada muestra vale una vez, y una
    # muestra suelta dentro de los 90 min no puede contar como lecturas consecutivas en ejecuciones distintas.
    desde = prev.ultimo_t_utc
    valores = [v for t, v in puntos if desde is None or t > desde]
    return replace(lectura, valor=max([lectura.valor, *valores])) if valores else lectura


def _historial(dir_data: str, ahora: datetime, puntos: dict[str, tuple[datetime, float]]) -> None:
    ruta = os.path.join(dir_data, "history", ahora.astimezone(timezone.utc).strftime("%Y-%m") + ".json")
    hist = _leer(ruta, {})
    for id_, (t, valor) in puntos.items():
        hora = _iso(t.replace(minute=0, second=0, microsecond=0))
        filas = hist.setdefault(id_, [])
        for fila in filas:
            if fila[0] == hora:
                fila[1] = max(fila[1], valor)
                break
        else:
            filas.append([hora, valor])
            filas.sort()
    escribir_json(ruta, hist)


def _puede_llegar(est, caudal, observado, nivel_actual):
    """Etiqueta informativa. Se compara el observado con el mínimo del modelo (su caudal de base): si el
    modelo prevé una crecida, su máximo se parece poco al caudal de hoy, y eso no lo hace incoherente."""
    from fuentes import prevision
    if est.magnitud != "caudal" or not caudal or observado is None or not prevision.coherente(observado, caudal[0]):
        return None
    n = prevision.nivel_posible(est.umbrales, caudal[1])
    return n if n > nivel_actual else None


def _doc_prevision(ahora, estaciones, bruto) -> dict:
    zonas: dict[str, list[dict]] = {}
    por_est = {}
    for e in estaciones:
        p = bruto.get(e.id)
        if not p:
            por_est[e.id] = {"lluvia_48h_mm": None, "caudal": None, "puede_llegar": None}
            continue
        lluvia = p["lluvia"]
        # GloFAS values at un-gauged points cannot be checked against a local observation; do not publish them as
        # river-flow forecasts until the model/grid assignment has been validated for that station.
        caudal = list(p["caudal"]) if p["caudal"] and e.magnitud == "caudal" and e.fuente != "glofas" else None
        por_est[e.id] = {"lluvia_48h_mm": round(sum(mm for _, mm, _ in lluvia[:2]), 1),
                         "caudal": caudal, "puede_llegar": None}
        dias = zonas.setdefault(e.zona, [])
        for i, (fecha, mm, prob) in enumerate(lluvia):
            if i < len(dias):
                dias[i]["mm"], dias[i]["prob"] = max(dias[i]["mm"], mm), max(dias[i]["prob"], prob)
            else:
                dias.append({"fecha": fecha, "mm": mm, "prob": prob})
    return {"generado_utc": _iso(ahora), "fuente": "Open-Meteo (CC BY 4.0)", "zonas": zonas, "estaciones": por_est}


def ejecutar(ahora: datetime, estaciones: list, fuentes: dict, dir_data: str) -> list[dict]:
    estados_json = _leer(os.path.join(dir_data, "state.json"), {})
    previo = _leer(os.path.join(dir_data, "latest.json"), {})
    ok = {}

    # --- lecturas y umbrales vivos ---
    lecturas, vivos = {}, {}
    for clave in FUENTES_DATOS:
        ests = [e for e in estaciones if e.fuente == clave]
        if not ests:
            if clave in fuentes:  # fuente cableada para el país pero sin estaciones hoy: figura como sana
                ok[clave] = True
            continue
        if clave not in fuentes:  # la fuente no está cableada para este país: sus estaciones quedan en «sin datos»
            ok[clave] = False
            continue
        try:
            ls, um = fuentes[clave](ests)
            lecturas.update({x.estacion_id: x for x in ls})
            vivos.update(um)
            ok[clave] = True
        except FuenteError:
            ok[clave] = False

    # --- avisos: si la fuente cae se conservan los últimos, un aviso rojo no desaparece por un corte ---
    if "avisos" in fuentes:
        try:
            avisos = list(fuentes["avisos"]())
            ok["avisos"] = True
        except FuenteError:
            avisos = [_aviso_desde_dict(d) for d in _leer(os.path.join(dir_data, "avisos.json"), [])]
            ok["avisos"] = False
    else:
        avisos = []

    # --- niveles ---
    cambios, nuevos, filas, historial = [], {}, [], {}
    for est in estaciones:
        e = replace(est, umbrales=vivos.get(est.id, est.umbrales))
        existia = est.id in estados_json
        prev = estado_desde_dict(estados_json[est.id]) if existia else ESTADO_INICIAL
        lectura = lecturas.get(est.id)
        nuevo = evaluar(prev, _lectura_para_evaluar(e, lectura, prev, ahora, fuentes.get("aca_ventana")), e, ahora,
                        aviso_rojo=_eleva(avisos, e))
        nuevos[est.id] = nuevo
        if (nuevo.nivel != prev.nivel or nuevo.sd != prev.sd) and (existia or nuevo.nivel > 0):
            cambios.append({"estacion_id": est.id, "nivel_antes": prev.nivel, "nivel_despues": nuevo.nivel,
                            "sd": nuevo.sd, "elevado_por_aviso": nuevo.elevado_por_aviso})
        if lectura is not None and lectura.unidad == est.unidad:
            valor, t = lectura.valor, lectura.t_utc
        else:
            valor, t = nuevo.ultimo_valor, nuevo.ultimo_t_utc
        if lectura is not None and lectura.unidad == est.unidad and not nuevo.sd:
            historial[est.id] = (lectura.t_utc, lectura.valor)
        filas.append({
            "id": est.id, "rio": est.rio, "nombre": est.nombre, "cuenca": est.cuenca, "zona": est.zona,
            "valor": valor, "unidad": est.unidad, "pais": est.pais, "t_utc": _iso(t) if t else None,
            "edad_min": int((ahora - t).total_seconds() // 60) if t else None,
            "nivel": nuevo.nivel, "sd": nuevo.sd,
            "umbrales": {"bajo": e.umbrales.bajo, "medio": e.umbrales.medio, "alto": e.umbrales.alto, "tipo": e.umbrales.tipo},
            "elevado_por_aviso": nuevo.elevado_por_aviso, "fuente": est.fuente,
        })

    # --- previsión: informativa, una vez por hora; nunca toca niveles ni cambios ---
    ruta_prev = os.path.join(dir_data, "prevision.json")
    doc = _leer(ruta_prev, None)
    if "prevision" in fuentes:
        ok["prevision"] = previo.get("fuentes_ok", {}).get("prevision", True)
    generado = _desde_iso(doc["generado_utc"]) if doc and doc.get("generado_utc") else None
    if "prevision" in fuentes and (generado is None or ahora - generado >= PERIODO_HORARIO):
        try:
            doc = _doc_prevision(ahora, estaciones, fuentes["prevision"](estaciones))
            ok["prevision"] = True
        except Exception:  # noqa: BLE001 - la previsión es informativa: ningún fallo suyo puede frenar las alertas
            ok["prevision"] = False
    if doc and "prevision" in fuentes:
        por_id = {f["id"]: f for f in filas}
        for est in estaciones:
            p = doc["estaciones"].get(est.id)
            if p is not None:
                f = por_id[est.id]
                e = replace(est, umbrales=vivos.get(est.id, est.umbrales))
                p["puede_llegar"] = _puede_llegar(e, p.get("caudal"), f["valor"], f["nivel"])
        escribir_json(ruta_prev, doc)

    # --- pronóstico de río (NWS): informativo, no entra en niveles, cambios ni fuentes_ok ---
    if "pronostico_rio" in fuentes:
        try:
            docs = fuentes["pronostico_rio"](estaciones)
        except Exception:  # noqa: BLE001 - nada de esto puede frenar las alertas
            docs = {}
        ids = {e.id for e in estaciones}  # el id es el nombre de la carpeta: solo ids del registro
        for id_, d in docs.items():
            if id_ in ids and d and d.get("puntos"):
                try:
                    escribir_json(os.path.join(dir_data, "rios", id_, "pronostico.json"), d)
                except OSError:
                    pass

    # --- persistencia ---
    escribir_json(os.path.join(dir_data, "state.json"), {i: estado_a_dict(s) for i, s in nuevos.items()})
    escribir_json(os.path.join(dir_data, "avisos.json"), [_aviso_a_dict(a) for a in avisos])
    escribir_json(os.path.join(dir_data, "latest.json"), {
        "generado_utc": _iso(ahora), "estaciones": filas,
        "avisos": [_aviso_a_dict(a) for a in avisos], "fuentes_ok": ok})
    _historial(dir_data, ahora, historial)
    return cambios


def ultima_publicacion(dir_data: str):
    t = _leer(os.path.join(dir_data, "meta.json"), {}).get("ultima_publicacion_utc")
    try:
        return _desde_iso(t) if t else None
    except ValueError:
        return None


def registrar_publicacion(dir_data: str, ahora: datetime) -> None:
    escribir_json(os.path.join(dir_data, "meta.json"), {"ultima_publicacion_utc": _iso(ahora)})


def debe_publicar(cambios: list[dict], ahora: datetime, ultima=None) -> bool:
    """Publica si hay cambios de nivel o si pasó más de ~una hora desde la última publicación."""
    return bool(cambios) or ultima is None or ahora - ultima >= PERIODO_HORARIO


def ejecutar_todo(ahora: datetime, paises: dict, fuentes_por_pais: dict, raiz_data: str) -> dict:
    """Ejecuta cada país aislado en raiz_data/<pais>. Un país que lanza cualquier excepción se registra en stderr
    y se salta: sus archivos quedan como estaban. Devuelve {pais: cambios} solo de los que corrieron bien."""
    resultado = {}
    for pais, estaciones in paises.items():
        try:
            resultado[pais] = ejecutar(ahora, estaciones, fuentes_por_pais.get(pais, {}), os.path.join(raiz_data, pais))
        except Exception as exc:  # noqa: BLE001 - el aislamiento por país es el contrato
            print(f"{pais}: falló la ejecución: {exc!r}", file=sys.stderr)
    ruta = os.path.join(raiz_data, "paises.json")
    indice = _leer(ruta, {})
    for pais in resultado:
        latest = _leer(os.path.join(raiz_data, pais, "latest.json"), {})
        filas = latest.get("estaciones", [])
        por_nivel = [0, 0, 0, 0]
        for f in filas:
            por_nivel[f["nivel"]] += 1
        indice[pais] = {"generado_utc": latest.get("generado_utc", _iso(ahora)), "estaciones": len(filas),
                        "por_nivel": por_nivel, "sd": sum(1 for f in filas if f["sd"]),
                        "fuentes_ok": latest.get("fuentes_ok", {})}
    if resultado:
        escribir_json(ruta, indice)
    return resultado


def _fuentes_ar() -> dict:
    """INA para el Paraná/Uruguay y AGP para Barranqueras (con el INA de respaldo). El INA se baja una sola vez
    por ejecución y se comparte entre las dos fuentes; el caché vive en esta llamada, no entre ejecuciones."""
    from fuentes import agp, ina, prevision
    cache = {}

    def ina_parseado():
        if "ina" not in cache:
            try:
                cache["ina"] = ina.parse(ina.bajar())
            except FuenteError as exc:
                cache["ina"] = exc  # el fallo también se comparte: no se reintenta dentro de la ejecución
        if isinstance(cache["ina"], FuenteError):
            raise cache["ina"]
        return cache["ina"]

    def f_ina(ests):
        parseadas = ina_parseado()
        return ina.lecturas_para(ests, parseadas), {e.id: parseadas[str(e.ref)]["umbrales"]
                                                    for e in ests if str(e.ref) in parseadas}

    def f_agp(ests):
        try:
            ultima = agp.parse(agp.bajar())
        except FuenteError:  # hoy el TLS del puerto no verifica: es lo esperado y se cubre con el INA
            ultima = None
        try:
            parseadas = ina_parseado()
        except FuenteError:
            parseadas = {}
        ahora = datetime.now(timezone.utc)
        salida = []
        for e in ests:
            l_agp = next(iter(agp.lecturas_para([e], ultima)), None)
            l_ina = next(iter(ina.lecturas_para([replace(e, fuente="ina")], parseadas)), None)
            elegida = agp.elegir(l_agp, l_ina, ahora)
            if elegida is not None:
                salida.append(elegida)  # conserva Lectura.fuente: "agp" o "ina"
        if not salida:
            raise FuenteError("agp: sin lectura de AGP ni de INA")
        return salida, {}  # los umbrales de Barranqueras son los APA fijos del registro

    return {"ina": f_ina, "agp": f_agp, "prevision": prevision.bajar}


def _fuentes_us() -> dict:
    from fuentes import prevision, usgs_nws

    def f_usgs(ests):
        return usgs_nws.bajar_todo(ests)

    def f_pronostico(ests):
        docs, generado = {}, _iso(datetime.now(timezone.utc))
        for e in ests:
            if not e.lid:
                continue
            try:
                puntos = usgs_nws.bajar_pronostico(e.lid)
            except Exception:  # noqa: BLE001 - informativo: una estación caída no afecta a las demás
                continue
            if puntos:
                docs[e.id] = {"fuente": "NWS", "manual": False, "generado_utc": generado,
                              "puntos": [[_iso(t), v] for t, v in puntos]}
        return docs

    return {"usgs": f_usgs, "prevision": prevision.bajar, "pronostico_rio": f_pronostico}


def _fuentes_reales(pais: str = "es") -> dict:
    from estaciones import PAISES
    if pais not in PAISES:
        return {}
    if pais == "ar":
        return _fuentes_ar()
    if pais == "us":
        return _fuentes_us()
    if pais != "es":
        from fuentes import prevision
        return {"prevision": prevision.bajar}
    from fuentes import aca, avisos, chj, prevision
    cache = {}

    def f_aca(ests):
        cache["catalogo"] = aca.bajar(aca.URL_CATALOGO)
        ultimos = aca.parse_ultimos(aca.bajar(aca.URL_ULTIMOS))
        return aca.lecturas_para(ests, ultimos, cache["catalogo"]), {}

    def f_ventana(est, desde, hasta):
        catalogo = cache.get("catalogo")
        sensor = aca.resolver_sensores(catalogo, est.componente)[0] if catalogo else None
        return aca.parse_ventana(aca.bajar(aca.url_ventana(sensor, desde, hasta))) if sensor else []

    def f_chj(ests):
        aforos = chj.parse_aforos(chj.bajar_aforos())
        vivos = {e.id: aforos[e.id_cha]["umbrales"] for e in ests if e.id_cha in aforos}
        return chj.lecturas_para(ests, aforos), vivos

    def f_avisos():
        salida, fallo = [], False
        for clave in ("cat", "val"):
            try:
                salida += [replace(a, region=clave) for a in avisos.parse_cap(avisos.bajar_cap(clave))]
            except FuenteError:
                fallo = True
        try:
            a = avisos.parse_inuncat(avisos.bajar_inuncat())
            if a:
                salida.append(replace(a, region="cat"))
        except FuenteError:
            fallo = True
        if fallo:
            raise FuenteError("avisos: alguna fuente falló; se conservan los últimos")
        return salida

    return {"aca": f_aca, "aca_ventana": f_ventana, "chj": f_chj, "avisos": f_avisos, "prevision": prevision.bajar}


def _paises_con_registro(dir_paises: str = DIR_PAISES) -> list[str]:
    try:
        carpetas = sorted(os.listdir(dir_paises))
    except OSError:
        return []
    return [c for c in carpetas if os.path.isfile(os.path.join(dir_paises, c, "estaciones.json"))]


def main() -> int:
    from estaciones import cargar
    ahora = datetime.now(timezone.utc).replace(microsecond=0)
    paises, fuentes_por_pais = {}, {}
    for pais in _paises_con_registro():
        try:
            paises[pais] = cargar(os.path.join(DIR_PAISES, pais, "estaciones.json"), pais)
            fuentes_por_pais[pais] = _fuentes_reales(pais)
        except Exception as exc:  # noqa: BLE001 - un registro roto no frena a los demás países
            print(f"{pais}: no se pudo cargar el registro: {exc!r}", file=sys.stderr)
    por_pais = ejecutar_todo(ahora, paises, fuentes_por_pais, DIR_DATA)
    for pais, cambios in por_pais.items():
        escribir_json(os.path.join(DIR_DATA, pais, "cambios.json"), cambios)
    # Un país que no corrió no puede dejar su cambios.json anterior: notificar lo reenviaría en cada ejecución.
    for pais in _paises_con_registro():
        if pais not in por_pais and os.path.isdir(os.path.join(DIR_DATA, pais)):
            escribir_json(os.path.join(DIR_DATA, pais, "cambios.json"), [])
    todos = [c for cs in por_pais.values() for c in cs]
    publicar = debe_publicar(todos, ahora, ultima_publicacion(DIR_DATA))
    if publicar:
        registrar_publicacion(DIR_DATA, ahora)
    print(f"{_iso(ahora)}: {len(todos)} cambios en {len(por_pais)}/{len(_paises_con_registro())} países, publicar={publicar}")
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"publicar={'true' if publicar else 'false'}\n")
    return 0 if por_pais else 1


if __name__ == "__main__":
    sys.exit(main())
