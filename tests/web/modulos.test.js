const test = require("node:test");
const assert = require("node:assert/strict");
const M = require("../../fuente/web/modulos.js");

const U = { bajo: 5.5, medio: 6, alto: 6.5, tipo: "oficial" };

test("compararConHistoricas: diferencia con la crecida y orden de mayor a menor", () => {
  const r = M.compararConHistoricas(7.2, [{ evento: "1983", valor: 8.6, nota: "n" }]);
  assert.equal(r.length, 1);
  assert.ok(Math.abs(r[0].diferencia - -1.4) < 1e-9);
  assert.equal(r[0].nota, "n");
  const o = M.compararConHistoricas(7.2, [
    { evento: "2013", valor: 7.09 }, { evento: "1983", valor: 8.6 }, { evento: "1992", valor: 8.25 }]);
  assert.deepEqual(o.map((x) => x.evento), ["1983", "1992", "2013"]);
  assert.ok(o[2].diferencia > 0);
});

test("compararConHistoricas: sin valor actual no lanza y deja la diferencia en null", () => {
  for (const v of [null, undefined, NaN]) {
    const r = M.compararConHistoricas(v, [{ evento: "1983", valor: 8.6 }]);
    assert.equal(r[0].diferencia, null);
    assert.equal(r[0].valor, 8.6);
  }
  assert.deepEqual(M.compararConHistoricas(5, null), []);
  assert.deepEqual(M.compararConHistoricas(5, [{ evento: "x", valor: "a" }, null]), []);
});

test("simular: nivel por umbrales y distancia a cada uno", () => {
  const s = M.simular(6.2, U);
  assert.equal(s.nivel, 2);
  assert.equal(s.textoClave, "mod_sim_n2");
  assert.ok(Math.abs(s.distancias.N1 - -0.7) < 1e-9);   // ya superado por 0,7
  assert.ok(Math.abs(s.distancias.N2 - -0.2) < 1e-9);
  assert.ok(Math.abs(s.distancias.N3 - 0.3) < 1e-9);    // faltan 0,3
  assert.equal(M.simular(5, U).nivel, 0);
  assert.equal(M.simular(5.5, U).nivel, 1);              // el umbral cuenta como alcanzado, igual que el motor de alertas
  assert.equal(M.simular(9, U).nivel, 3);
});

test("simular: valor nulo, NaN o texto no lanza", () => {
  for (const v of [null, undefined, NaN, "abc", Infinity]) {
    const s = M.simular(v, U);
    assert.equal(s.nivel, null);
    assert.equal(s.textoClave, "mod_sim_sin_valor");
    assert.deepEqual(s.distancias, { N1: null, N2: null, N3: null });
  }
});

test("simular: sin umbrales (en estudio) no inventa un nivel", () => {
  for (const u of [null, undefined, { bajo: null, medio: null, alto: null, tipo: "en_estudio" }, { bajo: 1, medio: 2, alto: 3, tipo: "en_estudio" }]) {
    const s = M.simular(4, u);
    assert.equal(s.nivel, null);
    assert.equal(s.textoClave, "mod_sim_sin_umbrales");
    assert.deepEqual(s.distancias, { N1: null, N2: null, N3: null });
  }
});

test("leerEntrada acepta coma o punto y rechaza lo que no es número", () => {
  assert.equal(M.leerEntrada("6,2"), 6.2);
  assert.equal(M.leerEntrada(" 6.25 "), 6.25);
  assert.equal(M.leerEntrada("-1"), -1);
  for (const x of ["", "  ", "abc", "6,2,1", null, undefined, "1e999", "NaN"]) assert.equal(M.leerEntrada(x), null);
});

test("serieConPronostico marca el último observado y los pronosticados", () => {
  const hist = [["2026-10-20T00:00:00Z", 6.0], ["2026-10-20T06:00:00Z", 6.1], ["2026-10-20T12:00:00Z", 6.2]];
  const pr = { puntos: [["2026-10-20T06:00:00Z", 9], ["2026-10-20T18:00:00Z", 6.3], ["2026-10-21T00:00:00Z", 6.5]] };
  const s = M.serieConPronostico(hist, pr);
  assert.deepEqual(s.map((p) => p.tipo), ["obs", "obs", "obs", "prono", "prono"]);
  assert.equal(s.filter((p) => p.ultimo).length, 1);
  assert.equal(s[2].ultimo, true);
  assert.equal(s[3].v, 6.3);
  assert.equal(s[0].t, Date.parse("2026-10-20T00:00:00Z"));
  // el punto pronosticado anterior a la última lectura se descarta: ya hay un dato real
  assert.ok(!s.some((p) => p.v === 9));
});

test("serieConPronostico: sin pronóstico, sin historial y rangos", () => {
  assert.deepEqual(M.serieConPronostico([], null), []);
  const h = [["2026-10-20T00:00:00Z", 6]];
  assert.deepEqual(M.serieConPronostico(h, null).map((p) => p.tipo), ["obs"]);
  assert.deepEqual(M.serieConPronostico(h, { puntos: "x" }).map((p) => p.tipo), ["obs"]);
  const r = M.serieConPronostico(h, { puntos: [["2026-10-21T12:00:00Z", 5.8, 6.6], ["basura", 1], ["2026-10-22T00:00:00Z", NaN]] });
  assert.equal(r.length, 2);
  assert.equal(r[1].tipo, "prono");
  assert.equal(r[1].v, null);
  assert.equal(r[1].min, 5.8);
  assert.equal(r[1].max, 6.6);
  const solo = M.serieConPronostico([], { puntos: [["2026-10-21T12:00:00Z", 6]] });
  assert.deepEqual(solo.map((p) => p.tipo), ["prono"]);
});

test("pronosticoVencido: más de 36 h desde la fecha del pronóstico", () => {
  const ahora = Date.parse("2026-10-21T12:00:00Z");
  assert.equal(M.pronosticoVencido({ generado_utc: "2026-10-20T12:00:00Z" }, ahora), false);     // 24 h
  assert.equal(M.pronosticoVencido({ generado_utc: "2026-10-20T00:00:00Z" }, ahora), false);     // 36 h justas
  assert.equal(M.pronosticoVencido({ generado_utc: "2026-10-19T23:59:00Z" }, ahora), true);
  assert.equal(M.pronosticoVencido({ fecha: "2026-10-20" }, ahora), false);
  assert.equal(M.pronosticoVencido({ fecha: "2026-10-19" }, ahora), true);
  assert.equal(M.pronosticoVencido({}, ahora), true);       // sin fecha no se puede afirmar que sea vigente
  assert.equal(M.pronosticoVencido(null, ahora), true);
});
