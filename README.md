# Nivel Río

Panel público para consultar niveles y caudales observados de ríos en **Argentina, España, Estados Unidos, Alemania, Francia, Reino Unido y Polonia**. Es una página estática, sin servidor ni analítica, con interfaz en castellano, catalán e inglés.

El proyecto combina el diseño de «Apurate José», de Pablo Dodda, con adaptadores de datos, niveles con histéresis y pruebas del proyecto Nivel Río. Mantiene la atribución y la licencia MIT del trabajo original.

**Es una herramienta informativa, no un sistema oficial de alerta.** Los datos pueden ser provisionales o retrasarse, y las crecidas repentinas pueden ocurrir entre lecturas. Sigue siempre las instrucciones de Protección Civil y de las autoridades locales; en una emergencia en España, llama al 112.

## Cobertura y fuentes

El registro contiene 6 estaciones de Argentina, 32 de España, 5 de Estados Unidos y una estación observada en cada uno de Alemania, Francia, Reino Unido y Polonia: 47 estaciones en total. Solo se publican ubicaciones con una fuente de medición configurada.

| País o región | Fuente de observación o modelo | Umbrales y avisos | Limitaciones principales |
|---|---|---|---|
| Argentina | INA; AGP para Barranqueras con INA como respaldo | Niveles del INA; umbrales locales de APA Chaco para Barranqueras | La lectura del INA es diaria. Algunos umbrales aún están en estudio. |
| España | ACA Sentilo para cuencas internas de Catalunya; SAIH de la CHJ para estaciones valencianas | Umbrales oficiales de CHJ donde existen; umbrales estimados y claramente etiquetados para ACA; avisos AEMET e INUNCAT | La ACA no publica umbrales por estación en formato máquina. |
| Estados Unidos | USGS para el Mississippi, Missouri, Ohio, Colorado y Rio Grande; NWS/NWPS donde hay un identificador de estación válido | Umbrales oficiales del NWS cuando los datos son completos y coherentes | Las estaciones nuevas aún no tienen umbrales de inundación vinculados y se muestran «en estudio», sin nivel de alerta propio. |
| Alemania | PEGELONLINE | Sin umbrales oficiales en formato compatible | La tarjeta muestra el nivel observado; los umbrales están en estudio. |
| Francia | Hub'Eau | Sin umbrales oficiales en formato compatible | La tarjeta muestra el caudal observado; los umbrales están en estudio. |
| Reino Unido | Environment Agency | Sin umbrales oficiales en formato compatible | La tarjeta muestra el nivel observado; los umbrales están en estudio. |
| Polonia | IMGW | Sin umbrales oficiales en formato compatible | La tarjeta muestra el nivel observado; los umbrales están en estudio. |

Los adaptadores están en `fuente/fuentes/` y los registros de estaciones en `fuente/paises/<pais-o-region>/estaciones.json`. Las estaciones seleccionadas representan ríos conocidos o potencialmente peligrosos; no pretenden cubrir todos los cursos fluviales.

## Cómo interpretar la página

- La escala N0 (normal) a N3 (peligro) es propia del proyecto, no una escala oficial. Cada nivel muestra texto y símbolo, además del color.
- Los umbrales se identifican como **oficiales**, **estimados** o **en estudio**. Un umbral estimado no debe interpretarse como cota oficial de desbordamiento.
- Los avisos meteorológicos y de Protección Civil se presentan como contexto. Solo los avisos configurados explícitamente pueden elevar el nivel mostrado.
- Las previsiones de lluvia y caudal son orientativas; no cambian los niveles de alerta ni generan notificaciones. Solo aparecen ríos con estaciones observadas; un valor ausente o una lectura obsoleta se muestra como tal, nunca como una medición actual.
- Una lectura obsoleta o ausente se marca «sin datos»; no equivale a un estado normal.
- Las notificaciones automáticas se publican como incidencias de GitHub cuando hay cambios de nivel que cumplen las reglas del proyecto. No se envían por correo ni mensajería.

## Actualización y estructura

GitHub Actions ejecuta `fuente/actualizar.py` cada 15 minutos y publica cambios relevantes. El programador vive en la rama predeterminada, pero obtiene y actualiza el código de `multipais`, porque GitHub solo ejecuta cron de Actions desde la rama predeterminada. Los datos se publican en `data/<pais>/`; la página (`index.html`) carga únicamente el país seleccionado. El flujo crea una publicación al cambiar un nivel o aproximadamente cada hora, debido a los retrasos variables de los cron de Actions. Los fallos de una fuente o país se aíslan para no detener la actualización de los demás.

Cada tarjeta incluye **Solicitar actualización**. El enlace abre GitHub Actions; requiere iniciar sesión y permiso de escritura en el repositorio. En la ejecución manual, selecciona el país y escribe el nombre del río indicado en la tarjeta (o `todos` para actualizar el país entero). No se incluye ningún token en la web.

```text
fuente/actualizar.py       descarga de fuentes, niveles y publicación de datos
fuente/alertas.py          máquina de estados y lógica de histéresis
fuente/estaciones.py       validación de catálogos por país
fuente/fuentes/            adaptadores ACA, CHJ, INA, AGP, USGS/NWS, PEGELONLINE, Hub'Eau, EA e IMGW
fuente/paises/             estaciones y módulos de cada país y río
fuente/page.html           plantilla de la web
fuente/textos.json         textos en español, catalán e inglés
fuente/web/                lógica de presentación y módulos de fichas
data/<pais>/               lecturas, avisos, historial y estado de cada país
```

La web no consulta las fuentes directamente desde el navegador. Esto permite consumir fuentes como ACA Sentilo, que no habilita CORS, y evita exponer lógica de ingestión en la página. Los datos de origen pueden ser provisionales y no validados; consulta siempre la fuente oficial correspondiente.

## Desarrollo y pruebas

Requisitos: Python 3.12, Node.js y pytest.

```sh
python3.12 -m pip install pytest
python3.12 -m pytest -q
node --test "tests/web/*.test.js"
python3.12 fuente/armar_sitio.py
```

Para ejecutar una actualización local de datos:

```sh
python3.12 fuente/actualizar.py
python3.12 fuente/actualizar.py --pais ar --rio Paraná
```

Las llamadas de prueba de fuentes reales y las herramientas de calibración requieren red; las pruebas unitarias usan fixtures locales. No ejecutes una actualización local si no quieres que se reemplacen los JSON de datos del país.

## Créditos y licencia

Hecho por Pablo Dodda. Adaptación multipaís: Sebastian Andrada. Licencia MIT; consulta [LICENSE](LICENSE).
