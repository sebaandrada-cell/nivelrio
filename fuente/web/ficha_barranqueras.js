// Adapted from github.com/pablododda/apuratejose (MIT)
// Ficha del Paraná en Barranqueras: esquema de las compuertas del Río Negro según la regla de la APA,
// situación informada, pronóstico, lluvia prevista y un dibujo explicativo del «corte» bajo el dique.
// La idea y los datos de partida son de Pablo Dodda; el código es una reescritura sin analítica, sin dominios
// propios, sin d3 y sin temporizadores: el dibujo del corte avanza solo cuando la persona pulsa el botón.
//
// API pública: FichaBarranqueras.montar(el, {estacion, situacion, lluvia, pronostico, lang, textos, umbrales})
//   estacion   fila de latest.json (valor, sd, t_utc, zona, unidad, umbrales)
//   situacion  modulos/ar/<id>/situacion.json      lluvia  data/ar/prevision.json (previsión del robot)
//   pronostico modulos/ar/<id>/pronostico_manual.json (opcional)   umbrales  modulos/ar/<id>/umbrales.json (opcional)
//   textos     T[lang].ficha_barr
// Los niveles de alerta y evacuación son los del registro oficial (estacion.umbrales); umbrales.json solo se
// contrasta con ellos y, si discrepan, gana el registro.
(function (root, factory) {
  const F = factory();
  if (typeof module === "object" && module.exports) module.exports = F;
  else root.FichaBarranqueras = F;
})(typeof self !== "undefined" ? self : this, function () {
  const dep = (nombre, ruta) => (typeof self !== "undefined" && self[nombre]) || (typeof require === "function" ? require(ruta) : null);
  const L = dep("Logica", "./logica.js");
  const M = dep("Modulos", "./modulos.js");

  const PASOS_CORTE = 3;
  const ZONA_HORARIA = "America/Argentina/Buenos_Aires";
  let pasoCorte = 0;  // se conserva si la página repinta la ficha

  const num = (x) => typeof x === "number" && Number.isFinite(x);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (txt, vars) => String(txt == null ? "" : txt).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  const porIdioma = (x, lang) => (x && typeof x === "object" ? x[lang] || x.es || "" : x || "");

  // Regla de la APA para las compuertas del Río Negro, según la altura del Paraná en Barranqueras.
  // Por debajo de la alerta: abiertas. En la alerta: la APA puede cerrarlas. Por encima: cerradas.
  function reglaCompuertas(h, alerta) {
    if (!num(h) || !num(alerta)) return null;
    return h < alerta ? "abiertas" : h === alerta ? "puede cerrar" : "cerradas";
  }

  function pasoSiguiente(p) { return Math.min(PASOS_CORTE, p + 1); }

  // Todo lo que la ficha afirma, calculado aparte del dibujo.
  function estadoFicha(o) {
    const e = o.estacion || {}, ahora = num(o.ahora) ? o.ahora : Date.now(), u = e.umbrales || {};
    const oficial = u.tipo !== "en_estudio";
    const alerta = oficial && num(u.medio) ? u.medio : null;
    const evacuacion = oficial && num(u.alto) ? u.alto : null;
    const niveles = o.umbrales && Array.isArray(o.umbrales.niveles) ? o.umbrales.niveles : [];
    const delArchivo = (tipo) => { const n = niveles.find((x) => x && x.tipo === tipo); return n && num(n.altura_m) ? n.altura_m : null; };
    const conflicto = (delArchivo("alerta") != null && alerta != null && delArchivo("alerta") !== alerta)
      || (delArchivo("evacuacion") != null && evacuacion != null && delArchivo("evacuacion") !== evacuacion);
    const h = !e.sd && num(e.valor) ? e.valor : null;
    const estado = reglaCompuertas(h, alerta);

    const sit = o.situacion && typeof o.situacion === "object" ? { doc: o.situacion, vencida: M.situacionVencida(o.situacion, ahora) } : null;

    let pron = null;
    const p = o.pronostico;
    if (p && Array.isArray(p.puntos) && p.puntos.length && (!p.unidad || !e.unidad || p.unidad === e.unidad)) {
      const ult = p.puntos.slice().filter((q) => Array.isArray(q) && num(q[1])).sort((a, b) => Date.parse(a[0]) - Date.parse(b[0])).pop();
      if (ult) {
        const min = ult.length >= 3 && num(ult[2]) ? Math.min(ult[1], ult[2]) : ult[1], max = ult.length >= 3 && num(ult[2]) ? Math.max(ult[1], ult[2]) : ult[1];
        const vencido = M.pronosticoVencido(p, ahora);
        pron = { doc: p, vencido, punto: ult, min, max, rango: ult.length >= 3, estadoMin: vencido ? null : reglaCompuertas(min, alerta), estadoMax: vencido ? null : reglaCompuertas(max, alerta) };
      }
    }

    const prev = o.lluvia && typeof o.lluvia === "object" ? o.lluvia : null;
    const zona = prev && prev.zonas && e.zona ? prev.zonas[e.zona] : null;
    const dias = Array.isArray(zona) ? zona.filter((d) => d && d.fecha && num(d.mm)) : [];
    return {
      h, alerta, evacuacion, conflicto, estado, situacion: sit, pronostico: pron,
      lluvia: { dias, generado: prev ? prev.generado_utc : null, vencida: M.lluviaVencida(prev, ahora) },
    };
  }

  // ---------- dibujo ----------
  const W = 320, TOPE_M = 10;

  function esquema(s, t, val) {
    const H = 214, top = 20, bottom = 176, damL = 148, damW = 16, damR = damL + damW, gap = 30;
    const y = (m) => bottom - (Math.max(0, Math.min(TOPE_M, m)) / TOPE_M) * (bottom - top);
    const abierta = s.estado !== "cerradas";
    const rnH = abierta ? s.h : Math.min(s.h, s.alerta);
    let g = "";
    // agua: abierta, una sola agua que pasa por debajo del dique; cerrada, cada río por su lado
    g += `<rect class="fb-agua-pa" x="0" y="${y(s.h)}" width="${damL}" height="${bottom - y(s.h)}"/>`;
    if (abierta) g += `<rect class="fb-agua-pa" x="${damL}" y="${bottom - gap}" width="${damW}" height="${gap}"/>`;
    g += `<rect class="fb-agua-rn" x="${damR}" y="${y(rnH)}" width="${W - damR}" height="${bottom - y(rnH)}"/>`;
    g += `<line class="fb-sup-pa" x1="0" x2="${damL}" y1="${y(s.h)}" y2="${y(s.h)}"/><line class="fb-sup-rn" x1="${damR}" x2="${W}" y1="${y(rnH)}" y2="${y(rnH)}"/>`;
    // niveles de alerta y evacuación
    if (num(s.evacuacion)) g += `<line class="fb-ev" x1="0" x2="${W}" y1="${y(s.evacuacion)}" y2="${y(s.evacuacion)}"/><text class="fb-tx fb-ev-t" x="4" y="${y(s.evacuacion) - 3}">${esc(fmt(t.lbl_evac, { v: val(s.evacuacion) }))}</text>`;
    g += `<line class="fb-al" x1="0" x2="${W}" y1="${y(s.alerta)}" y2="${y(s.alerta)}"/><text class="fb-tx fb-al-t" x="${W - 4}" y="${y(s.alerta) + 11}" text-anchor="end">${esc(fmt(t.lbl_alerta, { v: val(s.alerta) }))}</text>`;
    // dique y compuertas
    g += `<rect class="fb-muro" x="${damL}" y="${top}" width="${damW}" height="${bottom - top - (abierta ? gap : 0)}" rx="2"/>`;
    if (s.estado === "puede cerrar") g += `<rect class="fb-muro-sombra" x="${damL}" y="${bottom - gap}" width="${damW}" height="${gap}" rx="2"/>`;
    g += `<text class="fb-tx fb-b" x="${damL + damW / 2}" y="${top - 6}" text-anchor="middle">${esc(t.lbl_dique)}</text>`;
    if (abierta) {
      const ay = bottom - gap / 2;
      g += `<path class="fb-flujo" d="M${damR + 16} ${ay} L${damL - 10} ${ay}"/><path class="fb-punta" d="M${damL - 6} ${ay - 5} L${damL - 12} ${ay} L${damL - 6} ${ay + 5}"/>`;
    } else {
      const px = damR + 26, py = bottom - 26, tubo = `M${px} ${py - 10} V${top + 24} H${damL - 22} V${top + 44}`;
      g += `<path class="fb-tubo-borde" d="${tubo}"/><path class="fb-flujo fb-tubo" d="${tubo}"/><circle class="fb-bomba" cx="${px}" cy="${py}" r="10"/>`;
      g += `<text class="fb-tx" x="${px + 15}" y="${py + 4}">${esc(t.lbl_bombas)}</text>`;
    }
    g += `<line class="fb-suelo" x1="0" x2="${W}" y1="${bottom}" y2="${bottom}"/>`;
    // rótulos de cada río
    g += `<text class="fb-tx fb-b" x="${damL - 8}" y="${bottom - gap - 8}" text-anchor="end">${esc(t.lbl_parana)}</text>`;
    g += `<text class="fb-tx fb-b" x="${damR + 8}" y="${bottom - gap - 8}">${esc(t.lbl_rn)}</text>`;
    g += `<text class="fb-tx fb-b" x="4" y="${y(s.h) + 14}">${esc(val(s.h))}</text>`;
    g += `<text class="fb-tx fb-mu" x="${W - 4}" y="${bottom + 14}" text-anchor="end">${esc(t.lbl_rn)}: ${esc(t.lbl_rn_esquema)}</text>`;
    return `<svg class="fb-svg" viewBox="0 0 ${W} ${H}" role="img" aria-describedby="fb-desc" focusable="false">${g}</svg>`;
  }

  function corte(t, val, paso) {
    const H = 190, damL = 148, damW = 18, damR = damL + damW, claySup = 112, clayInf = 132;
    const paNivel = 50, rnNivel = 80;
    const cl = ["fb-c"].concat([1, 2, 3].filter((k) => paso >= k).map((k) => "p" + k)).join(" ");
    let g = "";
    g += `<rect class="fb-arena" x="0" y="${clayInf}" width="${W}" height="${H - clayInf}"/><rect class="fb-arcilla" x="0" y="${claySup}" width="${W}" height="${clayInf - claySup}"/>`;
    g += `<rect class="fb-agua-pa" x="0" y="${paNivel}" width="${damL}" height="${claySup - paNivel}"/>`;
    g += `<rect class="fb-agua-rn" x="${damR}" y="${rnNivel}" width="${W - damR}" height="${claySup - rnNivel}"/>`;
    g += `<rect class="fb-agua-pa fb-union" x="${damR}" y="${paNivel}" width="${W - damR}" height="${claySup - paNivel}"/>`;
    g += `<line class="fb-sup-pa" x1="0" x2="${damL}" y1="${paNivel}" y2="${paNivel}"/>`;
    g += `<line class="fb-sup-rn fb-rn-linea" x1="${damR}" x2="${W}" y1="${rnNivel}" y2="${rnNivel}"/><line class="fb-sup-pa fb-union" x1="${damR}" x2="${W}" y1="${paNivel}" y2="${paNivel}"/>`;
    g += `<path class="fb-hueco" d="M70 ${clayInf} C80 ${clayInf + 26} 150 ${clayInf + 34} ${damR + 52} ${clayInf + 8} L${damR + 52} ${clayInf} Z"/>`;
    g += `<path class="fb-flujo fb-filtra" d="M56 ${clayInf + 6} C80 ${clayInf + 30} 150 ${clayInf + 32} ${damR + 46} ${clayInf + 20}"/><path class="fb-punta fb-filtra" d="M${damR + 40} ${clayInf + 14} L${damR + 48} ${clayInf + 20} L${damR + 40} ${clayInf + 26}"/>`;
    g += `<text class="fb-tx fb-b fb-filtra" x="${damR + 54}" y="${clayInf + 38}">${esc(t.corte_lbl_empuje)}</text>`;
    g += `<g class="fb-dique"><rect class="fb-muro" x="${damL}" y="38" width="${damW}" height="${claySup - 38}" rx="2"/></g>`;
    g += `<text class="fb-tx fb-b fb-dique-t" x="${damL + damW / 2}" y="30" text-anchor="middle">${esc(t.lbl_dique)}</text>`;
    g += `<text class="fb-tx fb-b" x="${damL - 8}" y="${paNivel + 16}" text-anchor="end">${esc(t.corte_lbl_parana)} ${esc(val(7.5))}</text>`;
    g += `<text class="fb-tx fb-b fb-rn-t" x="${damR + 8}" y="${rnNivel + 16}">${esc(t.corte_lbl_rn)} ${esc(val(6))}</text>`;
    g += `<text class="fb-tx fb-mu" x="6" y="${claySup + 14}">${esc(t.corte_lbl_arcilla)}</text><text class="fb-tx fb-mu" x="6" y="${clayInf + 16}">${esc(t.corte_lbl_arena)}</text>`;
    return `<svg class="fb-svg ${cl}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t.corte_desc)}" focusable="false">${g}</svg>`;
  }

  // ---------- HTML ----------
  function construirHtml(o) {
    const lang = o.lang || "es", t = o.textos || {};
    const val = (v) => L.formatoValor(v, "m", lang);
    const loc = L.localeDe(lang);
    const dia = (iso) => new Date(String(iso).length === 10 ? iso + "T12:00:00Z" : iso).toLocaleDateString(loc, { weekday: "short", day: "numeric", month: "short", timeZone: String(iso).length === 10 ? "UTC" : ZONA_HORARIA });
    const fechaLarga = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString(loc, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
    const fechaHora = (iso) => { try { return new Date(iso).toLocaleString(loc, { timeZone: ZONA_HORARIA, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); } catch (e) { return ""; } };
    const palabra = (est) => t[est === "abiertas" ? "palabra_abiertas" : est === "cerradas" ? "palabra_cerradas" : "palabra_puede"];
    const s = estadoFicha(o), horas = M.HORAS_VENCIDO;
    let h = `<section class="fb" aria-labelledby="fb-h"><h4 class="mh" id="fb-h">${esc(t.titulo)}</h4>`;

    h += `<h5 class="fb-sub">${esc(t.esquema_h)}</h5><p class="sdnote">${esc(t.esquema_aviso)}</p>`;
    if (s.estado == null) {
      h += `<p class="fb-sin-lectura">${esc(t.sin_lectura)}</p>`;
    } else {
      const vars = { altura: val(s.h), alerta: val(s.alerta), evac: val(s.evacuacion), palabra: palabra(s.estado) };
      const clave = s.estado === "abiertas" ? "estado_abiertas" : s.estado === "cerradas" ? "estado_cerradas" : "estado_puede";
      let texto = fmt(t[clave], vars);
      if (num(s.evacuacion) && s.h >= s.evacuacion) texto += " " + fmt(t.estado_evac, vars);
      const edad = o.estacion && o.estacion.t_utc ? L.edadTexto(L.edadMin(o.estacion.t_utc, num(o.ahora) ? o.ahora : Date.now()), lang) : "";
      h += `<figure class="fb-fig">${esquema(s, t, val)}<figcaption id="fb-desc" class="fb-desc">${esc(fmt(t.fig_desc, vars))}</figcaption></figure>`;
      h += `<p><span class="tag fb-regla" data-estado="${esc(s.estado)}">${esc(fmt(t.regla_chip, vars))}</span></p><p class="fb-estado">${esc(texto)}</p>`;
      if (edad) h += `<p class="sdnote">${esc(fmt(t.lectura_edad, { edad }))}</p>`;
    }

    if (s.situacion) {
      const d = s.situacion.doc;
      h += `<h5 class="fb-sub">${esc(t.situacion_h)}</h5><p class="sdnote">${esc(fmt(t.situacion_fecha, { fecha: d.actualizado ? fechaHora(d.actualizado) : d.fecha ? fechaLarga(d.fecha) : "—" }))}</p>`;
      if (s.situacion.vencida) h += `<p class="mnote"><span class="vencido">${esc(fmt(t.situacion_vencido, { horas }))}</span></p>`;
      const r = porIdioma(d.resumen, lang), pr = porIdioma(d.pronostico_texto, lang), fu = porIdioma(d.fuentes, lang);
      if (r) h += `<p>${esc(r)}</p>`;
      if (pr) h += `<p>${esc(pr)}</p>`;
      if (fu) h += `<p class="sdnote">${esc(fmt(t.situacion_fuentes, { fuentes: fu }))}${/^https:\/\//.test(d.fuente_url || "") ? ` <a href="${esc(d.fuente_url)}" target="_blank" rel="noopener">${esc(t.situacion_enlace)}</a>` : ""}</p>`;
    }

    h += `<h5 class="fb-sub">${esc(t.prono_h)}</h5>`;
    if (!s.pronostico) h += `<p class="sdnote">${esc(t.prono_ninguno)}</p>`;
    else {
      const p = s.pronostico, fecha = p.doc.fecha ? fechaLarga(p.doc.fecha) : fechaHora(p.doc.generado_utc);
      h += `<p>${esc(p.rango ? fmt(t.prono_rango, { fecha, min: val(p.min), max: val(p.max), dia: dia(p.punto[0]) }) : fmt(t.prono_punto, { fecha, valor: val(p.min), dia: dia(p.punto[0]) }))}</p>`;
      if (p.vencido) h += `<p class="mnote"><span class="vencido">${esc(fmt(t.prono_vencido, { horas }))}</span></p>`;
      else if (p.estadoMin) {
        h += `<p>${esc(p.estadoMin === p.estadoMax ? fmt(t.prono_misma, { palabra: palabra(p.estadoMin) }) : fmt(t.prono_cruza, { a: palabra(p.estadoMin), b: palabra(p.estadoMax) }))}</p><p class="sdnote">${esc(t.prono_aviso)}</p>`;
      }
    }

    h += `<h5 class="fb-sub">${esc(t.lluvia_h)}</h5>`;
    if (!s.lluvia.dias.length) h += `<p class="sdnote">${esc(t.lluvia_sin)}</p>`;
    else {
      h += `<p class="sdnote">${esc(fmt(t.lluvia_fuente, { fecha: fechaHora(s.lluvia.generado) }))}</p>`;
      if (s.lluvia.vencida) h += `<p class="mnote"><span class="vencido">${esc(fmt(t.lluvia_vencida, { horas: M.HORAS_VENCIDA_LLUVIA }))}</span></p>`;
      h += `<ul class="hl fb-lluvia">${s.lluvia.dias.map((d) => `<li>${esc(fmt(t.lluvia_dia, { dia: dia(d.fecha), mm: L.formatoValor(d.mm, "mm", lang), prob: num(d.prob) ? L.formatoNumero(d.prob, lang) : "—" }))}</li>`).join("")}</ul>`;
      h += `<p class="sdnote">${esc(t.lluvia_nota)}</p>`;
    }

    const niv = o.umbrales && Array.isArray(o.umbrales.niveles) ? o.umbrales.niveles.filter((n) => n && num(n.altura_m)).sort((a, b) => a.altura_m - b.altura_m) : [];
    if (niv.length) {
      h += `<h5 class="fb-sub">${esc(t.niveles_h)}</h5>`;
      if (s.h != null) h += `<p class="sdnote">${esc(fmt(t.niveles_aqui, { altura: val(s.h) }))}</p>`;
      h += `<ul class="hl">${niv.map((n) => `<li><b>${esc(val(n.altura_m))}</b>: ${esc(porIdioma(n.nombre, lang))}</li>`).join("")}</ul>`;
      if (o.umbrales.fuente) h += `<p class="sdnote">${esc(fmt(t.niveles_fuente, { fuente: o.umbrales.fuente }))}</p>`;
    }

    h += `<h5 class="fb-sub">${esc(t.corte_h)}</h5><p class="sdnote">${esc(t.corte_aviso)}</p>`;
    h += `<div class="fb-corte"><figure class="fb-fig">${corte(t, val, pasoCorte)}</figure>`;
    h += `<p class="fb-cap" aria-live="polite">${esc(t["corte_paso_" + pasoCorte])}</p>`;
    h += `<p class="sdnote fb-n">${esc(fmt(t.corte_paso_n, { n: pasoCorte, total: PASOS_CORTE }))}</p>`;
    h += `<div class="fb-ctl"><button type="button" class="fb-btn fb-sig"${pasoCorte >= PASOS_CORTE ? " disabled" : ""}>${esc(t.corte_siguiente)}</button>`;
    h += `<button type="button" class="fb-btn fb-rei"${pasoCorte === 0 ? " disabled" : ""}>${esc(t.corte_reiniciar)}</button></div></div>`;
    return h + "</section>";
  }

  function montar(el, o) {
    if (!el) return;
    el.innerHTML = construirHtml(o);
    const t = o.textos || {};
    const raiz = el.querySelector(".fb-corte");
    if (!raiz) return;
    const poner = () => {
      const svg = raiz.querySelector("svg");
      [1, 2, 3].forEach((k) => svg.classList.toggle("p" + k, pasoCorte >= k));
      raiz.querySelector(".fb-cap").textContent = t["corte_paso_" + pasoCorte] || "";
      raiz.querySelector(".fb-n").textContent = fmt(t.corte_paso_n, { n: pasoCorte, total: PASOS_CORTE });
      raiz.querySelector(".fb-sig").disabled = pasoCorte >= PASOS_CORTE;
      raiz.querySelector(".fb-rei").disabled = pasoCorte === 0;
    };
    raiz.querySelector(".fb-sig").addEventListener("click", () => { pasoCorte = pasoSiguiente(pasoCorte); poner(); });
    raiz.querySelector(".fb-rei").addEventListener("click", () => { pasoCorte = 0; poner(); });
  }

  return { PASOS_CORTE, reglaCompuertas, estadoFicha, construirHtml, pasoSiguiente, montar };
});
