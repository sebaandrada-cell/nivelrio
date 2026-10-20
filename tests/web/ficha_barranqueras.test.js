const test = require("node:test");
const assert = require("node:assert/strict");
const F = require("../../fuente/web/ficha_barranqueras.js");
const TEXTOS = require("../../fuente/textos.json");

const AHORA = Date.parse("2026-10-20T20:00:00Z");
const EST = { id: "parana-barranqueras", zona: "chaco-corrientes", unidad: "m", valor: 7.24, sd: false, t_utc: "2026-10-20T19:00:00Z",
  umbrales: { bajo: 5.5, medio: 6, alto: 6.5, tipo: "oficial" } };
const SIT = { fecha: "2026-10-19", actualizado: "2026-10-20T15:14:23-03:00", resumen: { es: "r", ca: "r", en: "r" }, fuentes: "APA Chaco" };
const UMB = { niveles: [{ altura_m: 6, tipo: "alerta", nombre: { es: "a", ca: "a", en: "a" } }, { altura_m: 6.5, tipo: "evacuacion", nombre: { es: "e", ca: "e", en: "e" } }] };
const PREV = { generado_utc: "2026-10-20T19:00:00Z", zonas: { "chaco-corrientes": [
  { fecha: "2026-10-20", mm: 0, prob: 0 }, { fecha: "2026-10-21", mm: 9.5, prob: 70 }, { fecha: "2026-10-22", mm: 11, prob: 80 }] } };
const opts = (extra) => Object.assign({ estacion: EST, situacion: SIT, umbrales: UMB, pronostico: null, lluvia: PREV, lang: "es", textos: TEXTOS.es.ficha_barr, ahora: AHORA }, extra);

test("reglaCompuertas: por debajo de la alerta abiertas, en la alerta puede cerrar, por encima cerradas", () => {
  assert.equal(F.reglaCompuertas(5.9, 6), "abiertas");
  assert.equal(F.reglaCompuertas(6, 6), "puede cerrar");
  assert.equal(F.reglaCompuertas(6.6, 6), "cerradas");
  assert.equal(F.reglaCompuertas(0, 6), "abiertas");
  assert.equal(F.reglaCompuertas(6.0001, 6), "cerradas");
});

test("reglaCompuertas: sin valor, con NaN o con alerta ausente devuelve null y no lanza", () => {
  for (const h of [null, undefined, NaN, "6.6", Infinity]) assert.equal(F.reglaCompuertas(h, 6), null);
  for (const a of [null, undefined, NaN]) assert.equal(F.reglaCompuertas(6.6, a), null);
});

test("estadoFicha: los niveles de alerta y evacuación salen del registro (umbrales de la estación)", () => {
  const s = F.estadoFicha(opts());
  assert.equal(s.alerta, 6);
  assert.equal(s.evacuacion, 6.5);
  assert.equal(s.estado, "cerradas");
  assert.equal(s.conflicto, false);
});

test("estadoFicha: si umbrales.json discrepa del registro gana el registro y queda marcado", () => {
  const raro = { niveles: [{ altura_m: 5.8, tipo: "alerta" }, { altura_m: 6.5, tipo: "evacuacion" }] };
  const s = F.estadoFicha(opts({ umbrales: raro }));
  assert.equal(s.alerta, 6);
  assert.equal(s.conflicto, true);
});

test("estadoFicha: tres estados según la altura simulada", () => {
  const con = (valor) => F.estadoFicha(opts({ estacion: Object.assign({}, EST, { valor }) })).estado;
  assert.equal(con(5.9), "abiertas");
  assert.equal(con(6), "puede cerrar");
  assert.equal(con(6.6), "cerradas");
});

test("estadoFicha: sin lectura vigente (sd o sin valor) no hay estado y se dice", () => {
  for (const e of [{ sd: true }, { valor: null }, { valor: NaN }]) {
    const s = F.estadoFicha(opts({ estacion: Object.assign({}, EST, e) }));
    assert.equal(s.estado, null);
    assert.match(F.construirHtml(opts({ estacion: Object.assign({}, EST, e) })), /fb-sin-lectura/);
  }
});

test("estadoFicha: sin umbrales oficiales no se aplica la regla", () => {
  const s = F.estadoFicha(opts({ estacion: Object.assign({}, EST, { umbrales: { bajo: null, medio: null, alto: null, tipo: "en_estudio" } }) }));
  assert.equal(s.estado, null);
});

test("estadoFicha: la situación y la lluvia llevan su fecha y se marcan vencidas pasado su plazo", () => {
  let s = F.estadoFicha(opts());
  assert.equal(s.situacion.vencida, false);
  assert.equal(s.lluvia.vencida, false);
  s = F.estadoFicha(opts({ ahora: Date.parse("2026-10-23T00:00:00Z") }));
  assert.equal(s.situacion.vencida, true);
  assert.equal(s.lluvia.vencida, true);
});

test("estadoFicha: lluvia por día de la zona de la estación; sin zona o sin previsión queda vacía", () => {
  assert.equal(F.estadoFicha(opts()).lluvia.dias.length, 3);
  assert.deepEqual(F.estadoFicha(opts({ lluvia: null })).lluvia.dias, []);
  assert.deepEqual(F.estadoFicha(opts({ lluvia: { generado_utc: PREV.generado_utc, zonas: {} } })).lluvia.dias, []);
});

test("estadoFicha: un pronóstico vigente proyecta la regla; uno vencido no", () => {
  const vigente = { manual: true, fecha: "2026-10-20", fuente: "x", puntos: [["2026-10-21T12:00:00Z", 6.75, 7.55]] };
  let p = F.estadoFicha(opts({ pronostico: vigente })).pronostico;
  assert.equal(p.vencido, false);
  assert.deepEqual([p.estadoMin, p.estadoMax], ["cerradas", "cerradas"]);
  p = F.estadoFicha(opts({ pronostico: { manual: true, fecha: "2026-10-13", fuente: "x", puntos: [["2026-10-20T12:00:00Z", 6.75, 7.55]] } })).pronostico;
  assert.equal(p.vencido, true);
  assert.equal(p.estadoMin, null);
  const cruza = F.estadoFicha(opts({ pronostico: { manual: true, fecha: "2026-10-20", fuente: "x", puntos: [["2026-10-21T12:00:00Z", 5.8, 6.6]] } })).pronostico;
  assert.deepEqual([cruza.estadoMin, cruza.estadoMax], ["abiertas", "cerradas"]);
});

test("construirHtml: el esquema dice que sigue la regla de la APA y no el estado real, en los tres idiomas", () => {
  for (const lang of ["es", "ca", "en"]) {
    const h = F.construirHtml(opts({ lang, textos: TEXTOS[lang].ficha_barr }));
    assert.ok(h.includes(TEXTOS[lang].ficha_barr.esquema_aviso), lang);
    assert.match(h, /<svg[^>]+role="img"/);
    assert.match(h, /aria-describedby="fb-desc"/);
    assert.match(h, /id="fb-desc"/);
    assert.ok(h.includes(TEXTOS[lang].ficha_barr.palabra_cerradas), lang);
  }
});

test("construirHtml: no contiene direcciones externas ni analítica", () => {
  const h = F.construirHtml(opts());
  assert.doesNotMatch(h, /https?:\/\//);
  assert.doesNotMatch(h, /cloudflare|clarity/i);
});

test("construirHtml: escapa el texto que viene de los archivos", () => {
  const h = F.construirHtml(opts({ situacion: Object.assign({}, SIT, { resumen: { es: "<img src=x onerror=1>", ca: "x", en: "x" }, fuentes: "<b>" }) }));
  assert.doesNotMatch(h, /<img src=x/);
  assert.ok(h.includes("&lt;img"));
});

test("el corte avanza de a un paso, sin saltarse ninguno ni pasar del último", () => {
  assert.equal(F.pasoSiguiente(0), 1);
  assert.equal(F.pasoSiguiente(2), 3);
  assert.equal(F.pasoSiguiente(3), 3);
  assert.equal(F.PASOS_CORTE, 3);
});

test("la animación del corte solo existe con movimiento permitido: el módulo no usa temporizadores", () => {
  const fuente = require("node:fs").readFileSync(require.resolve("../../fuente/web/ficha_barranqueras.js"), "utf8");
  assert.doesNotMatch(fuente, /setTimeout|setInterval|requestAnimationFrame/);
});
