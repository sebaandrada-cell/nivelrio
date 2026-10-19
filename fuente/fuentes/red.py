"""GET con reintentos compartido por todas las fuentes. Solo biblioteca estándar, TLS siempre verificado."""
import http.client
import time
import urllib.error
import urllib.request

from modelo import FuenteError

USER_AGENT = "rius-catalunya/0.1 (+https://github.com/sebaandrada-cell/nivelrio)"


def get_texto(url: str, *, fuente: str, abrir=urllib.request.urlopen, intentos: int = 3,
              dormir=time.sleep, validar=None, timeout: int = 30, accept: str = "*/*") -> str:
    """Devuelve el cuerpo como texto UTF-8. `validar(texto)` puede lanzar ValueError para forzar otro intento."""
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
            with abrir(req, timeout=timeout) as r:
                texto = r.read().decode("utf-8")
            if validar:
                validar(texto)
            return texto
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError) as e:
            ultimo = e
            if i < intentos - 1:
                dormir(min(2 ** i, 8))
    raise FuenteError(f"{fuente}: {url} falló tras {intentos} intentos: {ultimo}")
