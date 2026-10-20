// Lógica pura de los módulos de ficha: crecidas históricas, serie con pronóstico y simulador.
// Sin DOM y sin conversión de unidades: los valores se comparan tal como los publica cada fuente.
// Idea tomada del proyecto de Pablo Dodda (licencia MIT); código propio.
(function (root, factory) {
  const M = factory();
  if (typeof module === "object" && module.exports) module.exports = M;
  else root.Modulos = M;
})(typeof self !== "undefined" ? self : this, function () {
  const HORAS_VENCIDO = 36;

  const esNumero = (x) => typeof x === "number" && Number.isFinite(x);

  // Compara el valor actual con cada referencia histórica, de mayor a menor.
  // diferencia = actual - referencia (negativa: hoy está por debajo). Sin valor actual queda en null.
  function compararConHistoricas(valorActual, historicas) {
    const hay = esNumero(valorActual);
    return (Array.isArray(historicas) ? historicas : [])
      .filter((h) => h && esNumero(h.valor))
      .map((h) => ({
        evento: h.evento, tipo: h.tipo, valor: h.valor, nota: h.nota,
        diferencia: hay ? valorActual - h.valor : null,
      }))
      .sort((a, b) => b.valor - a.valor);
  }

  const SIN_DISTANCIAS = () => ({ N1: null, N2: null, N3: null });

  // Nivel que correspondería a un valor hipotético según los umbrales de la estación.
  // distancias.Nk = umbral - valor: positiva, lo que falta para llegar; negativa, lo que ya se superó.
  // Es una lectura puntual de los umbrales: no aplica la histéresis ni las lecturas sostenidas del motor de alertas.
  function simular(valor, umbrales) {
    if (!esNumero(valor)) return { nivel: null, textoClave: "mod_sim_sin_valor", distancias: SIN_DISTANCIAS() };
    const u = umbrales;
    const ok = u && u.tipo !== "en_estudio" && esNumero(u.bajo) && esNumero(u.medio) && esNumero(u.alto);
    if (!ok) return { nivel: null, textoClave: "mod_sim_sin_umbrales", distancias: SIN_DISTANCIAS() };
    const nivel = valor >= u.alto ? 3 : valor >= u.medio ? 2 : valor >= u.bajo ? 1 : 0;
    return {
      nivel, textoClave: "mod_sim_n" + nivel,
      distancias: { N1: u.bajo - valor, N2: u.medio - valor, N3: u.alto - valor },
    };
  }

  // Lo que escribe la persona: acepta «6,2» y «6.2». Cualquier otra cosa es null.
  function leerEntrada(texto) {
    if (typeof texto !== "string") return null;
    const s = texto.trim().replace(",", ".");
    if (!/^-?\d+(\.\d+)?$/.test(s)) return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }

  // Historial observado + pronóstico en una sola serie [{t (ms), v, tipo}].
  // Un punto pronosticado puede ser un valor [iso, v] o un rango [iso, mín, máx] (v queda en null).
  // Los puntos del pronóstico que no son posteriores a la última lectura se descartan.
  function serieConPronostico(historial, pronostico) {
    const obs = (Array.isArray(historial) ? historial : [])
      .map((p) => ({ t: Date.parse(p && p[0]), v: p && p[1], tipo: "obs" }))
      .filter((p) => Number.isFinite(p.t) && esNumero(p.v))
      .sort((a, b) => a.t - b.t);
    if (obs.length) obs[obs.length - 1].ultimo = true;
    const desde = obs.length ? obs[obs.length - 1].t : -Infinity;
    const pr = [];
    for (const p of pronostico && Array.isArray(pronostico.puntos) ? pronostico.puntos : []) {
      const t = Date.parse(p && p[0]);
      if (!Number.isFinite(t) || t <= desde) continue;
      if (p.length >= 3 && esNumero(p[1]) && esNumero(p[2])) pr.push({ t, v: null, min: Math.min(p[1], p[2]), max: Math.max(p[1], p[2]), tipo: "prono" });
      else if (esNumero(p[1])) pr.push({ t, v: p[1], tipo: "prono" });
    }
    pr.sort((a, b) => a.t - b.t);
    return obs.concat(pr);
  }

  // Un pronóstico de más de 36 h se marca vencido. La fecha es `generado_utc` (NWS) o `fecha` (manual, día sin hora,
  // contado desde las 00:00 UTC). Sin fecha legible no se puede afirmar que sea vigente.
  function pronosticoVencido(doc, ahoraMs) {
    if (!doc) return true;
    const t = Date.parse(doc.generado_utc || (doc.fecha ? doc.fecha + "T00:00:00Z" : ""));
    return !Number.isFinite(t) || ahoraMs - t > HORAS_VENCIDO * 3600000;
  }

  // Reglas de edad de los demás instantáneos manuales o de modelo (cada uno lleva su fecha y se marca vencido):
  //  - situación (reporte escrito a mano): 36 h, igual que un pronóstico; fecha = `actualizado` o, sin hora, 00:00 UTC de `fecha`.
  //  - lluvia (previsión Open-Meteo del robot, se renueva cada hora): 6 h desde `generado_utc`.
  const HORAS_VENCIDA_LLUVIA = 6;
  const venceA = (iso, ahoraMs, horas) => {
    const t = Date.parse(iso || "");
    return !Number.isFinite(t) || ahoraMs - t > horas * 3600000;
  };
  function situacionVencida(doc, ahoraMs) {
    if (!doc) return true;
    return venceA(doc.actualizado || (doc.fecha ? doc.fecha + "T00:00:00Z" : ""), ahoraMs, HORAS_VENCIDO);
  }
  function lluviaVencida(doc, ahoraMs) {
    return !doc || venceA(doc.generado_utc, ahoraMs, HORAS_VENCIDA_LLUVIA);
  }

  return { HORAS_VENCIDO, HORAS_VENCIDA_LLUVIA, situacionVencida, lluviaVencida, compararConHistoricas, simular, leerEntrada, serieConPronostico, pronosticoVencido };
});
