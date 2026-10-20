# Nivel Río multipaís — plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans. Los pasos usan casillas `- [ ]`.

**Objetivo:** convertir el panel de ríos de Catalunya en una web única con pestañas por país (Argentina, España, EE. UU.), sumando lo mejor de `apuratejose` de Pablo Dodda.

**Arquitectura:** el motor de niveles (`alertas.evaluar`) pasa a ser agnóstico de la unidad; cada país tiene su registro de estaciones y sus datos en `data/<pais>/`; cada fuente es un adaptador que devuelve `(lecturas, umbrales_vivos)`; la página carga solo el país de la pestaña activa (`#ar|#es|#us`). El orquestador aísla fallos por país y por fuente.

**Stack:** Python 3.12 solo biblioteca estándar (Pillow y rasterio solo en el robot de satélite y la tarjeta, opcionales), JS sin build (`web/logica.js` + `page.html` + d3 local), pytest, `node --test`, GitHub Actions y Pages.

**Spec:** `docs/superpowers/specs/2026-10-20-multipais-design.md`. Base: rama `catalunya-rios` (162 pytest + 16 node verdes). Código de Pablo en `/home/claude/apuratejose` (clonar de nuevo desde `github.com/pablododda/apuratejose` si falta).

## Restricciones globales
- Solo biblioteca estándar en `fuente/` salvo `satelite.py` y `og.py` (Pillow/rasterio, instalación perezosa y con salida limpia si faltan).
- Sin analítica ni fuentes externas en la página. Créditos: «Hecho por Pablo Dodda. Adaptación multipaís: Sebastian Andrada. Licencia MIT.»
- Idiomas es, ca, en con las mismas claves (la prueba de paridad de `test_pagina.py` cubre los tres).
- Etiqueta de umbral siempre honesta: `oficial`, `estimado` (con `regla`) o `en_estudio`.
- Unidad tal como la publica la fuente: `m3s` y `m` (España, Argentina), `ft` (EE. UU.). No se convierte.
- La previsión (lluvia, caudal esperado, pronóstico NWS) nunca cambia un nivel ni dispara un aviso.
- Umbrales: N1=`bajo`, N2=`medio`, N3=`alto`. Argentina: N2=`nivel_alerta`, N3=`nivel_evacuacion`, N1=0,9×`nivel_alerta` (regla propia, etiquetada). EE. UU.: N1=`action`, N2=`minor`, N3=`moderate`. Barranqueras usa los niveles locales de la APA Chaco: N1=5,5 m, N2=6,0 m, N3=6,5 m.
- Commits con `git -c user.name="Claude" -c user.email="noreply@anthropic.com" commit` (los `-c` antes de `commit`) y los trailers `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_0134gaFy4k1jauFUrrGbWT38`.
- Verificación de cada tarea: `python3 -m pytest -q` y `node --test "tests/web/*.test.js"`. Rama de trabajo: `multipais`.
- La red del entorno de desarrollo solo llega a lo permitido: para verificar una API real se usa WebFetch y se guarda un recorte como fixture en `tests/fixtures/`. No inferir nombres de campos que no se hayan visto en una respuesta real.

## Foco de revisión
1. Una estación diaria (INA, 1 valor por día) no puede quedar en «sin datos» ni tardar dos días en subir de nivel. Test en T1.
2. Un país con la fuente caída, o que lanza una excepción rara, no puede borrar ni congelar los datos de los otros. Test en T2.
3. Estaciones en pies o metros no deben pasar por reglas pensadas para m³/s (subida rápida, previsión de caudal GloFAS, etiqueta «Podría llegar a»). Tests en T1 y T2.
4. Primera ejecución con ríos ya en N3 (Barranqueras y Corrientes hoy): se avisa una vez por estación y no se repite en las ejecuciones siguientes. Test en T2.
5. Una pestaña o URL con país desconocido, o un país sin datos todavía, muestra un mensaje claro y no una página rota. Test en T7.

---

### Tarea 1: Modelo y motor agnósticos de la unidad

**Archivos:**
- Modificar: `fuente/modelo.py`, `fuente/estaciones.py`, `fuente/alertas.py`, `tests/conftest.py`
- Crear: `fuente/paises/es/estaciones.json` (movido con `git mv` desde `fuente/estaciones.json`), `fuente/herramientas/migrar_estaciones.py` (script de un solo uso, no se conserva tras la migración)
- Pruebas: `tests/test_alertas.py`, `tests/test_estaciones.py`

**Interfaces:**
- Produce `Estacion` con campos nuevos: `pais: str`, `magnitud: str` (`"caudal"|"altura"`), `unidad: str` (`"m3s"|"m"|"ft"`), `ref: str | None` (id en la fuente: INA `estacion_id`, USGS `site`), `lid: str | None` (NWS), `vel_subida_rapida: float | None`.
- Produce `estaciones.cargar(ruta: str, pais: str) -> list[Estacion]`, con `FUENTES = ("aca","chj","ina","agp","usgs")`, `PAISES = ("ar","es","us")` y `ZONAS: dict[str, tuple[str,...]]` por país (`es`: las 5 actuales; `ar`: `chaco-corrientes`, `litoral-parana`, `uruguay`; `us`: `mississippi`, `missouri-ohio`, `red-river`).
- Produce `alertas.limite_sd(est) -> timedelta` (público): CHJ 25 min; muestreo ≥ 1440 → 2×muestreo; resto 3×muestreo.
- `Lectura.unidad` pasa a ser cualquier cadena; `evaluar` compara `lectura.unidad == est.unidad` (antes `== "m3s"`).
- `vel_subida_rapida` efectiva: el valor de la estación, o `VEL_SUBIDA_RAPIDA * umbrales.bajo` si `magnitud == "caudal"`, o desactivada (None) si es `altura`.
- Estación con `muestreo_min >= 1440` confirma la subida con 1 lectura (`lecturas_para_subir = 1`).

- [ ] **Paso 1: escribir los tests que fallan**
  - `test_estacion_en_metros_usa_su_unidad`: `make_estacion(magnitud="altura", unidad="m", umbrales=Umbrales(5.5,6.0,6.5,"oficial"))`, lectura `unidad="m"` valor 6.1 sin historial → nivel 2; con lectura `unidad="m3s"` → `sd=True`.
  - `test_altura_no_usa_subida_rapida`: estación `altura`, lecturas 5.0 y luego 6.6 (salto grande, una sola lectura sobre N3) → sube a N3 solo tras la segunda lectura; la misma secuencia en `caudal` con salto ≥ 0,25×bajo sube de inmediato (comportamiento actual).
  - `test_estacion_diaria_sube_con_una_lectura`: `muestreo_min=1440`, lecturas con 24 h de diferencia, 5.0 → 6.2 con `bajo=5.5, medio=6.0, alto=6.5` → N2 en la segunda lectura.
  - `test_estacion_diaria_no_cae_en_sd_a_las_30_horas` y `..._si_en_sd_a_las_50_horas`: usa `alertas.limite_sd`.
  - `test_cargar_exige_pais_y_zona_del_pais`: zona de otro país → `ValueError`; `fuente="ina"` sin `ref` → `ValueError`; `fuente="usgs"` sin `ref` o sin `lid` → `ValueError`; `magnitud` inválida → `ValueError`.
  - `test_registro_es_migrado_conserva_32_estaciones`: `cargar("fuente/paises/es/estaciones.json","es")` devuelve 32 con `unidad=="m3s"` y `magnitud=="caudal"`.
- [ ] **Paso 2: ejecutar y comprobar que fallan** — `python3 -m pytest -q tests/test_alertas.py tests/test_estaciones.py`. Esperado: FAIL por campos/funciones inexistentes.
- [ ] **Paso 3: implementar** — campos en `modelo.py`; validación por país en `estaciones.py`; en `alertas.evaluar` reemplazar el literal `"m3s"` por `est.unidad`, calcular `vel` y `lecturas_para_subir` como arriba, y publicar `limite_sd`. Script de migración: añade `pais:"es"`, `magnitud:"caudal"`, `unidad:"m3s"` a cada estación, escribe el archivo nuevo con el mismo formato (`indent=2`), y se borra. Actualizar `make_estacion` con los defaults `pais="es", magnitud="caudal", unidad="m3s", ref=None, lid=None, vel_subida_rapida=None` y las rutas de carga en `actualizar.py`/`verificar_estaciones.py` a `paises/es/`.
- [ ] **Paso 4: verde** — ambas suites completas; los 162 + 16 previos siguen pasando.
- [ ] **Paso 5: commit** — `feat: modelo y motor agnósticos de la unidad; registro de estaciones por país`.

### Tarea 2: Orquestador multipaís y avisos por país

**Archivos:**
- Modificar: `fuente/actualizar.py`, `fuente/notificar.py`, `.github/workflows/actualizar.yml` (solo si cambia algo), `tests/test_actualizar.py`, `tests/test_notificar.py`, `tests/test_workflow.py`
- Mover: `data/{latest,state,avisos,cambios,prevision}.json` y `data/history/` → `data/es/` (con `git mv`)
- Crear: `data/paises.json` (índice) lo escribe el orquestador

**Interfaces:**
- Consume: `ejecutar(ahora, estaciones, fuentes, dir_data) -> list[dict]` de hoy, sin cambiar su firma. `fuentes` pasa a aceptar claves opcionales `"avisos"` y `"prevision"`; si faltan, no hay avisos ni previsión y `fuentes_ok` no las incluye.
- Produce `ejecutar_todo(ahora, paises: dict[str, list[Estacion]], fuentes_por_pais: dict[str, dict], raiz_data: str) -> dict[str, list[dict]]`: llama a `ejecutar` con `dir_data = raiz_data/<pais>`; cualquier `Exception` de un país se registra (`print` a stderr) y se continúa; escribe `raiz_data/paises.json` = `{pais: {"generado_utc", "estaciones": N, "por_nivel": [n0,n1,n2,n3], "sd": N, "fuentes_ok": {...}}}` con los países que corrieron bien (los demás conservan su entrada anterior).
- `latest.json` filas: `"unidad": est.unidad`, `"pais"`; `_puede_llegar` y el modelo GloFAS solo para `magnitud == "caudal"`; el historial guarda lecturas cuya unidad sea la de la estación.
- `notificar.main` recorre `data/<pais>/cambios.json` de todos los países; título del issue con el código de país; `UNIDADES` añade `m` y `ft`; `FUENTES` añade `ina`, `agp`, `usgs`; el pie por país (`es`: Protecció Civil; `ar`: Protección Civil y el INA; `us`: weather.gov); `SITIO` configurable por variable de entorno `SITIO` con el valor actual por defecto, y el enlace termina en `#<pais>`.
- `debe_publicar`, `ultima_publicacion`, `registrar_publicacion` quedan globales (`data/meta.json`).

- [ ] **Paso 1: tests que fallan**
  - `test_un_pais_roto_no_frena_a_los_demas`: el país `ar` lanza `RuntimeError` desde su fuente; `es` escribe sus archivos; `ar` conserva los suyos intactos.
  - `test_pais_sin_avisos_ni_prevision_no_los_pide`: fuentes sin esas claves; `fuentes_ok` solo tiene `ina`.
  - `test_altura_no_genera_puede_llegar`: estación `altura` con previsión de caudal que superaría su N3 → `puede_llegar is None`.
  - `test_primera_ejecucion_avisa_una_vez`: dos estaciones nuevas, una ya en N3, otra en N0; primera ejecución → un cambio; segunda con los mismos datos → ninguno.
  - `test_indice_de_paises`: `paises.json` tiene el conteo por nivel correcto.
  - `test_notificar_recorre_todos_los_paises` y `test_issue_incluye_pais_y_unidad_en_pies`.
  - `test_workflow`: el workflow sigue haciendo `git add data` (cubre `data/<pais>/`).
- [ ] **Paso 2: RED** — `python3 -m pytest -q tests/test_actualizar.py tests/test_notificar.py tests/test_workflow.py`.
- [ ] **Paso 3: implementar** según Interfaces. `main()` arma `paises` con `estaciones.cargar("fuente/paises/<pais>/estaciones.json", pais)` para cada carpeta que exista, y `_fuentes_reales(pais)` (ver T6). Devuelve 0 salvo que fallen **todos** los países.
- [ ] **Paso 4: verde** — ambas suites.
- [ ] **Paso 5: commit** — `feat: orquestador multipaís con aislamiento por país`.

### Tarea 3: Adaptador INA (Argentina)

**Archivos:** Crear `fuente/fuentes/ina.py`, `tests/test_ina.py`, `tests/fixtures/ina_estaciones.json` (recorte de la respuesta real del 2026-10-20 con Barranqueras, Corrientes, Paraná, Rosario, Santa Fe y Concordia, más una entrada sintética `TEST-SIN-VALOR` con `valor_actual: null`).

**Interfaces:**
- Produce `ina.URL = "https://www.hidraulica.gob.ar/ina/ajax.estaciones.json.php"`, `ina.bajar(abrir=..., intentos=3, dormir=...) -> list[dict]` (usa `red.get_texto`; JSON roto → `FuenteError`), `ina.parse(filas) -> dict[str, dict]` (clave: `estacion_id` como texto; valores: `{"valor": float, "t_utc": datetime, "umbrales": Umbrales}`), `ina.umbrales(fila) -> Umbrales` y `ina.lecturas_para(estaciones, parseadas) -> list[Lectura]` (`unidad="m"`, `fuente="ina"`).
- Campos reales de la fila: `estacion_id, nombre, lat, lng, nivel_alerta, nivel_evacuacion, nivel_aguas_bajas, valor_actual, fecha_actual ("20/10/2026 00:00", hora de Argentina UTC‑3), delta, tendencia, vigente, situacion`.

- [ ] **Paso 1: tests que fallan**
  - `test_umbrales_barranqueras`: alerta 6, evacuación 6.5 → `Umbrales(5.4, 6.0, 6.5, "oficial")` (N1=0,9×6).
  - `test_umbrales_incoherentes_son_en_estudio`: alerta ≥ evacuación o alguno nulo → `en_estudio`.
  - `test_fecha_se_convierte_a_utc`: `20/10/2026 00:00` → `2026-10-20T03:00:00Z`.
  - `test_fila_sin_valor_no_genera_lectura`, `test_vigente_false_no_genera_lectura`.
  - `test_lecturas_para_usa_ref`: la estación con `ref="20"` recibe el valor de `estacion_id 20`, `unidad=="m"`.
  - `test_bajar_json_roto_lanza_fuenteerror`.
- [ ] **Paso 2: RED. Paso 3: implementar. Paso 4: verde (suites). Paso 5: commit** — `feat: adaptador INA`.

### Tarea 4: Adaptador AGP (Paraná en Barranqueras) con respaldo INA y niveles APA

**Archivos:** Crear `fuente/fuentes/agp.py`, `tests/test_agp.py`, `tests/fixtures/agp_barranqueras.dat` (recorte real con 6 filas de datos más una `NAN`, una fuera de rango `0 < h < 15` y la cabecera de 4 líneas). Referencia: `/home/claude/apuratejose/fuente/agp_update.py` funciones `bajar` y `agp`.

**Interfaces:**
- Produce `agp.URL`, `agp.parse(texto) -> tuple[datetime, float] | None` (última lectura válida, hora Argentina → UTC), `agp.bajar(abrir=..., intentos=3, dormir=...)` (reintenta sin verificar la cadena TLS **solo** para el host `agpse.gob.ar`, como en Pablo, con comentario que explica por qué y con el descarte de saltos raros ya descrito), `agp.lecturas_para(estaciones, ultima) -> list[Lectura]` (`unidad="m"`, `fuente="agp"`).
- Regla de respaldo en el adaptador de la estación (T6): si la lectura AGP tiene más de 3 h, se usa la del INA para la misma estación (`ref` INA en el registro).

- [ ] **Paso 1: tests** — `test_parse_devuelve_la_ultima_valida`, `test_parse_ignora_nan_y_fuera_de_rango`, `test_parse_sin_filas_devuelve_none`, `test_sin_verificacion_tls_solo_para_agpse` (con `abrir` simulado que lanza `URLError("CERTIFICATE_VERIFY_FAILED")` para `agpse.gob.ar` → se reintenta sin verificar; para otro host → se propaga), `test_respaldo_ina_si_agp_pasa_de_3h`.
- [ ] **Paso 2–5:** RED, implementar, verde, commit — `feat: adaptador AGP con respaldo INA`.

### Tarea 5: Adaptador USGS + NWS (EE. UU.)

**Archivos:** Crear `fuente/fuentes/usgs_nws.py`, `tests/test_usgs_nws.py`, `tests/fixtures/usgs_iv_07010000.json`, `tests/fixtures/nwps_EADM7.json` (recortes **reales**: obtenerlos con WebFetch/curl desde las URLs de abajo; no escribirlos de memoria).

**Interfaces:**
- Produce `usgs_nws.url_usgs(sitios: list[str]) -> str` = `https://waterservices.usgs.gov/nwis/iv/?format=json&sites=<coma>&parameterCd=00065&siteStatus=all`, `usgs_nws.parse_usgs(texto) -> dict[str, tuple[float, datetime]]` (site → (pies, t_utc); descarta `-999999` y valores no numéricos), `usgs_nws.url_nwps(lid) = https://api.water.noaa.gov/nwps/v1/gauges/<lid>`, `usgs_nws.parse_nwps(texto) -> Umbrales` (`action`→`bajo`, `minor`→`medio`, `moderate`→`alto`; `tipo="oficial"`; categorías ausentes o `-9999` → `en_estudio`), `usgs_nws.bajar_todo(estaciones, abrir=..., dormir=...) -> tuple[list[Lectura], dict[str, Umbrales]]` (una petición USGS para todos los sitios y una NWPS por estación; si falla una NWPS esa estación queda `en_estudio` y las demás siguen; si falla USGS lanza `FuenteError`).
- **Paso previo obligatorio:** abrir la respuesta real de NWPS y anotar los nombres exactos de los campos de las categorías antes de escribir `parse_nwps`. Lo comprobado hasta ahora: `flood > categories`, `stageUnits: "ft"`, valores 28/30/35/40 en St. Louis; falta el nombre exacto del campo de altura dentro de cada categoría.

- [ ] **Paso 1: tests** — `test_parse_usgs_lee_pies_y_hora_utc` (St. Louis: valor 7.97 ft y `2026-10-20T14:00:00-05:00` → `19:00:00Z`), `test_parse_usgs_descarta_valores_centinela`, `test_parse_nwps_st_louis` (`Umbrales(28,30,35,"oficial")`), `test_nwps_sin_categorias_es_en_estudio`, `test_una_nwps_caida_no_tumba_las_demas`, `test_usgs_caido_lanza_fuenteerror`, `test_lecturas_en_pies` (`unidad=="ft"`, `fuente=="usgs"`).
- [ ] **Paso 2–5:** RED, implementar, verde, commit — `feat: adaptador USGS y NWS`.

### Tarea 6: Registros de Argentina y EE. UU. y conexión de las fuentes reales

**Archivos:**
- Crear: `fuente/paises/ar/estaciones.json`, `fuente/paises/us/estaciones.json`, `tests/test_registros.py`
- Modificar: `fuente/actualizar.py` (`_fuentes_reales(pais)`)

**Interfaces:**
- Produce `_fuentes_reales(pais: str) -> dict`: `es` igual que hoy; `ar` → `{"ina": ..., "agp": ..., "prevision": ...}` con `aca`/`chj` ausentes; `us` → `{"usgs": ..., "prevision": ...}`. `ejecutar` pasa a recorrer las fuentes presentes en el registro (`aca`,`chj`,`ina`,`agp`,`usgs`) en lugar de `("aca","chj")` fijo, cada una con el mismo contrato `callable(ests) -> (lecturas, umbrales_vivos)` y aislada con `try/except FuenteError`.
- Estaciones iniciales (ids kebab‑case; `ref` = `estacion_id` INA o sitio USGS):
  - `ar`: `parana-barranqueras` (fuente `agp`, `ref` INA `20`, umbrales fijos `5.5/6.0/6.5` oficiales APA), `parana-corrientes` (`19`), `parana-santa-fe` (`30`), `parana-parana` (`29`), `parana-rosario` (`34`), `uruguay-concordia` (`79`); las cinco últimas con fuente `ina` y umbrales vivos.
  - `us`: `mississippi-st-louis` (`07010000`, LID `EADM7`), `mississippi-memphis`, `mississippi-nueva-orleans`, `missouri-kansas-city`, `ohio-cincinnati`, `red-fargo`.
- **Verificación obligatoria por estación de EE. UU.:** confirmar con WebFetch que el LID y el sitio USGS existen y que el LID corresponde a ese río y ciudad (`api.water.noaa.gov/nwps/v1/gauges/<LID>` y la consulta USGS). Si algún dato no se puede confirmar, la estación **se quita** y se anota en el libro de registro (no adivinar identificadores).

- [ ] **Paso 1: tests** — `test_registros_cargan_sin_error` (los tres países), `test_ids_unicos_entre_paises`, `test_ar_us_usan_unidades_de_su_fuente` (`ina`/`agp`→`m`, `usgs`→`ft`), `test_zonas_validas`, `test_barranqueras_tiene_umbrales_apa`, `test_ejecutar_recorre_fuentes_del_registro` (fuentes simuladas `ina`/`usgs` producen lecturas en `latest.json`).
- [ ] **Paso 2–5:** RED, implementar, verde, commit — `feat: registros de Argentina y EE. UU. y fuentes reales por país`.

### Tarea 7: Página con pestañas por país y datos por país

**Archivos:** Modificar `fuente/page.html`, `fuente/web/logica.js`, `fuente/textos.json`, `fuente/armar_sitio.py`; pruebas `tests/web/logica.test.js`, `tests/test_pagina.py`.

**Interfaces:**
- Produce en `logica.js`: `PAISES = ["ar","es","us"]`; `paisDesdeHash(hash, porDefecto) -> string` (país conocido o `porDefecto`); `hashPara(pais) -> "#ar"`; `rutaDatos(pais, archivo) -> "data/<pais>/<archivo>"`; `resumenPais(entradaIndice) -> {n, porNivel, sd}`.
- `page.html`: barra de pestañas accesible (`role="tablist"`, teclado con flechas, `aria-selected`), título y descripción por país, `hashchange`, carga de `data/paises.json` y luego solo `data/<pais>/{latest,prevision}.json` y los meses de `history/`. País sin datos todavía → mensaje `pais_sin_datos`. País desconocido en la URL → cae al país por defecto con aviso `pais_desconocido`. País por defecto según idioma del navegador: `ca`/`es-ES` → `es`; `es-AR` → `ar`; `en-US` → `us`; si no, `es`.
- `textos.json`: claves nuevas `paises.{ar,es,us}.{nombre,desc,sub,zonas...}`, `pais_sin_datos`, `pais_desconocido`, `tab_label`; sección `zonas` con los ids de T1.

- [ ] **Paso 1: tests**
  - node: `paisDesdeHash("#us","es")=="us"`, `("#xx","es")=="es"`, `("","ar")=="ar"`; `rutaDatos("ar","latest.json")=="data/ar/latest.json"`; `resumenPais` con índice vacío devuelve ceros.
  - pytest `test_pagina`: la página armada contiene `role="tablist"` y las tres pestañas; todas las claves nuevas existen en los tres idiomas cuando T8 las añada (esta tarea cubre es y ca; en T8 se activa la paridad con `en`); cada zona de cada país tiene texto.
  - Prueba de humo con navegador: `python3 -m http.server` desde la raíz y Playwright (Chromium preinstalado): abrir `#ar`, `#es`, `#us`, `#xx`; sin errores de consola; captura de pantalla de cada una guardada fuera del repo.
- [ ] **Paso 2–5:** RED, implementar, verde, commit — `feat: pestañas por país`.

### Tarea 8: Inglés, unidades y formatos

**Archivos:** Modificar `fuente/textos.json`, `fuente/web/logica.js`, `fuente/page.html`; pruebas `tests/test_pagina.py`, `tests/web/logica.test.js`.

**Interfaces:** `logica.formatoValor(valor, unidad, lang) -> string` (`m3s`→`m³/s`, `m`→`m`, `ft`→`ft`; coma decimal en es/ca, punto en en); `idiomaInicial` acepta `en`; selector de idioma con tres opciones; `<html lang>` se actualiza.

- [ ] **Paso 1: tests** — node: `formatoValor(6.1,"m","es")=="6,1 m"`, `(28,"ft","en")=="28 ft"`, `(41.2,"m3s","ca")=="41,2 m³/s"`; `edadTexto` en inglés (`"12 min ago"`); pytest: la paridad de claves cubre `es`, `ca` y `en` (incluye `tile_desc`, `foot`, `fuentes_nombres`, `zonas` y `paises`); ningún texto de `en` queda igual a `es` salvo nombres propios (comprobación de al menos el 90 % de las claves de texto distintas).
- [ ] **Paso 2–5:** RED, implementar (traducciones reales, sin copiar el castellano), verde, commit — `feat: inglés y formatos por unidad`.

### Tarea 9: Fichas con módulos: crecidas históricas y gráfico con pronóstico y simulador

**Archivos:**
- Crear: `fuente/paises/<pais>/rios/<id>/historicos.json` para Paraná en Barranqueras (portar `historicos.json` de Pablo: 1983 8,6 m, 1992 8,25 m, 2013 7,09 m y el tope de las defensas 9,5 m, cada uno con `nota`); `fuente/web/modulos.js` (render de módulos con d3 local)
- Modificar: `fuente/page.html`, `fuente/armar_sitio.py` (empaqueta los módulos en `data/<pais>/rios/<id>/`), `fuente/actualizar.py` (copia/valida los archivos de módulos hacia `data/` en el armado, no en el robot), `tests/test_pagina.py`, `tests/web/modulos.test.js`
- Referencia de Pablo: `fuente/page.html` secciones `#grafico` (líneas ~391–445, funciones `build`, `draw`, `update`) e `#historia` (líneas ~445–468, función de líneas ~1471–1500).

**Interfaces:**
- `modulos.js` produce `compararConHistoricas(valorActual, historicas) -> [{evento, valor, diferencia, nota}]` ordenado de mayor a menor; `simular(valor, umbrales) -> {nivel, textoClave, distancias:{N1,N2,N3}}` (`nivel` 0–3 por umbrales; `distancias` a cada umbral; sin umbrales → solo distancia a `null`); `serieConPronostico(historial, pronostico) -> [{t, v, tipo:"obs"|"prono"}]`.
- Módulo «crecidas históricas»: aparece solo si existe `historicos.json` del río. Módulo «gráfico + simulador»: aparece en toda estación con historial; muestra el pronóstico oficial si `pronostico.json` existe (EE. UU.: NWS en T6bis; Paraná: archivo manual con etiqueta «pronóstico manual» y fecha, y aviso de vencido si pasa de 36 h).
- Los textos de los módulos son claves de `textos.json` en es/ca/en.

- [ ] **Paso 1: tests** — node: `compararConHistoricas(7.2,[{evento:"1983",valor:8.6}])[0].diferencia` ≈ `-1.4`; `simular(6.2,{bajo:5.5,medio:6,alto:6.5}).nivel==2`; `simular` con `valor` nulo no lanza; `serieConPronostico` marca el último observado y los pronosticados; pytest: la página incluye el contenedor del módulo solo para el río con archivos; los archivos de módulos tienen el esquema esperado.
- [ ] **Paso 2–5:** RED, implementar con d3 local, verde, comprobación visual en navegador (captura), commit — `feat: módulos de ficha (históricas, gráfico con simulador)`.

### Tarea 10: Ficha especial del Paraná en Barranqueras y la represa del Río Negro

**Archivos:** Crear `fuente/paises/ar/rios/parana-barranqueras/{situacion.json,umbrales.json,lluvia.json,pronostico.json}` y `fuente/web/ficha_barranqueras.js`; modificar `fuente/page.html` (punto de montaje), `tests/test_pagina.py`, `tests/web/ficha_barranqueras.test.js`. Referencia: `apuratejose/fuente/page.html` (esquema de la represa y compuertas, líneas ~887–1260 y la secuencia de «corte» ~1558–1700) y los JSON de `apuratejose/fuente/data/`.

**Interfaces:** `FichaBarranqueras.montar(el, {estacion, situacion, lluvia, pronostico, lang})` monta el esquema de la represa con compuertas abiertas o cerradas según la regla de la APA (`alerta_m`/`evacuacion_m` de `situacion.json`) y la lluvia a 4 días; `reglaCompuertas(h, alerta) -> "abiertas"|"cerradas"|"puede cerrar"` es una función pura exportada para tests.

- Portar el código **sin analítica**, sin dominios de Pablo, con textos en es/ca/en y datos desde `data/ar/rios/parana-barranqueras/`. El módulo solo se carga cuando la ficha activa es `parana-barranqueras`.
- [ ] **Paso 1: tests** — node: `reglaCompuertas(5.9,6)=="abiertas"`, `(6,6)=="puede cerrar"`, `(6.6,6)=="cerradas"`; pytest: `index.html` no contiene `cloudflare`, `clarity` ni `apuratejose.com.ar`; los JSON de la ficha tienen las claves que usa el módulo.
- [ ] **Paso 2–5:** RED, portar, verde, captura en navegador, commit — `feat: ficha del Paraná y la represa del Río Negro`.

### Tarea 11: Satélite Sentinel‑2 por río

**Archivos:** Crear `fuente/satelite.py`, `.github/workflows/satelite.yml`, `tests/test_satelite.py`, `tests/test_workflow.py` (casos nuevos); modificar `fuente/page.html` (módulo con comparador y carga bajo demanda). Referencia: `apuratejose/fuente/sat_s2.py` (`BBOX`, `buscar`, filtro de nubes con la banda SCL).

**Interfaces:**
- `satelite.py` lee `fuente/paises/*/rios/*/satelite_config.json` (`{"bbox":[lonmin,latmin,lonmax,latmax],"max_nubes":0.45,"max_sin_dato":0.03}`), busca pasadas nuevas en Earth Search (`https://earth-search.aws.element84.com/v1/search`), y escribe `data/<pais>/rios/<id>/satelite.json` (metadatos) y dos imágenes **como archivos** `satelite_a.jpg` y `satelite_b.jpg` (no base64 incrustado). Instala rasterio/Pillow solo si faltan. `buscar(bbox, desde)` y `nubosidad(scl_array)` son puras y testeables.
- Config inicial: `parana-barranqueras` con el recuadro de Pablo `(-59.015,-27.4915,-58.865,-27.3885)`.
- Workflow diario `satelite.yml` (permisos `contents: write`, `concurrency`, mismo método de publicación con reintentos que `actualizar.yml`).

- [ ] **Paso 1: tests** — `test_nubosidad_cuenta_nubes_y_sombras` con una matriz SCL pequeña; `test_buscar_filtra_las_que_no_cubren_el_recuadro`; `test_sin_pasadas_nuevas_no_escribe`; `test_workflow_satelite_tiene_permisos_y_concurrency`; `test_fixture_de_busqueda_real` (recorte real guardado en `tests/fixtures/`).
- [ ] **Paso 2–5:** RED, implementar, verde, commit — `feat: satélite Sentinel-2 por río`.

### Tarea 12: Tarjetas para compartir

**Archivos:** Crear `fuente/og.py` (adaptado de `apuratejose/fuente/og.py`, 116 líneas), `fuente/fonts/` (Liberation, SIL OFL, con su licencia), `tests/test_og.py`; modificar `fuente/armar_sitio.py`.

**Interfaces:** `og.dibujar(datos: dict, destino: str, idioma: str) -> bool` (False sin error si falta Pillow); genera `data/og/global.png` y `data/og/<pais>.png` (1200×630) a partir de `paises.json` y `latest.json`; `armar_sitio` añade las metaetiquetas `og:image` de la tarjeta global con `?v=<fecha>`; cada país se comparte con `#<pais>` y la imagen global (la tarjeta por país se usa si se publica una página estática por país, fuera de alcance).

- [ ] **Paso 1: tests** — `test_dibujar_crea_png_1200x630` (si Pillow no está, `pytest.skip`), `test_sin_pillow_devuelve_false`, `test_textos_de_la_tarjeta_salen_de_los_datos`, `test_armar_sitio_incluye_og_image`.
- [ ] **Paso 2–5:** RED, implementar, verde, comprobación visual de las tarjetas (sin aspecto genérico de plantilla: tipografía clara, jerarquía, un solo acento), commit — `feat: tarjetas para compartir`.

### Tarea 13: Ebro y Guadalquivir (condicional)

**Archivos:** posible `fuente/fuentes/saih_ebro.py`, `fuente/fuentes/saih_guadalquivir.py`, sus tests y fixtures; entradas nuevas en `fuente/paises/es/estaciones.json`.

- [ ] **Paso 1: investigar** con WebFetch si el SAIH Ebro y el SAIH Guadalquivir publican datos abiertos legibles sin autenticación, con licencia clara y umbrales propios. Registrar el hallazgo en el libro.
- [ ] **Paso 2: decisión** — si una fuente es fiable, implementarla con el mismo patrón (parse + fixture real + tests) y añadir las estaciones (Ebro en Zaragoza, Guadalquivir en Sevilla); si no, **no se implementa** y se anota como pendiente de fase 2. Un resultado negativo cierra la tarea sin código.
- [ ] **Paso 3: commit** — `feat: SAIH Ebro y Guadalquivir` o, si no procede, solo la nota en el libro.

### Tarea 14: Documentación, créditos, datos iniciales y cierre

**Archivos:** Modificar `README.md`, `LICENSE` (mantener las dos líneas de copyright), `fuente/notificar.py` (`SITIO`), `data/` (datos iniciales de los tres países), `index.html` (reconstruido), `tests/test_pagina.py`.

- [ ] **Paso 1: README** — qué es, países y ríos incluidos, tabla de fuentes con licencia, escala N0–N3, cómo añadir un país (carpeta `paises/<cc>/`, adaptador, fixtures, textos), crecidas históricas y satélite por río, aviso de uso no comercial de Open‑Meteo, créditos a Pablo Dodda y Sebastian Andrada, estado del permiso de reutilización de ACA y CHJ.
- [ ] **Paso 2: datos iniciales** — ejecutar el robot con fuentes simuladas **no**: sembrar solo con datos reales obtenidos por WebFetch (INA y USGS) o dejar `paises.json` con el país pendiente; nunca datos inventados. Si no se pueden obtener, la página debe mostrar «Sin datos todavía» para ese país hasta el primer ciclo del robot (test de T7 lo cubre).
- [ ] **Paso 3: reconstruir** `python3 fuente/armar_sitio.py` y comprobar que `index.html` no tiene analítica de Pablo ni dominios ajenos (grep en el test).
- [ ] **Paso 4: verde** ambas suites; revisión visual en navegador de las tres pestañas.
- [ ] **Paso 5: commit y push de `multipais`** — `docs: README multipaís y datos iniciales`. No mergear ni cambiar el nombre del repo en GitHub: son acciones de Sebastian (renombrar el repo requiere actualizar `SITIO` y las URLs de la tarjeta).
