// Función de Vercel: recibe {pais, rio} y lanza el workflow "actualizar" en GitHub.
// Variables de entorno (Vercel → Settings → Environment Variables):
//   GITHUB_TOKEN  token fine-grained solo para nivelrio, permiso "Actions: Read and write"
const REPO = "sebaandrada-cell/nivelrio";
const WORKFLOW = "actualizar.yml";
const REF = "multipais";
const ORIGEN = "https://sebaandrada-cell.github.io";
const PAISES = ["todos", "ar", "es", "us", "de", "fr", "gb", "pl"];
const ESPERA_MS = 60 * 1000;
const ultimo = new Map(); // por instancia: freno básico; el workflow además se encola con concurrency

module.exports = async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", ORIGEN);
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Vary", "Origin");
  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ error: "metodo" });
  if (req.headers.origin !== ORIGEN) return res.status(403).json({ error: "origen" });

  const cuerpo = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
  const pais = String(cuerpo.pais || "");
  const rio = String(cuerpo.rio || "").trim();
  if (!PAISES.includes(pais) || !rio || rio.length > 80) return res.status(400).json({ error: "datos" });

  const clave = pais + "|" + rio.toLowerCase();
  const ahora = Date.now();
  if (ahora - (ultimo.get(clave) || 0) < ESPERA_MS) return res.status(429).json({ error: "espera" });
  ultimo.set(clave, ahora);

  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      "User-Agent": "nivelrio-actualizar",
    },
    body: JSON.stringify({ ref: REF, inputs: { pais, rio } }),
  });
  if (r.status !== 204) {
    ultimo.delete(clave);
    return res.status(502).json({ error: "github", estado: r.status });
  }
  return res.status(202).json({ ok: true });
};
