/* Lógica pura de la página (sin DOM). Se prueba con `node --test tests/web/` y se incrusta en index.html. */
(function (root, factory) {
  const L = factory();
  if (typeof module === "object" && module.exports) module.exports = L;
  else root.Logica = L;
})(typeof self !== "undefined" ? self : this, function () {
  const ROTULOS = {
    es: ["Normal", "Vigilancia", "Aviso", "Peligro"],
    ca: ["Normal", "Vigilància", "Avís", "Perill"],
    en: ["Normal", "Watch", "Alert", "Danger"],
  };
  const SIN_DATOS = { es: "Sin datos", ca: "Sense dades", en: "No data" };
  // Inicial de cada umbral (el 1.º, 2.º y 3.º) en los rótulos de las gráficas y de las tarjetas.
  const LETRAS_UMBRAL = { es: "VAP", ca: "VAP", en: "WAD" };
  const IDIOMAS = ["es", "ca", "en"];
  const LOCALES = { es: "es-ES", ca: "ca-ES", en: "en-US" };
  // Símbolos distintos por nivel: el nivel nunca se comunica solo con color.
  const SIMBOLOS = ["●", "◆", "▲", "■"];
  const SIMBOLO_SD = "○";
  const UMBRAL_TEXTO = {
    es: { oficial: "oficial", estimado: "estimado, no oficial", en_estudio: "umbral en estudio" },
    ca: { oficial: "oficial", estimado: "estimat, no oficial", en_estudio: "llindar en estudi" },
    en: { oficial: "official", estimado: "estimated, unofficial", en_estudio: "threshold under review" },
  };
  const LIMITE_DATOS_VIEJOS_MIN = 90;

  const idioma = (lang) => (IDIOMAS.includes(lang) ? lang : "es");
  const localeDe = (lang) => LOCALES[idioma(lang)];

  // Duración sin prefijo ni sufijo: «3 h 10 min».
  function duracionTexto(minutos) {
    if (minutos === null || minutos === undefined || Number.isNaN(minutos)) return "—";
    const m = Math.max(0, Math.round(minutos));
    if (m >= 1440) return `${Math.floor(m / 1440)} d`;
    if (m >= 60) {
      const h = Math.floor(m / 60), r = m % 60;
      return r ? `${h} h ${r} min` : `${h} h`;
    }
    return `${m} min`;
  }

  function edadTexto(minutos, lang) {
    const d = duracionTexto(minutos);
    if (d === "—") return d;
    if (lang === "en") return `${d} ago`;
    return `${lang === "ca" ? "fa" : "hace"} ${d}`;
  }

  function nivelRotulo(nivel, sd, lang) {
    const l = idioma(lang);
    if (sd) return { texto: SIN_DATOS[l], simbolo: SIMBOLO_SD };
    return { texto: ROTULOS[l][nivel], simbolo: SIMBOLOS[nivel] };
  }

  function tipoUmbralTexto(tipo, lang) {
    return (UMBRAL_TEXTO[idioma(lang)] || {})[tipo] || "";
  }

  // La URL manda; después lo guardado; después el idioma del navegador (solo en* → en); por defecto castellano.
  function idiomaInicial(search, guardado, navegador) {
    const m = /[?&]lang=(es|ca|en)(?:&|$)/.exec(search || "");
    if (m) return m[1];
    if (IDIOMAS.includes(guardado)) return guardado;
    return /^en(?:[-_]|$)/i.test(String(navegador || "")) ? "en" : "es";
  }

  function letraUmbral(i, lang) { return LETRAS_UMBRAL[idioma(lang)][i] || ""; }

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

  // ---------- países ----------
  const PAISES = ["ar", "es", "us", "de", "fr", "gb", "it", "nl", "pl", "pt", "hu", "ru",
    "asia", "centroamerica", "sudamerica", "oceania", "africa"];
  const POR_NIVEL_VACIO = () => [0, 0, 0, 0];

  function paisDesdeHash(hash, porDefecto) {
    const p = String(hash || "").replace(/^#/, "").toLowerCase();
    return PAISES.includes(p) ? p : porDefecto;
  }

  function hashPara(pais) { return "#" + pais; }

  function rutaDatos(pais, archivo) { return "data/" + pais + "/" + archivo; }

  // País inicial según el idioma del navegador: ca y es-ES → es, es-AR → ar, en-US → us; el resto, es.
  function paisPorIdioma(idioma) {
    const l = String(idioma || "").toLowerCase().replace("_", "-");
    if (l === "es-ar") return "ar";
    if (l === "en-us") return "us";
    return "es";
  }

  // Una entrada de data/paises.json: {estaciones: N, por_nivel: [n0..n3], sd, ...}. Sin entrada, todo a cero.
  function resumenPais(entrada) {
    const e = entrada || {};
    const porNivel = POR_NIVEL_VACIO();
    (Array.isArray(e.por_nivel) ? e.por_nivel : []).slice(0, 4).forEach((v, i) => { porNivel[i] = Number(v) || 0; });
    return { n: Number(e.estaciones) || 0, porNivel, sd: Number(e.sd) || 0 };
  }

  // La unidad se muestra como la publica la fuente: metros en Argentina, pies en EE. UU., sin convertir.
  const UNIDADES = { m3s: "m³/s", m: "m", ft: "ft", mm: "mm" };
  function unidadTexto(unidad) { return UNIDADES[unidad] || ""; }

  // Número con los separadores del idioma y los decimales que caben según su tamaño.
  function formatoNumero(valor, lang) {
    if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
    const v = Math.abs(valor);
    return new Intl.NumberFormat(localeDe(lang), { maximumFractionDigits: v >= 100 ? 0 : v >= 10 ? 1 : 2 }).format(valor);
  }

  // Único punto de formato de una medida: «6,1 m», «28 ft», «41,2 m³/s». Nunca convierte de unidad.
  function formatoValor(valor, unidad, lang) {
    const n = formatoNumero(valor, lang);
    const u = unidadTexto(unidad);
    return n === "—" || !u ? n : `${n} ${u}`;
  }

  // Rango vertical de los gráficos. El caudal parte de cero; una altura de río se ajusta a sus datos,
  // porque con un 0 de base una variación de decímetros se vería como una línea recta.
  function rangoY(unidad, valores, umbralBajo) {
    const vs = valores.filter((v) => typeof v === "number");
    const hi = Math.max(...vs, 0.5);
    if (unidad === "m3s" || !vs.length) {
      return { min: 0, max: Math.max(hi * 1.08, umbralBajo ? umbralBajo * 1.35 : 0, 0.5) };
    }
    const lo = Math.min(...vs, umbralBajo == null ? Infinity : umbralBajo);
    const tope = Math.max(hi, umbralBajo == null ? -Infinity : umbralBajo * 1.05);
    const hueco = Math.max((tope - lo) * 0.15, 0.1);
    return { min: lo - hueco, max: tope + hueco };
  }

  return { PAISES, paisDesdeHash, hashPara, rutaDatos, paisPorIdioma, resumenPais, unidadTexto, formatoNumero, formatoValor, duracionTexto, letraUmbral, localeDe, rangoY, edadMin, serieConActual, edadTexto, nivelRotulo, tipoUmbralTexto, idiomaInicial, ordenarPorPeligro, resumenPorNivel,
    agruparPorRio, tendencia, filtrarRango, nivelAviso, datosViejos };
});
