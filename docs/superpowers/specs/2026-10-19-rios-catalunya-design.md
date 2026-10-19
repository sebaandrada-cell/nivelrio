# Panel de ríos de Catalunya: especificación de diseño

Fecha: 2026-10-19. Estado: pendiente de revisión por Sebastian Andrada.
Base: el proyecto "Apurate José" de Pablo Dodda (MIT), copiado en `sebaandrada-cell/nivelrio`.
Informe de fuentes que respalda esta especificación: `Fuentes ríos Catalunya inundaciones.md`.

## 1. Qué se quiere

Una página pública, estática y con actualización automática, que muestre el estado de los ríos más peligrosos de Catalunya (nivel, caudal, tendencia) y avise cuando un río supera un límite peligroso. Para contexto incluye los ríos valencianos que se desbordaron en 2024. Reutiliza el diseño visual de apuratejose.com.ar, que ya está probado y que Sebastian propuso reutilizar.

Lo que la página NO es: un sistema de alerta oficial. No sustituye a Protecció Civil, Meteocat, AEMET, ACA ni a las confederaciones del Ebro y del Júcar. Lo dice en pantalla de forma permanente.

## 2. Decisiones ya tomadas

1. Este repo es la copia de Sebastian. Se puede modificar sin límites; el sitio de Pablo (apuratejose.com.ar) vive en su propio repo y no se toca.
2. Diseño visual: se reutiliza el de Pablo (colores, tipografía, tarjetas, gráfico con líneas de umbral, píldora de estado, tarjeta para compartir, lluvia, satélite, modo oscuro). Se reemplaza lo específico de Resistencia: el diagrama del dique y las compuertas, la sección de 1983 y los textos de la crecida del Paraná.
3. Créditos: se conservan "Hecho por Pablo Dodda" y la licencia MIT, y se agrega a Sebastian Andrada como autor de la adaptación para Catalunya (README, pie de página y `LICENSE`).
4. Sin analítica con grabación de sesiones. Se quitan Microsoft Clarity y Cloudflare Analytics. Si más adelante se quiere medir visitas, se hace con una herramienta sin cookies o con banner de consentimiento (RGPD/ePrivacy).
5. No se ejecuta la skill `/minds` por ahora.

## 3. Alcance

### Fase 1 (esta especificación)

- Ríos de las cuencas internas con feed verificado: Llobregat, Besòs, Ter, Fluvià, Muga, Tordera, Francolí, Gaià, Foix, Cardener, Anoia (fuente: ACA Sentilo, 87 estaciones, sin clave).
- Valencia como contexto: Túria, Xúquer, Poyo (fuente: SAIH Júcar, con umbrales oficiales de caudal).
- Avisos oficiales mostrados tal cual: feeds CAP de AEMET (AFAC69 Cataluña, AFAC77 Comunitat Valenciana) y el plan INUNCAT activo (dataset `wj9c-j6vf`).
- Alertas propias en tres niveles más "sin datos", con notificación.
- Historial propio, porque ACA solo conserva 3 meses.

### Fase 2 (depende de gestiones externas)

- Segre, Ebre, Noguera Pallaresa y Noguera Ribagorçana: no hay feed encontrado. El SAIH Ebro no respondió desde el entorno de investigación. Primero se prueba desde un runner real de GitHub Actions; si falla, se pide acceso a la CHE.
- Umbrales oficiales de ACA: se pide la tabla de "llindar d'alerta" y "llindar de perill" a ACA o Protecció Civil.
- API de Meteocat (avisos por comarca): requiere registro y clave. Cabecera de autenticación y cuotas sin confirmar.
- Previsión GloFAS vía Open-Meteo y reservas de embalses (`gn9e-3qhr`) como contexto, nunca como alerta.

### Fuera de alcance

Probabilidad de inundación calibrada (no existe en ninguna fuente abierta), previsión de caudal para ramblas, mapas de inundabilidad, cualquier cosa con servidor.

## 4. Arquitectura

Sitio estático en GitHub Pages. Un workflow de GitHub Actions descarga las fuentes, las normaliza, evalúa las alertas y hace commit de JSON. El navegador solo lee JSON del mismo origen. Esto resuelve que la API de ACA no manda cabeceras CORS.

### 4.1 Archivos

```
fuente/
  estaciones.json      lista de estaciones: id, río, cuenca, nombre, fuente, ids de Sentilo/CHJ, umbrales, tipo de umbral (oficial|estimado)
  fuentes/aca.py       cliente Sentilo (último valor, ventana de 90 min, catálogo semanal)
  fuentes/chj.py       lee el array `aforos` de saih.chj.es/mapa-aforos, con reintentos
  fuentes/avisos.py    CAP de AEMET + dataset INUNCAT
  alertas.py           máquina de estados (N0-N3, SD) con histéresis
  actualizar.py        orquesta todo y escribe data/
  page.html            diseño de Pablo, generalizado a varias estaciones
  armar_sitio.py       sin cambios de fondo: arma index.html
data/
  latest.json          última lectura normalizada por estación
  state.json           nivel de alerta vigente por estación (lo que permite la histéresis)
  history/AAAA-MM.json historial propio acumulado
tests/
  fixtures/            respuestas reales guardadas de Sentilo, CHJ y CAP
  test_alertas.py, test_fuentes.py
```

### 4.2 Flujo de cada ejecución

1. Una llamada a `data/AFORAMENT-EST` (Sentilo) y filtro de los sensores clave. Para unas 25-30 estaciones, pide además la ventana de los últimos 75-90 minutos y calcula máximo y tendencia, para no perder picos entre ejecuciones.
2. Una petición a `mapa-aforos` del SAIH Júcar con reintentos (el servidor corta cerca de 1 de cada 3 conexiones).
3. Avisos: feeds CAP de AEMET y dataset INUNCAT.
4. Normaliza a un esquema común: `fuente`, `timestamp_utc`, `unidad`, `edad_dato`. Todo se guarda en UTC; los timestamps de Sentilo se tratan como UTC.
5. Evalúa alertas con `state.json`, escribe `latest.json`, agrega al historial y rearma `index.html`.
6. Si cambió un nivel de alerta, dispara la notificación.

Cada ejecución es idempotente. Una fuente que falla no frena las demás: esa fuente queda en "sin datos" y el resto se publica.

### 4.3 Frecuencia

La rutina horaria de Pablo (un trabajo de 5,5 horas que cada 10 minutos mira y se relanza solo) se reemplaza por un cron simple cada 15 minutos con `workflow_dispatch`. La fuente publica cada 5 a 15 minutos, y un cron más espaciado de lo necesario genera menos commits y menos peso en el repo. Se mantiene la idea de reintentar y de no pisar commits ajenos (`git fetch` y `reset` antes de publicar).

## 5. Esquema de alertas (diseño propio, no oficial)

| Estado | Nombre | Entrada | Valencia (CHJ) | Cataluña (ACA) |
|---|---|---|---|---|
| N0 | Normal | Debajo de N1 | sin umbral superado | sin umbral superado |
| N1 | Vigilancia | caudal ≥ umbral bajo | amarillo oficial | umbral estimado (~T=2 años) |
| N2 | Aviso | caudal ≥ umbral medio y subiendo | naranja oficial | umbral estimado (~T=5 años) |
| N3 | Peligro | caudal ≥ umbral alto, o aviso rojo / INUNCAT en alerta o emergencia sobre la comarca | rojo oficial | umbral estimado (~T=20 años) u oficial externo |
| SD | Sin datos | dato demasiado viejo | más de 25 min (regla de la CHJ) | más de 3 muestras (≈ 15-20 min); a calibrar |

Reglas:

- **Subida:** inmediata cuando el valor supera la entrada en dos lecturas seguidas, o en una sola si la velocidad de subida es alta, siempre que el valor esté dentro del rango del instrumento.
- **Bajada:** solo cuando el valor queda debajo del 85 % del umbral de entrada durante 3 lecturas o 3 horas, un nivel por vez, nunca de N3 a N0 de golpe.
- **Sin datos no es "río tranquilo".** Al pasar a SD se conserva el último nivel conocido con la leyenda "último dato hace X". Si era N2 o N3, la alerta se mantiene. Si SD dura más de un periodo configurable, se emite un aviso aparte de "estación sin datos".
- **Avisos oficiales:** AEMET, Meteocat e INUNCAT no se calculan, se muestran. Pueden elevar el nivel mostrado a N3 con la leyenda "elevado por aviso oficial". Si el caudal está en SD y hay aviso rojo, se escala igual.
- **Umbrales catalanes estimados:** salen de `hprm-xuw7` (medias diarias desde 2000) y `3yr3-vq6y` (5 minutos desde 2020). Tienen dos sesgos conocidos: las medias diarias subestiman los picos y los ríos regulados (Llobregat, Ter, Ebre) no siguen la estadística natural. Cada uno se muestra como "estimado, no oficial" con su método. Si ACA entrega la tabla oficial, se sustituye sin tocar el resto.
- Los umbrales de la CHJ son de caudal, no de nivel, y algunos puntos figuran "en estudio"; esos no generan alerta propia.

Límite que se dice en la página: con un muestreo de 15 minutos el panel sirve para crecidas que avanzan en horas (Segre, Ebre, Ter bajo, Llobregat, Xúquer) y no sirve como aviso para cuencas rápidas como el Besòs o el Poyo. Ahí manda la alerta oficial (ES-Alert, INUNCAT), y el panel la muestra.

## 6. Cambios sobre el código heredado

De la revisión del código de Pablo, y por orden:

1. Borrar `.github/workflows/zscaler-iac-scan.yml` (inputs vacíos, referencia `steps.zscaler-iac-scan.sarif_file_path` en vez de `.outputs.`, sin IaC en el repo y sin secrets: falla en cada push).
2. Verificar siempre el TLS. No hace falta el atajo de `agp_update.py`: las fuentes de Catalunya y Valencia no lo necesitan. Se elimina `agp_update.py`, `sat_update.py` y la lógica de compuertas.
3. Quitar la analítica de `page.html` (Clarity y Cloudflare).
4. Quitar `CNAME` (apuratejose.com.ar) y las referencias a Resistencia, al Paraná y a "pablo" en textos.
5. Actualizar `README.md` y `ACTUALIZAR.md` (que hoy describen una rutina manual del Paraná) y corregir docstrings desfasados.
6. Evitar que `index.html` crezca con imágenes en base64: en esta versión no se incrustan imágenes satelitales. El satélite queda fuera de la fase 1.
7. Reemplazar `datetime.utcnow()` (deprecado).

El repo de Sebastian hoy sigue ejecutando el robot del Paraná sobre `main` (el último push fue hoy). Hay que desactivar ese workflow al fusionar la rama, para que no siga commiteando datos del Paraná sobre el sitio nuevo.

## 7. Interfaz

- Portada con un resumen: cuántas estaciones están en cada nivel y los avisos oficiales vigentes, con su fuente y su hora.
- Una tarjeta por río, ordenadas por peligrosidad actual. Cada tarjeta muestra la estación más relevante, la lectura, la tendencia, la edad del dato, la fuente y el nivel con su rótulo ("oficial" o "estimado").
- Detalle por estación con el gráfico de 15 días y 3 meses con las líneas de umbral (el componente de Pablo, generalizado).
- Pie permanente: "Informativo. Datos provisionales sin validar. No sustituye a Protecció Civil. Siga siempre sus instrucciones." y las atribuciones: ACA, SAIH CHJ, AEMET, Meteocat y Open-Meteo (CC BY 4.0) cuando se use.
- Idiomas: catalán y castellano.
- Accesibilidad: el nivel nunca se comunica solo con color; lleva texto y símbolo.

## 8. Pruebas y verificación

- Pruebas unitarias de la máquina de estados con casos: subida lenta, pico de una sola lectura, bajada con histéresis, bajada escalonada, salida a SD en N3, aviso rojo con SD.
- Fixtures reales guardados de Sentilo, `mapa-aforos` y CAP, para probar el parseo sin red. Se valida también que una fuente que falla no rompe las otras.
- Validación de la tabla de equivalencias Sentilo-Socrata comparando valores, porque no hay tabla oficial y las unidades difieren (cm frente a m).
- `node --check` sobre los scripts de la página y reconstrucción de `index.html` en una copia para verificar que coincide con lo publicado.
- Una ejecución manual del workflow (`workflow_dispatch`) en el runner real antes de activar el cron, para confirmar que ACA y CHJ responden desde GitHub Actions. Esa compatibilidad hoy es una inferencia.

## 9. Riesgos y condiciones

- **Falsa seguridad:** el mayor riesgo. Mitigación: rótulo permanente, edad del dato visible y SD que no desactiva alertas.
- **Datos provisionales:** ACA y CHJ avisan de que no están validados. CHJ no declara licencia ni prohíbe el uso; se pide permiso por escrito a ambas antes de publicar de forma amplia.
- **Licencia de ACA:** el campo dice "ver términos de uso" y la página de licencias de la Generalitat no se leyó. Se lee antes de publicar.
- **Open-Meteo:** gratis solo para uso no comercial.
- **Dependencia de endpoints no oficiales:** el array `aforos` de la CHJ está en el HTML de una página. Si cambian la página, el parseo falla; por eso el estado "sin datos" y una alerta de fallo del robot.
- **Cobertura:** 4 de los 15 ríos no tendrán dato en la fase 1, y faltan puntos clave (Besalú, Castelló en el Fluvià, tramo bajo del Tordera, Alzira, Paiporta, Torrent). La página lo dice en lugar de ocultarlo.

## 10. Preguntas abiertas para Sebastian

1. Dominio y GitHub Pages: ¿usa un dominio propio o `sebaandrada-cell.github.io/nivelrio`?
2. Notificaciones: ¿qué canal quiere? (issue de GitHub, correo, Telegram, push). Por defecto se propone un issue de GitHub que le llega por correo, sin secretos externos.
3. Nombre del sitio y de la rama final. Por defecto, rama `catalunya-rios` y sitio "Rius de Catalunya".
4. Idioma por defecto: catalán o castellano.
5. Clave de Meteocat: si se registra, va como secreto de Actions (fase 2).
