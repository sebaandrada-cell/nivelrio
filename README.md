# Nivel Río

Panel público multipaís para consultar niveles y caudales de ríos con riesgo de crecida en **Argentina, España y Estados Unidos**. Es una página estática, sin servidor ni analítica, con interfaz en castellano, catalán e inglés.

El proyecto combina el diseño de «Apurate José», de Pablo Dodda, con adaptadores de datos, niveles con histéresis y pruebas del proyecto Nivel Río. Mantiene la atribución y la licencia MIT del trabajo original.

**Es una herramienta informativa, no un sistema oficial de alerta.** Los datos pueden ser provisionales o retrasarse, y las crecidas repentinas pueden ocurrir entre lecturas. Sigue siempre las instrucciones de Protección Civil y de las autoridades locales; en una emergencia en España, llama al 112.

## Cobertura y fuentes

El registro inicial contiene 6 estaciones de Argentina, 32 de España y 4 de Estados Unidos. La cobertura publicada depende de la disponibilidad de cada fuente.

| País | Fuente de observación | Umbrales y avisos | Limitaciones principales |
|---|---|---|---|
| Argentina | INA; AGP para Barranqueras con INA como respaldo | Niveles del INA; umbrales locales de APA Chaco para Barranqueras | La lectura del INA es diaria. Algunos umbrales aún están en estudio. |
| España | ACA Sentilo para cuencas internas de Catalunya; SAIH de la CHJ para estaciones valencianas | Umbrales oficiales de CHJ donde existen; umbrales estimados y claramente etiquetados para ACA; avisos AEMET e INUNCAT | No hay cobertura validada del Segre, Ebre ni Noguera en esta entrega. La ACA no publica umbrales por estación en formato máquina. |
| Estados Unidos | USGS para observaciones; NWS/NWPS para niveles de inundación y pronóstico oficial | Umbrales oficiales del NWS cuando los datos son completos y coherentes | Una estación sin umbrales válidos se muestra «en estudio», sin nivel de alerta propio. |

Los adaptadores están en `fuente/fuentes/` y los registros de estaciones en `fuente/paises/{ar,es,us}/estaciones.json`. Las estaciones seleccionadas representan ríos conocidos o potencialmente peligrosos; no pretenden cubrir todos los cursos fluviales.

## Cómo interpretar la página

- La escala N0 (normal) a N3 (peligro) es propia del proyecto, no una escala oficial. Cada nivel muestra texto y símbolo, además del color.
- Los umbrales se identifican como **oficiales**, **estimados** o **en estudio**. Un umbral estimado no debe interpretarse como cota oficial de desbordamiento.
- Los avisos meteorológicos y de Protección Civil se presentan como contexto. Solo los avisos configurados explícitamente pueden elevar el nivel mostrado.
- Las previsiones de lluvia y caudal son orientativas; no cambian los niveles de alerta ni generan notificaciones. El modelo global GloFAS no representa bien las crecidas repentinas de ramblas y rieras.
- Una lectura obsoleta o ausente se marca «sin datos»; no equivale a un estado normal.
- Las notificaciones automáticas se publican como incidencias de GitHub cuando hay cambios de nivel que cumplen las reglas del proyecto. No se envían por correo ni mensajería.

## Actualización y estructura

GitHub Actions ejecuta `fuente/actualizar.py` cada 15 minutos. Los datos se publican en `data/<pais>/`; la página (`index.html`) carga únicamente el país seleccionado. El flujo publica cuando cambia un nivel o ha transcurrido aproximadamente una hora, debido a los retrasos variables de los cron de Actions. Los fallos de una fuente o país se aíslan para no detener la actualización de los demás.

```text
fuente/actualizar.py       descarga de fuentes, niveles y publicación de datos
fuente/alertas.py          máquina de estados y lógica de histéresis
fuente/estaciones.py       validación de catálogos por país
fuente/fuentes/            adaptadores ACA, CHJ, INA, AGP, USGS/NWS y previsión
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
```

Las llamadas de prueba de fuentes reales y las herramientas de calibración requieren red; las pruebas unitarias usan fixtures locales. No ejecutes una actualización local si no quieres que se reemplacen los JSON de datos del país.

## Créditos y licencia

Hecho por Pablo Dodda. Adaptación multipaís: Sebastian Andrada. Licencia MIT; consulta [LICENSE](LICENSE).
