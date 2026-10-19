# Rius de Catalunya

Panel público con el caudal de los ríos de Catalunya que más riesgo de inundación tienen, más tres ríos de Valencia como contexto (Túria, Xúquer y la rambla del Poyo). Se actualiza solo cada 15 minutos, no tiene servidor ni analítica, y está en castellano con opción a catalán.

Es una adaptación de «Apurate José», el panel del Paraná que hizo Pablo Dodda. Se mantiene su diseño y la idea de página estática que se actualiza sola.

**No es una fuente oficial. No sustituye a Protecció Civil.** En una emergencia, 112 y las instrucciones de las autoridades.

## Qué muestra

- Un resumen con cuántos ríos están en cada nivel y los avisos oficiales vigentes (AEMET e INUNCAT).
- Una tarjeta por río con su estación más relevante: caudal, tendencia, edad del dato, fuente y umbrales. Cada río despliega todas sus estaciones con un gráfico del historial.
- La lluvia prevista por zona para 3 días, y en cada tarjeta la lluvia a 48 h y un caudal esperado orientativo.

## Niveles

| Nivel | Significado |
|---|---|
| N0 Normal | por debajo del primer umbral |
| N1 Vigilancia | caudal alto |
| N2 Aviso | crecida importante y caudal subiendo |
| N3 Peligro | riesgo de desbordamiento, o aviso rojo vigente |
| Sin datos | lectura vieja o ausente; se mantiene el último nivel conocido |

Es una escala propia de esta página, no una escala oficial. Cada nivel lleva texto y símbolo, nunca solo color.

- **Valencia (CHJ):** los umbrales son los oficiales del SAIH, se leen en vivo.
- **Catalunya (ACA):** no hay umbrales públicos por estación. Los de aquí son **estimados** a partir de los máximos anuales de la serie histórica de caudales diarios (mediana, percentil 80 y 95) y están marcados como «estimado, no oficial». Las medias diarias subestiman los picos y los ríos regulados no siguen esa estadística: son una referencia, no una norma. Las estaciones sin serie suficiente muestran el caudal sin nivel («umbral en estudio»).
- **Avisos:** un aviso rojo de AEMET eleva a N3 las estaciones de su región. INUNCAT solo las eleva en fase de emergencia; la fase de alerta se muestra como aviso pero no cambia los niveles, porque es un estado habitual durante episodios largos.
- **Previsión:** es solo informativa. Nunca cambia un nivel ni dispara un aviso. Puede añadir la etiqueta «Podría llegar a …».

## Límites

- No hay feed público para el Segre, el Ebre ni el Noguera; faltan en esta fase.
- Las cuencas rápidas (ramblas, Poyo, rieras) pueden crecer entre dos lecturas. La previsión de caudal sale de GloFAS, que tiene una malla de unos 5 km y un dato por día, y no capta esas crecidas.
- La página de aforos de la CHJ no es una API oficial y podría cambiar sin aviso.
- Los datos son provisionales y sin validar.

## Fuentes

Agència Catalana de l'Aigua (ACA, API Sentilo), SAIH de la Confederación Hidrográfica del Júcar, AEMET (avisos), Protecció Civil de Catalunya (INUNCAT, datos abiertos de la Generalitat), serie histórica de caudales diarios de la Generalitat (para los umbrales estimados) y [Open-Meteo.com](https://open-meteo.com) (CC BY 4.0; su API gratuita es solo para uso no comercial).

## Cómo funciona

Un workflow de GitHub Actions corre cada 15 minutos (`.github/workflows/actualizar.yml`), ejecuta `fuente/actualizar.py` y escribe `data/*.json`. Solo hace commit si cambió algún nivel o es la primera ejecución de la hora; el estado entre ejecuciones se guarda en la caché de Actions. Si un cambio de nivel lo justifica, `fuente/notificar.py` abre un issue (quien sigue el repositorio recibe el aviso). La página (`index.html`) es estática y lee los JSON con `fetch`.

```
fuente/alertas.py          máquina de niveles (función pura)
fuente/fuentes/            clientes de ACA, CHJ, AEMET/INUNCAT y Open-Meteo
fuente/actualizar.py       orquestador
fuente/estaciones.json     catálogo de estaciones y umbrales
fuente/herramientas/       verificar estaciones y calibrar umbrales (a mano)
fuente/page.html           plantilla; textos en fuente/textos.json (es y ca)
```

Para reconstruir la página tras tocar la plantilla, los textos o la lógica: `python3 fuente/armar_sitio.py`.

### Pruebas

```
pip install pytest
python3 -m pytest
node --test "tests/web/*.test.js"
```

Las herramientas de `fuente/herramientas/` usan red y no forman parte de las pruebas.

## Créditos y licencia

Hecho por Pablo Dodda. Adaptación para Catalunya: Sebastian Andrada. Licencia MIT.
