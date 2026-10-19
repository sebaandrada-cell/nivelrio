/* Lógica pura de la página (sin DOM). Se prueba con `node --test tests/web/` y se incrusta en index.html. */
(function (root, factory) {
  const L = factory();
  if (typeof module === "object" && module.exports) module.exports = L;
  else root.Logica = L;
})(typeof self !== "undefined" ? self : this, function () {
  const ROTULOS = {
    es: ["Normal", "Vigilancia", "Aviso", "Peligro"],
    ca: ["Normal", "Vigilància", "Avís", "Perill"],
  };
  const SIN_DATOS = { es: "Sin datos", ca: "Sense dades" };
  // Símbolos distintos por nivel: el nivel nunca se comunica solo con color.
  const SIMBOLOS = ["●", "◆", "▲", "■"];
  const SIMBOLO_SD = "○";
  const UMBRAL_TEXTO = {
    es: { oficial: "oficial", estimado: "estimado, no oficial", en_estudio: "umbral en estudio" },
    ca: { oficial: "oficial", estimado: "estimat, no oficial", en_estudio: "llindar en estudi" },
  };
  const LIMITE_DATOS_VIEJOS_MIN = 90;

  function edadTexto(minutos, lang) {
    if (minutos === null || minutos === undefined || Number.isNaN(minutos)) return "—";
    const pre = lang === "ca" ? "fa" : "hace";
    const m = Math.max(0, Math.round(minutos));
    if (m >= 1440) return `${pre} ${Math.floor(m / 1440)} d`;
    if (m >= 60) {
      const h = Math.floor(m / 60), r = m % 60;
      return r ? `${pre} ${h} h ${r} min` : `${pre} ${h} h`;
    }
    return `${pre} ${m} min`;
  }

  function nivelRotulo(nivel, sd, lang) {
    const l = lang === "ca" ? "ca" : "es";
    if (sd) return { texto: SIN_DATOS[l], simbolo: SIMBOLO_SD };
    return { texto: ROTULOS[l][nivel], simbolo: SIMBOLOS[nivel] };
  }

  function tipoUmbralTexto(tipo, lang) {
    return (UMBRAL_TEXTO[lang === "ca" ? "ca" : "es"] || {})[tipo] || "";
  }

  function idiomaInicial(search, guardado) {
    const m = /[?&]lang=(es|ca)(?:&|$)/.exec(search || "");
    if (m) return m[1];
    return guardado === "ca" || guardado === "es" ? guardado : "es";
  }

  function ratio(e) {
    const b = e.umbrales && e.umbrales.bajo;
    return b > 0 && typeof e.valor === "number" ? e.valor / b : -1;
  }

  function ordenarPorPeligro(estaciones) {
    return estaciones.slice().sort((a, b) =>
      b.nivel - a.nivel || Number(a.sd) - Number(b.sd) || String(a.rio).localeCompare(String(b.rio), "es"));
  }

  function resumenPorNivel(estaciones) {
    const niveles = [0, 0, 0, 0];
    let sd = 0;
    estaciones.forEach((e) => { niveles[e.nivel]++; if (e.sd) sd++; });
    return { niveles, sd };
  }

  // Una entrada por río. La estación principal es la de mayor nivel; a igual nivel, la que tiene dato
  // y está más cerca de su umbral; si no hay umbrales, la primera de la lista.
  function agruparPorRio(estaciones) {
    const orden = new Map();
    estaciones.forEach((e, i) => orden.set(e, i));
    const cmp = (a, b) =>
      b.nivel - a.nivel || Number(a.sd) - Number(b.sd) || ratio(b) - ratio(a) || orden.get(a) - orden.get(b);
    const por = new Map();
    estaciones.forEach((e) => { if (!por.has(e.rio)) por.set(e.rio, []); por.get(e.rio).push(e); });
    const grupos = [...por.entries()].map(([rio, lista]) => {
      const ord = lista.slice().sort(cmp);
      return { rio, estaciones: ord, principal: ord[0] };
    });
    return grupos.sort((x, y) => cmp(x.principal, y.principal));
  }

  // puntos: [[iso, valor], ...] en orden temporal. Compara el último con el de ~1 h antes.
  function tendencia(puntos) {
    if (!puntos || puntos.length < 2) return null;
    const ult = puntos[puntos.length - 1];
    const tUlt = Date.parse(ult[0]);
    let ref = null;
    for (let i = puntos.length - 2; i >= 0; i--) {
      if (tUlt - Date.parse(puntos[i][0]) >= 50 * 60000) { ref = puntos[i]; break; }
    }
    if (!ref) return null;
    const delta = ult[1] - ref[1];
    if (Math.abs(delta) <= 0.1 * Math.max(ref[1], 0.01)) return "estable";
    return delta > 0 ? "sube" : "baja";
  }

  function filtrarRango(puntos, ahoraMs, horas) {
    const desde = ahoraMs - horas * 3600000;
    return puntos.filter((p) => Date.parse(p[0]) >= desde);
  }

  function nivelAviso(color) {
    return { amarillo: 1, naranja: 2, rojo: 3 }[color] || 0;
  }

  function datosViejos(generadoIso, ahoraMs) {
    if (!generadoIso) return true;
    return (ahoraMs - Date.parse(generadoIso)) / 60000 > LIMITE_DATOS_VIEJOS_MIN;
  }

  // La edad se calcula en el navegador: «edad_min» del JSON queda congelada en el momento de generarlo.
  function edadMin(iso, ahoraMs) {
    if (!iso) return null;
    return Math.max(0, Math.floor((ahoraMs - Date.parse(iso)) / 60000));
  }

  // Añade la lectura actual al historial horario: el historial guarda un punto por hora (el pico) y
  // compararlo con el valor actual evita que un pico de hace 50 min haga parecer que el río «baja».
  function serieConActual(hist, tIso, valor) {
    if (valor == null) return hist;
    return hist.concat([[tIso, valor]]);
  }

  return { edadMin, serieConActual, edadTexto, nivelRotulo, tipoUmbralTexto, idiomaInicial, ordenarPorPeligro, resumenPorNivel,
    agruparPorRio, tendencia, filtrarRango, nivelAviso, datosViejos };
});
