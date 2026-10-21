# Nivel Río multipaís — diseño

Fecha: 2026-10-20. Autor: Sebastian Andrada. Base: `apuratejose` de Pablo Dodda (MIT, Pablo está al tanto) y `nivelrio` rama `catalunya-rios`.
Nombre de trabajo: **Nivel Río** (conserva el nombre del repo; se puede cambiar sin tocar la arquitectura).

## 1. Intención
Una sola web pública, con **pestañas por país**, que muestra el estado de los ríos famosos o potencialmente peligrosos (no cada arroyo), con niveles de alerta propios N0–N3 y avisos por issue de GitHub. Se une lo mejor de las dos webs:
- De Pablo: gráfico con pronóstico y simulador, comparación con crecidas históricas, satélite Sentinel‑2, tarjeta para compartir.
- De Sebastian: motor de niveles con histéresis, muchas estaciones, avisos por issue, previsión informativa, castellano/catalán, tests.

Éxito: se abre `#ar`, `#es` o `#us` y se ve el estado actual de los ríos de ese país, sin servidor, con una fuente caída que solo apaga su país.

## 2. Fuera de alcance (esta entrega)
Resto de Europa, resto de América, autenticación, base de datos, analítica, pronóstico manual para ríos distintos del Paraná, avisos por email o Telegram. Cada país nuevo después es una entrega propia.

## 3. Arquitectura
Sitio estático en GitHub Pages. Un robot en GitHub Actions cada 15 minutos. Python solo con biblioteca estándar.

```
fuente/paises/{ar,es,us}/estaciones.json   registro de estaciones del país
fuente/paises/{ar,es,us}/rios/<id>/        módulos opcionales: historicos.json, situacion.json, pronostico.json, satelite.json
fuente/fuentes/                            un adaptador por fuente (aca, chj, avisos, prevision, ina, usgs_nws)
fuente/actualizar.py                       recorre los países, aísla fallos por país y por fuente
data/<pais>/{latest,state,avisos,cambios,prevision}.json    datos por país
data/<pais>/history/AAAA-MM.json
data/meta.json                             última publicación (ya existe)
```
La página carga solo los datos del país activo. La URL guarda el país (`#ar`, `#es`, `#us`) y el idioma.

## 4. Modelo de datos
Cambios en `Estacion`:
- `pais` (`ar|es|us`), `magnitud` (`caudal|altura`), `unidad` (`m3s|m|ft`).
- `umbrales.tipo`: `oficial | estimado | en_estudio` (ya existe), y se añade `regla` (texto corto de cómo se obtuvo cada nivel).
`evaluar` y la histéresis no cambian en lógica; pasan a ser agnósticos de la unidad. `VEL_SUBIDA_RAPIDA` pasa a ser por estación (`vel_subida_rapida`, opcional), porque un caudal en m³/s y una altura en metros no comparten escala. Si falta, el cambio rápido por una sola lectura queda desactivado para esa estación.
`unidad` se muestra tal cual la publica la fuente (pies en EE. UU., metros en Argentina): no se convierte, para que coincida con lo que el usuario ve en el NWS.

## 5. Fuentes (verificadas el 2026-10-20)
- **Argentina, INA** (`hidraulica.gob.ar/ina/ajax.estaciones.json.php`): 69 estaciones, JSON con `nivel_alerta`, `nivel_evacuacion`, `nivel_aguas_bajas`, `valor_actual`, `fecha_actual`, `tendencia`, `situacion`. Hay un valor por día (00:00), no horario. Para el Paraná en Barranqueras se mantiene además la estación automática del puerto (AGP, horaria) que usa Pablo, con el INA como respaldo, como en `agp_update.py`.
- **EE. UU., NWS/NWPS** (`api.water.noaa.gov/nwps/v1/gauges/<LID>`): categorías oficiales `action/minor/moderate/major` en pies, observado y pronóstico oficial. **USGS** (`waterservices.usgs.gov/nwis/iv`): altura (00065) y caudal (00060) casi en tiempo real. Ejemplo comprobado: Mississippi en St. Louis, LID `EADM7`, USGS `07010000`.
- **España:** ACA y CHJ, ya existentes. Ebro (SAIH Ebro) y Guadalquivir (SAIH): la fuente y los umbrales se verifican en el plan; si no son fiables quedan fuera de esta entrega.

## 6. Niveles por país
- **España:** como hoy (estimados por ACA, oficiales por CHJ).
- **Argentina:** `bajo`=N1, `medio`=N2, `alto`=N3. N2 = `nivel_alerta`, N3 = `nivel_evacuacion` (oficiales del INA). N1 = 90 % de `nivel_alerta` (regla propia, etiquetada). En Barranqueras se usan los avisos locales de la APA Chaco de `umbrales.json` de Pablo (N1 = 5,5 m).
- **EE. UU.:** N1 = `action`, N2 = `minor`, N3 = `moderate` (y `major`). Oficiales del NWS.
Una estación sin umbrales válidos queda `en_estudio` y muestra solo el valor.
Hoy (20‑oct) el INA marca Barranqueras y Corrientes en `evacuacion`: la primera ejecución abrirá issues; es estado real, no un error.

## 7. Página
- Pestañas de país en la cabecera, un resumen por nivel y los avisos del país.
- Idiomas: castellano, catalán y se añade **inglés**. Idioma inicial por navegador; las pestañas recuerdan país con la URL.
- Ficha de río con módulos que aparecen solo si el río tiene su archivo: crecidas históricas, gráfico con pronóstico y simulador, satélite, tarjeta para compartir.
- Sin analítica. Créditos a Pablo Dodda y Sebastian Andrada, licencia MIT.

## 8. Módulos de Pablo, generalizados
- **Gráfico + simulador:** sirve para cualquier estación con historial; pronóstico oficial donde exista (NWS automático) y curado donde no (Paraná, archivo manual marcado «pronóstico manual»).
- **Crecidas históricas:** `historicos.json` por río (como el de 1983 en el Paraná).
- **Satélite:** archivos aparte (no embebidos) con carga bajo demanda; robot diario separado porque necesita rasterio; solo ríos con `bbox` configurado.
- **Tarjeta para compartir:** `og.png` por país más una global, redibujada con cada publicación; sin dependencias nuevas obligatorias (si falta Pillow, se omite).

## 9. Robots
- `actualizar.yml` cada 15 minutos: todos los países, presupuesto de tiempo total, aislamiento de fallos, publicación solo si hay cambios o pasó ~55 min (regla ya implementada).
- `satelite.yml` diario, solo ríos con `bbox`.
- La caché de Actions conserva el estado entre ejecuciones (ya implementado).

## 10. Ríos de la primera entrega
- **Argentina:** Paraná en Barranqueras (con la represa del Río Negro de Pablo), Corrientes, Santa Fe, Paraná (ciudad) y Rosario; Uruguay en Concordia.
- **España:** las 32 estaciones actuales de Catalunya y Valencia; Ebro (Zaragoza) y Guadalquivir (Sevilla) si pasan la verificación.
- **EE. UU.:** Mississippi en St. Louis. Se limita esta primera fase a una estación del Mississippi; se podrán sumar otros puntos del río después de validarlos.

## 11. Pruebas
Pytest para cada adaptador con fixtures reales, para el motor con magnitudes distintas y para el aislamiento por país; pruebas node para el enrutado por pestañas y el formato por unidad; la prueba de paridad de textos pasa a es/ca/en. La suite actual (162 + 16) debe seguir verde tras migrar Catalunya al nuevo esquema.

## 12. Riesgos
- Las APIs de terceros cambian sin aviso: cada adaptador falla de forma aislada y la página lo avisa.
- Presupuesto del robot: más estaciones, más peticiones; se mide y se escalona la previsión si hace falta.
- Uso de datos: términos de INA, USGS y NWS (públicos); ACA y CHJ siguen pendientes de permiso de reutilización.
- El pronóstico del Paraná es manual: si nadie lo mantiene se marca como vencido en la página.
