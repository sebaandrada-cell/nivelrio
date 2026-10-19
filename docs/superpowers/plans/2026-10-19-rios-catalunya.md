# Rius de Catalunya: plan de implementación

> **Para quien ejecute el plan:** usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans, tarea por tarea. Los pasos usan casillas `- [ ]`.

**Objetivo:** un panel estático con el estado de los ríos de Catalunya (y Valencia como contexto), con alertas propias de tres niveles y notificación, que se actualiza solo desde GitHub Actions.

**Arquitectura:** un cron de Actions ejecuta `fuente/actualizar.py`, que descarga ACA Sentilo, SAIH Júcar, AEMET e INUNCAT, normaliza a `Lectura`, evalúa la máquina de alertas y escribe JSON en `data/`. `index.html` es estático y lee `data/latest.json` por `fetch` del mismo origen, así que el cron solo commitea JSON (no reconstruye la página).

**Tecnología:** Python 3.11+ (el runner trae 3.12) con solo biblioteca estándar en ejecución; `pytest` solo para pruebas; JavaScript sin framework, `d3.min.js` ya incluido en el repo, `node --test` para la lógica de la página.

**Especificación:** `docs/superpowers/specs/2026-10-19-rios-catalunya-design.md`. Informe de fuentes: `Fuentes ríos Catalunya inundaciones.md` (no está en el repo; los datos que se usan están copiados abajo).

## Restricciones globales

- Todo timestamp se guarda y calcula en UTC, con zona (`datetime` consciente). Los de Sentilo (`dd/mm/yyyyThh:mi:ss`) se tratan como UTC.
- TLS siempre verificado. Prohibido `ssl.CERT_NONE`.
- Sin analítica de visitas: ni Clarity, ni Cloudflare, ni scripts de terceros. Solo `d3.min.js` local.
- Unidades internas: caudal en `m3s` (m³/s), nivel en `cm`. La ACA da el nivel en cm; Socrata `hprm-xuw7` lo da en m: convertir al leer.
- Una fuente que falla nunca frena a las demás: esa fuente queda en estado `SD` y se publica el resto.
- Cada nivel que se muestra lleva: edad del dato, fuente y rótulo `oficial` o `estimado`. Un nivel nunca se comunica solo con color.
- Pie permanente en la página (castellano): «Informativo. Datos provisionales sin validar. No sustituye a Protecció Civil. Siga siempre sus instrucciones.» Idioma por defecto castellano, selector a catalán.
- Créditos: «Hecho por Pablo Dodda. Adaptación para Catalunya: Sebastian Andrada. Licencia MIT.» Se conserva la licencia MIT y el aviso de copyright de Pablo Dodda.
- Nombre del sitio: «Rius de Catalunya». Rama de trabajo: `catalunya-rios`. Publicación en `sebaandrada-cell.github.io/nivelrio`.
- Constantes de la máquina de alertas (copiadas de la especificación): histéresis 85 % del umbral de entrada; bajada tras 3 lecturas consecutivas o 3 horas, un nivel por vez; escalada con 2 lecturas consecutivas; `SD` en la CHJ si la edad supera 25 min; `SD` en la ACA si la edad supera 3 veces el intervalo de muestreo (15 min con muestreo de 5 min).
- Commits con las líneas `Co-Authored-By` y `Claude-Session` que indica el entorno.

## Revisión de puntos ciegos

Entradas que la especificación no nombra y que un usuario real encontrará. Cada línea tiene su prueba en la tarea indicada.

1. **Observación vacía o `"NAN"` de un sensor ACA** (sensor sin lectura reciente): la estación queda `SD`, no rompe la ejecución ni se interpreta como 0. Tarea 2.
2. **Timestamp en el futuro** (reloj de la fuente adelantado): se trata como `SD`, no como dato fresco con edad negativa. Tarea 5.
3. **Umbrales CHJ nulos, cero o «en estudio»**: esa estación se muestra sin alerta propia y con la leyenda «umbral en estudio»; nunca N1 por comparar contra 0. Tarea 3.
4. **La CHJ cambia su HTML** (no aparece `let aforos = [`): `parse_aforos` lanza `FuenteError`, las estaciones CHJ quedan `SD` y las catalanas se publican igual. Tareas 3 y 7.
5. **Dos ejecuciones superpuestas o un commit concurrente**: el workflow usa `concurrency` sin cancelar y hace `git fetch` + `reset --hard origin/<rama>` antes de escribir; la escritura de JSON es atómica (archivo temporal + `os.replace`). Tareas 7 y 10.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `fuente/modelo.py` | `Lectura`, `Estacion`, `Umbrales`, `Aviso`, `FuenteError` |
| `fuente/estaciones.py` | cargar y validar `fuente/estaciones.json` |
| `fuente/estaciones.json` | catálogo de estaciones (datos, no código) |
| `fuente/fuentes/aca.py` | Sentilo: catálogo, último valor, ventana |
| `fuente/fuentes/chj.py` | CHJ: extraer el array `aforos` y normalizarlo |
| `fuente/fuentes/avisos.py` | AEMET CAP e INUNCAT |
| `fuente/alertas.py` | máquina de estados N0-N3 y SD |
| `fuente/umbrales.py` | umbrales estimados desde series históricas |
| `fuente/actualizar.py` | orquestación, persistencia atómica, política de publicación |
| `fuente/notificar.py` | redacta el issue de GitHub por cambio de nivel |
| `fuente/web/logica.js` | funciones puras de la página (formato, edad, rótulos) |
| `fuente/page.html` | página (diseño de Pablo, generalizado a estaciones) |
| `fuente/textos.json` | textos `es` y `ca` |
| `fuente/armar_sitio.py` | ensambla `index.html` desde `page.html` y `textos.json` |
| `fuente/herramientas/` | scripts manuales: calibrar umbrales, verificar estaciones |
| `.github/workflows/actualizar.yml` | cron cada 15 minutos |
| `tests/` | pruebas y `tests/fixtures/` |

## Tarea 1: Modelo y catálogo de estaciones

**Archivos:**
- Crear: `fuente/modelo.py`, `fuente/estaciones.py`, `fuente/estaciones.json`, `tests/test_estaciones.py`, `pytest.ini` (con `pythonpath = fuente`)

**Interfaces:**
- Produce (`modelo.py`):
  - `class FuenteError(Exception)`
  - `@dataclass(frozen=True) class Umbrales: bajo: float | None; medio: float | None; alto: float | None; tipo: str  # "oficial" | "estimado" | "en_estudio"`
  - `@dataclass(frozen=True) class Lectura: estacion_id: str; valor: float; unidad: str; t_utc: datetime; fuente: str`
  - `@dataclass(frozen=True) class Estacion: id: str; rio: str; nombre: str; cuenca: str; fuente: str; muestreo_min: int; umbrales: Umbrales; componente: str | None; id_cha: str | None`  (`componente` = código Sentilo, `id_cha` = `fldTCodigo` de la CHJ)
  - `@dataclass(frozen=True) class Aviso: origen: str; nivel: str; zona: str; descripcion: str; t_utc: datetime`  (`nivel` ∈ `"amarillo" "naranja" "rojo"`)
- Produce (`estaciones.py`): `cargar(ruta: str) -> list[Estacion]`. Lanza `ValueError` si hay ids repetidos, si `fuente` no es `"aca"` o `"chj"`, si una estación `aca` no trae `componente`, si una `chj` no trae `id_cha`, o si `umbrales` tiene `tipo` distinto de los tres válidos o valores no crecientes (`bajo < medio < alto`).

- [ ] **Paso 1: escribir las pruebas que fallan.** En `tests/test_estaciones.py`: `test_carga_catalogo_valido` (dos estaciones, una `aca` con `componente="082172-002"` y una `chj` con `id_cha="0O04"`; assert `len(...) == 2` y `e.umbrales.tipo == "estimado"` en la primera), `test_id_repetido_falla`, `test_aca_sin_componente_falla`, `test_umbrales_no_crecientes_falla`, `test_umbral_en_estudio_acepta_none` (con `tipo="en_estudio"` y los tres valores `None` no falla).
- [ ] **Paso 2: ejecutar** `python -m pytest tests/test_estaciones.py -v`. Esperado: FALLA por import (`modelo` no existe).
- [ ] **Paso 3: implementar** `modelo.py` y `cargar` con las firmas de arriba; `estaciones.json` empieza con la estación Sant Joan Despí (`id: "llobregat-sant-joan-despi"`, `componente: "082172-002"`, `muestreo_min: 5`, umbrales `tipo: "en_estudio"` con los tres valores `null`, hasta la tarea 11).
- [ ] **Paso 4: ejecutar** las pruebas. Esperado: PASAN.
- [ ] **Paso 5: commit** `feat: modelo y catálogo de estaciones`.

## Tarea 2: Cliente ACA Sentilo

**Archivos:**
- Crear: `fuente/fuentes/__init__.py`, `fuente/fuentes/aca.py`, `tests/test_aca.py`, `tests/fixtures/sentilo_data.json`, `tests/fixtures/sentilo_catalogo.json`

**Interfaces:**
- Consume: `Lectura`, `Estacion`, `FuenteError` (tarea 1).
- Produce:
  - `parse_ultimos(doc: dict) -> dict[str, tuple[float, datetime]]`: mapa `sensor_id -> (valor, t_utc)`. Ignora observaciones vacías, no numéricas o `"NAN"`.
  - `resolver_sensores(catalogo: dict, componente: str) -> tuple[str | None, str | None]`: devuelve `(sensor_caudal, sensor_nivel)` buscando por `component` y `type` (`"0014"` caudal, `"0019"` nivel).
  - `lecturas_para(estaciones: list[Estacion], ultimos: dict, catalogo: dict) -> list[Lectura]`: una `Lectura` de caudal (`unidad="m3s"`) por estación `aca`; si no hay caudal, usa el nivel en `cm`; si no hay ninguno, no devuelve lectura.
  - `bajar(url: str, abrir=urllib.request.urlopen, intentos: int = 3) -> dict`: JSON con `User-Agent` identificable, `timeout=30`, reintento con espera creciente; lanza `FuenteError` al agotar intentos.
  - `url_ventana(sensor: str, desde: datetime, hasta: datetime) -> str`: `URL_ULTIMOS + "/" + sensor + "?limit=30&from=dd/mm/yyyyThh:mi:ss&to=dd/mm/yyyyThh:mi:ss"` (fechas en UTC).
  - `parse_ventana(doc: dict) -> list[tuple[datetime, float]]`: observaciones de un solo sensor `[(t_utc, valor)]`, más nueva primero, ignorando vacías y `"NAN"`.
  - `URL_ULTIMOS = "https://aplicacions.aca.gencat.cat/sdim2/apirest/data/AFORAMENT-EST"`, `URL_CATALOGO = "https://aplicacions.aca.gencat.cat/sdim2/apirest/catalog?componentType=aforament"`

Las fixtures se guardan de respuestas reales: `curl` a las dos URLs y recortar a las estaciones de la tarea 11 más un sensor con observación vacía y otro con `"value": "NAN"`. Forma de `data`: `{"sensors":[{"sensor":"CALC001261","observations":[{"value":"40.492","timestamp":"19/10/2026T20:55:00","time":1792443300000}]}]}`.

- [ ] **Paso 1: pruebas que fallan.** `test_parse_ultimos_lee_valor_y_utc` (`CALC001261` → `40.492` y `datetime(2026,10,19,20,55,tzinfo=utc)`), `test_observacion_vacia_se_ignora`, `test_valor_nan_se_ignora`, `test_resolver_sensores_por_tipo` (`082172-002` → caudal `CALC001261`, nivel `082172-002-ANA010`), `test_estacion_sin_lectura_no_genera_lectura` (cubre el punto ciego 1), `test_bajar_reintenta_y_falla_con_fuenteerror` (opener falso que lanza `URLError` 3 veces), `test_url_ventana_formatea_fechas_utc` (`from=19/10/2026T18:00:00`), `test_parse_ventana_devuelve_pares_ordenados`.
- [ ] **Paso 2: ejecutar** `python -m pytest tests/test_aca.py -v`. Esperado: FALLA.
- [ ] **Paso 3: implementar** las funciones con esas firmas. Parseo de fecha con `datetime.strptime(s, "%d/%m/%YT%H:%M:%S").replace(tzinfo=timezone.utc)`.
- [ ] **Paso 4: ejecutar.** Esperado: PASAN.
- [ ] **Paso 5: commit** `feat: cliente ACA Sentilo`.

## Tarea 3: Cliente SAIH Júcar

**Archivos:**
- Crear: `fuente/fuentes/chj.py`, `tests/test_chj.py`, `tests/fixtures/chj_aforos.html` (recorte real con 3 estaciones, una con umbrales en 0)

**Interfaces:**
- Consume: `Lectura`, `Estacion`, `Umbrales`, `FuenteError`.
- Produce:
  - `extraer_array(html: str, nombre: str) -> list[dict]`: localiza `let <nombre> = [`, balancea corchetes respetando cadenas, y devuelve `json.loads` del array. Lanza `FuenteError` si no lo encuentra o no parsea.
  - `parse_aforos(html: str) -> dict[str, dict]`: mapa `fldTCodigo -> {"valor": float | None, "t_utc": datetime, "umbrales": Umbrales}` desde los campos `lastValue`, `fldDFechaComunicacion` (ISO UTC con `Z`), `fldFUmbralBajo/Medio/Alto`. Si algún umbral es `None`, `0` o no creciente, `Umbrales(None, None, None, "en_estudio")`; si no, `tipo="oficial"`.
  - `lecturas_para(estaciones: list[Estacion], aforos: dict[str, dict]) -> list[Lectura]`: caudal en `m3s` por estación `chj`.
  - `bajar_aforos(abrir=urllib.request.urlopen, intentos: int = 5) -> str`: GET `https://saih.chj.es/mapa-aforos` con reintentos (el servidor corta cerca de 1 de cada 3 conexiones).

- [ ] **Paso 1: pruebas que fallan.** `test_extrae_array_con_corchetes_en_cadenas`, `test_aforo_con_umbrales_validos_es_oficial` (Poyo N-III `0O04`: `30/70/150`), `test_umbrales_cero_son_en_estudio` (punto ciego 3), `test_sin_array_lanza_fuenteerror` (punto ciego 4), `test_fecha_iso_z_a_utc`.
- [ ] **Paso 2: ejecutar** `python -m pytest tests/test_chj.py -v`. Esperado: FALLA.
- [ ] **Paso 3: implementar.** El balanceo de corchetes se hace a mano porque la página es HTML, no JSON.
- [ ] **Paso 4: ejecutar.** Esperado: PASAN.
- [ ] **Paso 5: commit** `feat: cliente SAIH Júcar`.

## Tarea 4: Avisos AEMET e INUNCAT

**Archivos:**
- Crear: `fuente/fuentes/avisos.py`, `tests/test_avisos.py`, `tests/fixtures/cap_afac69.xml`, `tests/fixtures/inuncat.json`

**Interfaces:**
- Consume: `Aviso`, `FuenteError`.
- Produce:
  - `parse_cap(xml: str) -> list[Aviso]`: lee el feed RSS/Atom con `xml.etree.ElementTree`; mapea `Moderate/Severe/Extreme` a `amarillo/naranja/rojo`; ignora avisos caducados (`expires` anterior a ahora) y los de severidad menor.
  - `parse_inuncat(filas: list[dict]) -> Aviso | None`: del dataset `wj9c-j6vf`, solo filas con `PlaAcronim == "INUNCAT"`; `prealerta/alerta/emergència` → `amarillo/naranja/rojo`; vacío → `None`.
  - `URL_CAP = {"cat": ".../CAP_AFAC69_RSS.xml", "val": ".../CAP_AFAC77_RSS.xml"}` con el prefijo `https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/`; `URL_INUNCAT = "https://analisi.transparenciacatalunya.cat/resource/wj9c-j6vf.json"`.

Los nombres de columna del dataset INUNCAT y los campos exactos del CAP están sin verificar en el informe: el primer paso es descargar los dos documentos reales y guardarlos como fixtures.

- [ ] **Paso 1: descargar fixtures reales** con `curl` y revisar los nombres de campo. Si difieren, corregir esta tarea antes de seguir.
- [ ] **Paso 2: pruebas que fallan.** `test_cap_severe_es_naranja`, `test_cap_caducado_se_ignora`, `test_inuncat_vacio_devuelve_none`, `test_inuncat_alerta_es_naranja`, `test_cap_xml_roto_lanza_fuenteerror`.
- [ ] **Paso 3: ejecutar** `python -m pytest tests/test_avisos.py -v`. Esperado: FALLA.
- [ ] **Paso 4: implementar.**
- [ ] **Paso 5: ejecutar.** Esperado: PASAN. Commit `feat: avisos AEMET e INUNCAT`.

## Tarea 5: Máquina de alertas

**Archivos:**
- Crear: `fuente/alertas.py`, `tests/test_alertas.py`

**Interfaces:**
- Consume: `Estacion`, `Lectura`, `Umbrales`, `Aviso`.
- Produce:
  - `@dataclass(frozen=True) class Estado: nivel: int  # 0..3; sd: bool; ultimo_valor: float | None; ultimo_t_utc: datetime | None; cnt_sobre: int; cnt_bajo: int; bajo_desde: datetime | None; elevado_por_aviso: bool`
  - `ESTADO_INICIAL: Estado` (nivel 0, resto vacío)
  - `estado_a_dict(e: Estado) -> dict` y `estado_desde_dict(d: dict) -> Estado`: serialización a `data/state.json` (fechas en ISO con `Z`)
  - `VEL_SUBIDA_RAPIDA = 0.25`: fracción del umbral bajo por lectura que cuenta como subida rápida. **Valor propuesto, a calibrar con el historial.**
  - `evaluar(prev: Estado, lectura: Lectura | None, est: Estacion, ahora: datetime, aviso_rojo: bool = False) -> Estado`

Reglas que implementa `evaluar` (todas de la especificación):
- `SD` si no hay lectura, si `ahora - t_utc` supera el límite de la fuente (CHJ 25 min; ACA 3 × `muestreo_min`), o si `t_utc > ahora` (punto ciego 2). En `SD` se conserva `nivel` y `ultimo_valor`; solo `sd=True`.
- Nivel bruto: 1 si valor ≥ `bajo`; 2 si valor ≥ `medio` y la lectura anterior es menor; 3 si valor ≥ `alto`. Umbrales `None` ⇒ nivel bruto 0 y nunca alerta propia.
- Escalada: sube al nivel bruto tras 2 lecturas consecutivas en o sobre la entrada, o en una sola si `valor - ultimo_valor >= VEL_SUBIDA_RAPIDA * bajo`.
- Bajada: solo si el valor queda debajo del 85 % del umbral de entrada del nivel actual durante 3 lecturas consecutivas o 3 horas (`bajo_desde`), y baja un nivel cada vez. Cualquier lectura sobre ese 85 % reinicia los contadores.
- `aviso_rojo=True` fija `nivel = 3` y `elevado_por_aviso = True`, también si la estación está en `SD`. En la fase 1 el orquestador lo activa solo cuando INUNCAT está en `alerta` o `emergència`, para todas las estaciones catalanas (los avisos de AEMET y Meteocat se muestran, pero no elevan, porque sus zonas no están cruzadas con las comarcas; ver «Pendientes de la fase 2»).

- [ ] **Paso 1: pruebas que fallan.** Casos con umbrales `10/20/40` y `muestreo_min=5`:
  - `test_subida_lenta_pasa_por_n1_con_dos_lecturas`: valores `[9, 11, 12]` → niveles `[0, 0, 1]`.
  - `test_pico_de_una_lectura_escala_si_es_rapido`: `[1, 14]` → nivel 1 en la segunda (subida ≥ 2,5).
  - `test_oscilacion_en_el_umbral_no_parpadea`: `[11, 9, 11, 9, 11, 9]` desde N1 se mantiene en nivel 1 (punto de la histéresis; el 85 % de 10 es 8,5).
  - `test_bajada_escalonada`: desde N3, valores bajo el 85 % del umbral alto durante 3 lecturas → N2, nunca N0 directo.
  - `test_sd_en_n3_mantiene_alerta`: lectura de hace 40 min con ACA 5 min → `sd=True`, `nivel` sigue en 3.
  - `test_aviso_rojo_con_sd_escala_a_n3`.
  - `test_timestamp_futuro_es_sd` (punto ciego 2).
  - `test_umbrales_none_nunca_alertan`.
  - `test_estado_ida_y_vuelta_a_dict`.
  - `test_chj_sd_a_los_26_minutos_y_no_a_los_24`.
- [ ] **Paso 2: ejecutar** `python -m pytest tests/test_alertas.py -v`. Esperado: FALLA.
- [ ] **Paso 3: implementar `evaluar`** con las reglas de arriba, función pura sin E/S.
- [ ] **Paso 4: ejecutar.** Esperado: PASAN.
- [ ] **Paso 5: commit** `feat: máquina de alertas N0-N3 y SD con histéresis`.

## Tarea 6: Umbrales estimados

**Archivos:**
- Crear: `fuente/umbrales.py`, `fuente/herramientas/calibrar_umbrales.py`, `tests/test_umbrales.py`

**Interfaces:**
- Consume: `Umbrales`.
- Produce: `estimar(caudales_diarios_m3s: list[float]) -> Umbrales`: aproxima T≈2, T≈5 y T≈20 años con el máximo anual de la serie diaria: `bajo` = mediana de los máximos anuales, `medio` = percentil 80, `alto` = percentil 95; `tipo="estimado"`. Lanza `ValueError` con menos de 5 años completos. Sesgo conocido: las medias diarias subestiman los picos; la herramienta lo imprime.
- El script `calibrar_umbrales.py` descarga `hprm-xuw7` filtrando por estación (SoQL por `dia`, pedir por año: las consultas grandes agotan el tiempo), llama a `estimar` y reescribe los umbrales de `estaciones.json`. Es manual, no se ejecuta en el cron.

- [ ] **Paso 1: pruebas que fallan.** `test_estimar_serie_sintetica` (20 años con máximos 1..20 → `bajo=10.5`, `medio` y `alto` crecientes), `test_menos_de_cinco_anios_falla`, `test_resultado_es_estimado`.
- [ ] **Paso 2: ejecutar** `python -m pytest tests/test_umbrales.py -v`. Esperado: FALLA.
- [ ] **Paso 3: implementar `estimar`** con `statistics.quantiles`. El script se escribe sin prueba automática (usa red) y se verifica a mano en la tarea 11.
- [ ] **Paso 4: ejecutar.** Esperado: PASAN. Commit `feat: umbrales estimados desde la serie histórica`.

## Tarea 7: Orquestador y persistencia

**Archivos:**
- Crear: `fuente/actualizar.py`, `tests/test_actualizar.py`
- Datos que escribe: `data/latest.json`, `data/state.json`, `data/avisos.json`, `data/history/AAAA-MM.json`

**Interfaces:**
- Consume: todo lo anterior.
- Produce:
  - `escribir_json(ruta: str, obj) -> None`: archivo temporal en el mismo directorio y `os.replace` (atómica).
  - `ejecutar(ahora: datetime, estaciones: list[Estacion], fuentes: dict, dir_data: str) -> list[Cambio]`, donde `fuentes` es `{"aca": callable, "aca_ventana": callable(sensor, desde, hasta), "chj": callable, "avisos": callable}` (inyectables para pruebas) y `Cambio = {"estacion_id", "nivel_antes", "nivel_despues", "sd", "elevado_por_aviso"}`.
  - `debe_publicar(cambios: list[Cambio], ahora: datetime) -> bool`: verdadero si hay algún cambio de nivel o de `sd`, o si `ahora.minute < 15` (primera ejecución de cada hora).
  - `main()`: lee `fuente/estaciones.json`, llama a `ejecutar`, escribe `data/` y `GITHUB_OUTPUT` con `publicar=true|false` y el JSON de cambios en `data/cambios.json`.
- Formato de `latest.json`: `{"generado_utc": iso, "estaciones": [{"id", "rio", "nombre", "cuenca", "valor", "unidad", "t_utc", "edad_min", "nivel": 0-3, "sd": bool, "umbrales": {"bajo","medio","alto","tipo"}, "elevado_por_aviso": bool, "fuente"}], "avisos": [{"origen","nivel","zona","descripcion","t_utc"}], "fuentes_ok": {"aca": bool, "chj": bool, "avisos": bool}}`.
- El historial guarda, por estación y por hora, el valor máximo observado: `{"<estacion_id>": [["2026-10-19T20:00:00Z", 40.49], ...]}`.

- [ ] **Paso 1: pruebas que fallan.** `test_fuente_que_falla_no_frena_a_las_demas` (la fuente `chj` lanza `FuenteError`: las estaciones CHJ quedan `sd=True` y las ACA tienen nivel; punto ciego 4), `test_cambio_de_nivel_se_reporta`, `test_debe_publicar_solo_si_cambia_o_es_hora_en_punto` (casos: sin cambios a las 20:20 → falso; sin cambios a las 20:05 → verdadero; con cambio a las 20:20 → verdadero), `test_historial_guarda_maximo_horario`, `test_escritura_atomica_no_deja_archivo_a_medias` (simula excepción entre escribir el temporal y `os.replace`; el archivo original sigue íntegro; punto ciego 5), `test_inuncat_en_alerta_eleva_estaciones_catalanas_pero_no_las_valencianas`, `test_ventana_solo_para_estaciones_cerca_del_umbral` (con `fuentes["aca_ventana"]` falso: se llama solo para estaciones con nivel ≥ 1 o valor ≥ 80 % del umbral `bajo`, y el máximo de la ventana sustituye al último valor al evaluar).
- [ ] **Paso 2: ejecutar** `python -m pytest tests/test_actualizar.py -v`. Esperado: FALLA.
- [ ] **Paso 3: implementar.** Cada fuente se llama dentro de `try/except FuenteError`; el error se registra en `fuentes_ok`.
- [ ] **Paso 4: ejecutar.** Esperado: PASAN.
- [ ] **Paso 5: commit** `feat: orquestador de actualización y persistencia`.

## Tarea 8: Notificación por issue de GitHub

**Archivos:**
- Crear: `fuente/notificar.py`, `tests/test_notificar.py`

**Interfaces:**
- Consume: `Cambio` (tarea 7).
- Produce:
  - `redactar_issue(cambio: dict, estacion_nombre: str, rio: str, valor: float | None, unidad: str, edad_min: int | None) -> tuple[str, str]`: `(titulo, cuerpo)` en castellano. Título: `"{rio} · {nombre}: nivel N2 (Aviso)"` o `"... sin datos"`. Cuerpo: valor, edad del dato, fuente, rótulo oficial o estimado, y el pie «Informativo... Siga siempre las instrucciones de Protecció Civil».
  - `main()`: lee `data/cambios.json` y `data/latest.json`, y por cada cambio ejecuta `gh issue create --title ... --body ...` (necesita `GH_TOKEN`). Solo notifica subidas de nivel y entradas en `SD` de estaciones en N2 o N3; las bajadas no crean issue.

- [ ] **Paso 1: pruebas que fallan.** `test_titulo_incluye_nivel_y_rio`, `test_cuerpo_incluye_edad_y_pie`, `test_sd_en_n3_menciona_ultimo_dato`.
- [ ] **Paso 2: ejecutar** `python -m pytest tests/test_notificar.py -v`. Esperado: FALLA.
- [ ] **Paso 3: implementar.**
- [ ] **Paso 4: ejecutar.** Esperado: PASAN. Commit `feat: notificación por issue`.

## Tarea 9: Lógica y página web

**Archivos:**
- Crear: `fuente/web/logica.js`, `tests/web/logica.test.js`, `fuente/textos.json`, `tests/test_pagina.py`
- Reemplazar: `fuente/page.html` (se conserva el sistema de variables CSS y los componentes visuales de Pablo; se elimina todo lo de Resistencia)
- Modificar: `fuente/armar_sitio.py` (ensambla `index.html` desde `page.html`, `textos.json`, `web/logica.js`; ya no incrusta datos ni genera `og.png`)

**Interfaces:**
- Produce (`logica.js`, exporta con `module.exports` y también expone `window.Logica`):
  - `edadTexto(minutos: number, lang: "es"|"ca"): string`: `"hace 7 min"`, `"hace 3 h 10 min"`, `"hace 2 d"`.
  - `nivelRotulo(nivel: 0|1|2|3, sd: boolean, lang): {texto: string, simbolo: string}`: p. ej. `{texto: "Aviso", simbolo: "▲"}`; `sd` devuelve `"Sin datos"`.
  - `ordenarPorPeligro(estaciones): array`: por nivel descendente, luego `sd`, luego río.
  - `tipoUmbralTexto(tipo: "oficial"|"estimado"|"en_estudio", lang): string` (`"estimado, no oficial"`, `"umbral en estudio"`).
  - `idiomaInicial(search: string, guardado: string | null): "es"|"ca"`: `?lang=ca` manda sobre lo guardado; por defecto `"es"`.
- La página (`page.html`) hace `fetch("data/latest.json", {cache: "no-store"})` cada 5 minutos y renderiza: resumen (conteo por nivel y avisos oficiales vigentes con fuente y hora), una tarjeta por río con su estación más relevante, y detalle por estación con gráfico de d3 de los datos de `data/history/` con líneas de umbral. Si `fuentes_ok` marca una fuente caída, muestra un banner. El pie y los créditos salen de `textos.json`. `localStorage` solo se usa dentro de `try/catch` para recordar el idioma.

- [ ] **Paso 1: pruebas que fallan.** En `logica.test.js` (con `node:test`): `edadTexto(7,"es") === "hace 7 min"`, `edadTexto(190,"es") === "hace 3 h 10 min"`, `nivelRotulo(2,false,"es").texto === "Aviso"`, `nivelRotulo(3,true,"es").texto === "Sin datos"`, `ordenarPorPeligro` (caso explícito: entrada `[N0, N3, N1]` → salida `[N3, N1, N0]`; a igual nivel, las estaciones con `sd` van después de las que tienen dato), `idiomaInicial("?lang=ca","es") === "ca"`, `idiomaInicial("", null) === "es"`. En `test_pagina.py`: `test_index_sin_analitica` (el HTML armado no contiene `clarity.ms`, `cloudflareinsights` ni `static.cloudflare`), `test_pie_en_es_y_ca` (`textos.json` tiene la clave del pie en ambos idiomas y contiene «Protecció Civil»), `test_creditos_incluyen_a_ambos_autores` (contiene «Pablo Dodda» y «Sebastian Andrada»), `test_scripts_pasan_node_check`, `test_nivel_no_depende_solo_del_color` (cada rótulo de nivel tiene `simbolo`).
- [ ] **Paso 2: ejecutar** `node --test tests/web/` y `python -m pytest tests/test_pagina.py -v`. Esperado: FALLAN.
- [ ] **Paso 3: implementar** `logica.js`, `textos.json` (es y ca) y `page.html`; adaptar `armar_sitio.py`.
- [ ] **Paso 4: ejecutar** las dos órdenes. Esperado: PASAN. Abrir `index.html` con un `data/latest.json` de ejemplo y revisar a ojo en ancho de móvil y de escritorio, modo claro y oscuro.
- [ ] **Paso 5: commit** `feat: página con estaciones, idiomas es/ca y sin analítica`.

## Tarea 10: Workflow y publicación

**Archivos:**
- Crear: `.github/workflows/actualizar.yml`

**Interfaces:**
- Consume: `python fuente/actualizar.py` (escribe `GITHUB_OUTPUT`: `publicar`), `python fuente/notificar.py`.

El workflow: `on: schedule: cron "*/15 * * * *"` y `workflow_dispatch`; `permissions: contents: write, issues: write`; `concurrency: {group: actualizar, cancel-in-progress: false}`; pasos: `actions/checkout@v4` de la rama por defecto, `python fuente/actualizar.py`, si `publicar == 'true'` commit de `data/` con el usuario `rius-bot` y `git fetch` + `git rebase`/reintento antes de `git push` (hasta 3 intentos), y `python fuente/notificar.py` con `GH_TOKEN`. Los tres pasos de red tienen `timeout-minutes` y un fallo del script no deja el commit a medias.

- [ ] **Paso 1: validar** el YAML con `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/actualizar.yml'))"` (instalar `pyyaml` si falta) o con `actionlint` si está disponible. Esperado: sin errores.
- [ ] **Paso 2: ejecución manual en el runner real.** Tras fusionar a la rama de prueba, lanzar `workflow_dispatch` y revisar el registro: confirma que ACA, CHJ y AEMET responden desde GitHub Actions (hoy es una inferencia) y que se publicó `data/latest.json`.
- [ ] **Paso 3: commit** `ci: workflow de actualización cada 15 minutos`.

## Tarea 11: Estaciones reales y verificación contra las APIs

**Archivos:**
- Modificar: `fuente/estaciones.json`
- Crear: `fuente/herramientas/verificar_estaciones.py`

**Interfaces:**
- Consume: `aca.resolver_sensores`, `chj.parse_aforos`, `umbrales.estimar`.
- `verificar_estaciones.py` descarga el catálogo y los últimos valores de Sentilo y la página de la CHJ, y para cada estación de `estaciones.json` imprime si el `componente` o el `id_cha` existen, qué sensores resuelve, el valor actual y su edad. Sale con código distinto de 0 si alguna estación no se resuelve.

Estaciones (`componente` de Sentilo; todas con `muestreo_min` leído del catálogo, 5 por defecto):

| Río | Estaciones |
|---|---|
| Llobregat | Sant Joan Despí `082172-002`, Sant Vicenç dels Horts `082634-001`, Castellbisbal `080543-002`, Castellbell `080538-005`, Guardiola `080996-007` |
| Cardener | Cardona `080478-006`, Súria `082747-007` |
| Anoia | Sant Sadurní `082401-002`, Martorell `081141-002` |
| Besòs | Santa Coloma `082457-001` |
| Ter | Girona `170792-002`, Colomers `170558-002`, Roda de Ter `081831-003`, Torroella `171997-002` (funcionalidad limitada) |
| Fluvià | Esponellà `170656-005`, Olot `171143-002` |
| Muga | Pont de Molins `171352-003`, Castelló d'Empúries `170470-003`, Sant Llorenç `171714-001` |
| Tordera | Fogars de la Selva `080826-002`, Sant Celoni `082021-001` |
| Francolí | Montblanc `430862-001`, Tarragona `431482-004` |
| Gaià | Vilabella `431652-001` |
| Foix | Castellet i la Gornal `080581-003` |
| Túria (CHJ, `id_cha`) | Manises `0R06`, Quart de Poblet `0E02`, Vilamarxant `0O03`, Bugarra `0A01` |
| Xúquer (CHJ) | Algemesí `7A02`, salida de Tous `7E04` |
| Poyo (CHJ) | N-III `0O04` (único punto, aguas arriba de Paiporta y Torrent) |

- [ ] **Paso 1: completar `estaciones.json`** con esas estaciones. Las catalanes empiezan con `umbrales.tipo = "en_estudio"` y `null`; los umbrales de la CHJ vienen en vivo de la página.
- [ ] **Paso 2: ejecutar** `python fuente/herramientas/verificar_estaciones.py`. Esperado: código 0 y una línea por estación con valor y edad. Corregir cualquier `componente` que no resuelva.
- [ ] **Paso 3: ejecutar** `python fuente/herramientas/calibrar_umbrales.py` y revisar a mano que los umbrales estimados sean plausibles (caudal `bajo` mayor que cero y por debajo de caudales de crecida conocidos); la equivalencia ACA–Socrata se valida comparando un valor actual de Sentilo contra la última fila diaria de `hprm-xuw7` antes de aceptar los umbrales de esa estación. Las estaciones sin serie utilizable se quedan en `en_estudio`.
- [ ] **Paso 4: ejecutar** `python -m pytest -v`. Esperado: todo pasa.
- [ ] **Paso 5: commit** `feat: catálogo real de estaciones y verificación`.

## Tarea 12: Limpieza del heredado, documentación y créditos

**Archivos:**
- Borrar: `.github/workflows/zscaler-iac-scan.yml`, `.github/workflows/altura_horaria.yml`, `CNAME`, `fuente/agp_update.py`, `fuente/sat_s2.py`, `fuente/sat_update.py`, `fuente/og.py`, `fuente/build_public.py`, `ACTUALIZAR.md`, `fuente/data/` (los JSON del Paraná y `og.png`)
- Modificar: `README.md`, `LICENSE`

El `README.md` se reescribe en castellano (breve, en un estilo humano y directo): qué es el panel, de dónde salen los datos (con atribución a ACA, SAIH CHJ, AEMET, Protecció Civil/INUNCAT), qué significa cada nivel y cuáles son oficiales y cuáles estimados, los límites (4 ríos sin feed, cuencas rápidas, no sustituye a Protecció Civil), cómo ejecutar las pruebas y el cron, y los créditos: «Hecho por Pablo Dodda. Adaptación para Catalunya: Sebastian Andrada. Licencia MIT.» En `LICENSE` se agrega una segunda línea de copyright para Sebastian Andrada, sin quitar la de Pablo Dodda.

- [ ] **Paso 1: borrar** los archivos de la lista con `git rm` y confirmar que `grep -ri "clarity\|cloudflare\|resistencia\|paraná\|barranqueras\|apuratejose" --exclude-dir=.git --exclude-dir=docs .` no devuelve nada fuera de `docs/` y de los créditos del README (el crédito a Pablo menciona su proyecto original por nombre).
- [ ] **Paso 2: ejecutar** `python -m pytest -v && node --test tests/web/`. Esperado: todo pasa.
- [ ] **Paso 3: reescribir** `README.md` y actualizar `LICENSE`.
- [ ] **Paso 4: activar GitHub Pages** para la rama de publicación (ajuste del repo; lo hace Sebastian o se le pide permiso) y comprobar que carga `sebaandrada-cell.github.io/nivelrio`.
- [ ] **Paso 5: commit** `chore: quitar lo específico del Paraná y documentar el proyecto`.

---

## Antes de fusionar a `main`

El repo de Sebastian ejecuta hoy el robot del Paraná sobre `main`. Este plan trabaja en `catalunya-rios` y no toca `main`. Para fusionar: primero la tarea 12 (que borra `altura_horaria.yml`), después la fusión; si se fusionara en otro orden, el robot seguiría escribiendo datos del Paraná sobre el sitio nuevo.

## Antes de publicar de forma amplia

Gestiones que no son código y que condicionan la difusión del sitio: leer la página de licencias de la Generalitat (el campo de ACA solo dice «ver términos de uso»), escribir a ACA y a la CHJ pidiendo permiso de reutilización (la CHJ no declara licencia ni prohíbe el uso), y revisar que cada fuente tenga su atribución visible en la página.

## Pendientes de la fase 2 (fuera de este plan)

Segre, Ebre, Noguera Pallaresa y Noguera Ribagorçana (probar `saihebro.com` desde el runner y pedir acceso a la CHE), tabla oficial de umbrales a ACA o Protecció Civil, API de Meteocat con clave, cruce de las zonas de aviso de AEMET con las comarcas (para que un aviso rojo eleve solo las estaciones de su zona), GloFAS vía Open-Meteo y reservas `gn9e-3qhr` como contexto.
