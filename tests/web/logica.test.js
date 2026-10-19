const test = require("node:test");
const assert = require("node:assert/strict");
const L = require("../../fuente/web/logica.js");

test("edadTexto en minutos, horas y días", () => {
  assert.equal(L.edadTexto(7, "es"), "hace 7 min");
  assert.equal(L.edadTexto(190, "es"), "hace 3 h 10 min");
  assert.equal(L.edadTexto(60, "es"), "hace 1 h");
  assert.equal(L.edadTexto(2 * 1440 + 30, "es"), "hace 2 d");
  assert.equal(L.edadTexto(190, "ca"), "fa 3 h 10 min");
  assert.equal(L.edadTexto(0, "es"), "hace 0 min");
});

test("edadTexto sin dato devuelve guion", () => {
  assert.equal(L.edadTexto(null, "es"), "—");
});

test("nivelRotulo lleva texto y símbolo distintos por nivel", () => {
  assert.deepEqual(L.nivelRotulo(2, false, "es"), { texto: "Aviso", simbolo: "▲" });
  assert.equal(L.nivelRotulo(3, true, "es").texto, "Sin datos");
  assert.equal(L.nivelRotulo(1, false, "ca").texto, "Vigilància");
  const simbolos = [0, 1, 2, 3].map((n) => L.nivelRotulo(n, false, "es").simbolo);
  simbolos.push(L.nivelRotulo(0, true, "es").simbolo);
  assert.equal(new Set(simbolos).size, 5);
  assert.ok(simbolos.every((s) => s.length > 0));
});

test("ordenarPorPeligro: nivel descendente", () => {
  const e = [
    { id: "a", rio: "A", nivel: 0, sd: false },
    { id: "b", rio: "B", nivel: 3, sd: false },
    { id: "c", rio: "C", nivel: 1, sd: false },
  ];
  assert.deepEqual(L.ordenarPorPeligro(e).map((x) => x.id), ["b", "c", "a"]);
});

test("ordenarPorPeligro: a igual nivel, sin datos después; luego río; no muta la entrada", () => {
  const e = [
    { id: "sd", rio: "Ter", nivel: 2, sd: true },
    { id: "z", rio: "Ter", nivel: 2, sd: false },
    { id: "a", rio: "Anoia", nivel: 2, sd: false },
  ];
  const copia = JSON.parse(JSON.stringify(e));
  assert.deepEqual(L.ordenarPorPeligro(e).map((x) => x.id), ["a", "z", "sd"]);
  assert.deepEqual(e, copia);
});

test("tipoUmbralTexto", () => {
  assert.equal(L.tipoUmbralTexto("estimado", "es"), "estimado, no oficial");
  assert.equal(L.tipoUmbralTexto("en_estudio", "es"), "umbral en estudio");
  assert.equal(L.tipoUmbralTexto("oficial", "es"), "oficial");
  assert.equal(L.tipoUmbralTexto("estimado", "ca"), "estimat, no oficial");
});

test("idiomaInicial: la URL manda sobre lo guardado; por defecto castellano", () => {
  assert.equal(L.idiomaInicial("?lang=ca", "es"), "ca");
  assert.equal(L.idiomaInicial("?lang=es", "ca"), "es");
  assert.equal(L.idiomaInicial("", null), "es");
  assert.equal(L.idiomaInicial("", "ca"), "ca");
  assert.equal(L.idiomaInicial("?lang=xx", "ca"), "ca");
  assert.equal(L.idiomaInicial("?lang=xx", "fr"), "es");
});

test("resumenPorNivel cuenta por nivel y aparte las estaciones sin datos", () => {
  const e = [
    { nivel: 3, sd: false }, { nivel: 3, sd: true }, { nivel: 0, sd: false }, { nivel: 1, sd: false }, { nivel: 0, sd: true },
  ];
  assert.deepEqual(L.resumenPorNivel(e), { niveles: [2, 1, 0, 2], sd: 2 });
});

test("agruparPorRio elige la estación más relevante de cada río y ordena los ríos por peligro", () => {
  const u = { bajo: 10, medio: 20, alto: 40, tipo: "estimado" };
  const e = [
    { id: "t1", rio: "Ter", nivel: 0, sd: false, valor: 2, umbrales: u },
    { id: "t2", rio: "Ter", nivel: 1, sd: false, valor: 12, umbrales: u },
    { id: "b1", rio: "Besòs", nivel: 3, sd: false, valor: 50, umbrales: u },
    { id: "l1", rio: "Llobregat", nivel: 0, sd: false, valor: 8, umbrales: u },
    { id: "l2", rio: "Llobregat", nivel: 0, sd: false, valor: 3, umbrales: u },
  ];
  const g = L.agruparPorRio(e);
  assert.deepEqual(g.map((x) => x.rio), ["Besòs", "Ter", "Llobregat"]);
  assert.equal(g[1].principal.id, "t2");
  assert.equal(g[2].principal.id, "l1"); // mismo nivel: la que está más cerca de su umbral
  assert.equal(g[1].estaciones.length, 2);
});

test("agruparPorRio sin umbrales conserva el orden de entrada", () => {
  const u = { bajo: null, medio: null, alto: null, tipo: "en_estudio" };
  const e = [
    { id: "a", rio: "Cardener", nivel: 0, sd: false, valor: 5, umbrales: u },
    { id: "b", rio: "Cardener", nivel: 0, sd: false, valor: 9, umbrales: u },
  ];
  assert.equal(L.agruparPorRio(e)[0].principal.id, "a");
});

test("tendencia compara el último punto con el de una hora antes", () => {
  const h = (min, v) => [new Date(Date.UTC(2026, 9, 19, 12, 0) + min * 60000).toISOString(), v];
  assert.equal(L.tendencia([h(0, 10), h(60, 20)]), "sube");
  assert.equal(L.tendencia([h(0, 20), h(60, 10)]), "baja");
  assert.equal(L.tendencia([h(0, 20), h(60, 20.5)]), "estable");
  assert.equal(L.tendencia([h(0, 20)]), null);
  assert.equal(L.tendencia([]), null);
});

test("filtrarRango deja solo los puntos de las últimas N horas", () => {
  const ahora = Date.UTC(2026, 9, 19, 12, 0);
  const p = [["2026-10-17T11:00:00Z", 1], ["2026-10-19T00:00:00Z", 2], ["2026-10-19T11:00:00Z", 3]];
  assert.deepEqual(L.filtrarRango(p, ahora, 48), [["2026-10-19T00:00:00Z", 2], ["2026-10-19T11:00:00Z", 3]]);
});

test("nivelAviso traduce el color del aviso a nivel 1-3", () => {
  assert.equal(L.nivelAviso("amarillo"), 1);
  assert.equal(L.nivelAviso("naranja"), 2);
  assert.equal(L.nivelAviso("rojo"), 3);
  assert.equal(L.nivelAviso("x"), 0);
});

test("datosViejos avisa cuando el servidor lleva más de 90 min sin actualizar", () => {
  const ahora = Date.UTC(2026, 9, 19, 12, 0);
  assert.equal(L.datosViejos("2026-10-19T11:30:00Z", ahora), false);
  assert.equal(L.datosViejos("2026-10-19T10:40:00Z", ahora), false); // se publica cada hora: 80 min aún es normal
  assert.equal(L.datosViejos("2026-10-19T10:20:00Z", ahora), true);
  assert.equal(L.datosViejos(null, ahora), true);
});

test("edadMin se calcula con el reloj del navegador, no con el del servidor", () => {
  const ahora = Date.UTC(2026, 9, 19, 12, 0);
  assert.equal(L.edadMin("2026-10-19T11:16:00Z", ahora), 44);
  assert.equal(L.edadMin(null, ahora), null);
  assert.equal(L.edadMin("2026-10-19T12:05:00Z", ahora), 0);
});

test("serieConActual añade la lectura actual para que el pico horario no falsee la tendencia", () => {
  const hist = [["2026-10-19T09:00:00Z", 95], ["2026-10-19T10:00:00Z", 100]];
  const s = L.serieConActual(hist, "2026-10-19T10:50:00Z", 70);
  assert.equal(s.length, 3);
  assert.equal(L.tendencia(s), "baja");
  assert.deepEqual(L.serieConActual(hist, "2026-10-19T10:50:00Z", null), hist);
});
