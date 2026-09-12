"""
robustez.py — Capa de resiliencia para el procesamiento masivo de carpetas.

Tres componentes independientes que se importan desde script_v2.py:
  • reintentar():      decorador con exponential backoff para llamadas a la API
  • EstadoLote:        checkpointing persistente para reanudar ejecuciones interrumpidas
  • configurar_logs(): logging estructurado a archivos y consola

No modifica la lógica de clasificación ni las reglas de negocio.
"""

import time
import json
import logging
import functools
from pathlib import Path
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════


def configurar_logs(directorio_logs):
    """Configura el logger 'automata' con tres destinos:

      - ejecucion.log : registro completo (DEBUG+)
      - errores.log   : solo advertencias y errores (WARNING+)
      - consola        : información resumida (INFO+)

    Retorna el logger configurado. Idempotente (no duplica handlers).
    """
    directorio_logs = Path(directorio_logs)
    directorio_logs.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("automata")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s │ %(levelname)-8s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Registro completo → ejecucion.log
    h_todo = logging.FileHandler(directorio_logs / "ejecucion.log", encoding="utf-8")
    h_todo.setLevel(logging.DEBUG)
    h_todo.setFormatter(fmt)

    # Solo errores → errores.log
    h_err = logging.FileHandler(directorio_logs / "errores.log", encoding="utf-8")
    h_err.setLevel(logging.WARNING)
    h_err.setFormatter(fmt)

    # Consola
    h_con = logging.StreamHandler()
    h_con.setLevel(logging.INFO)
    h_con.setFormatter(fmt)

    logger.addHandler(h_todo)
    logger.addHandler(h_err)
    logger.addHandler(h_con)

    return logger


# ═══════════════════════════════════════════════════════════════
# RETRY CON EXPONENTIAL BACKOFF
# ═══════════════════════════════════════════════════════════════


_PATRONES_REINTENTABLES = (
    "429", "503", "500",
    "resource_exhausted", "resourceexhausted",
    "unavailable", "service_unavailable",
    "deadline", "timeout", "timed out",
    "connection", "reset", "broken pipe",
    "remotedisconnected", "connectionreset",
    "internal", "server_error",
)

_EXCEPCIONES_PERMANENTES = (
    ValueError, KeyError, TypeError, FileNotFoundError,
    json.JSONDecodeError,
)


def _es_reintentable(excepcion):
    """Decide si una excepción merece reintento (errores de red/cuota/servidor).

    Errores de lógica (ValueError, KeyError, etc.) se propagan de inmediato.
    """
    if isinstance(excepcion, _EXCEPCIONES_PERMANENTES):
        return False
    if isinstance(excepcion, (ConnectionError, TimeoutError, OSError)):
        return True
    texto = f"{type(excepcion).__name__} {excepcion}".lower()
    return any(patron in texto for patron in _PATRONES_REINTENTABLES)


def reintentar(max_intentos=5, base_espera=2.0):
    """Decorador: reintenta la función ante fallos transitorios con backoff exponencial.

    Esperas: base × 2^(intento-1) → con base=2: 2s, 4s, 8s, 16s, 32s.
    Solo reintenta errores de red, cuota (429) y servidor (5xx).
    """
    def decorador(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger("automata")
            for intento in range(1, max_intentos + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if not _es_reintentable(e) or intento == max_intentos:
                        if intento > 1:
                            logger.error(
                                f"✗ {fn.__name__} falló definitivamente "
                                f"(intento {intento}/{max_intentos}): {e}"
                            )
                        raise
                    espera = base_espera * (2 ** (intento - 1))
                    logger.warning(
                        f"⟳ {fn.__name__} intento {intento}/{max_intentos} falló "
                        f"({type(e).__name__}). Reintentando en {espera:.0f}s…"
                    )
                    time.sleep(espera)
        return wrapper
    return decorador


# ═══════════════════════════════════════════════════════════════
# ESTADO DEL LOTE (CHECKPOINTING)
# ═══════════════════════════════════════════════════════════════


class EstadoLote:
    """Registro persistente del progreso de un lote de carpetas.

    Archivo: <directorio_salida>/estado_lote.json

    Estados posibles: PENDIENTE → EN_PROCESO → COMPLETADO | FALLIDO

    Permite reanudar ejecuciones interrumpidas saltando carpetas ya completadas.
    """

    ARCHIVO = "estado_lote.json"

    def __init__(self, directorio_salida):
        self.ruta = Path(directorio_salida) / self.ARCHIVO
        self.datos = self._cargar()
        self.logger = logging.getLogger("automata")

    def _cargar(self):
        if self.ruta.exists():
            with open(self.ruta, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _guardar(self):
        self.ruta.write_text(
            json.dumps(self.datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def ya_completado(self, clave):
        """True si la carpeta fue procesada exitosamente en una ejecución anterior."""
        return self.datos.get(clave, {}).get("estado") == "COMPLETADO"

    def marcar_en_proceso(self, clave):
        self.datos[clave] = {
            "estado": "EN_PROCESO",
            "inicio": datetime.now().isoformat(timespec="seconds"),
        }
        self._guardar()

    def marcar_completado(self, clave, archivos=0):
        self.datos[clave] = {
            "estado": "COMPLETADO",
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "archivos": archivos,
        }
        self._guardar()
        self.logger.info(f"  ✓ Completado ({archivos} archivos)")

    def marcar_fallido(self, clave, error):
        self.datos[clave] = {
            "estado": "FALLIDO",
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "error": str(error)[:500],
        }
        self._guardar()

    def resumen(self):
        """Retorna (completados, fallidos, total)."""
        completados = sum(1 for v in self.datos.values() if v.get("estado") == "COMPLETADO")
        fallidos = sum(1 for v in self.datos.values() if v.get("estado") == "FALLIDO")
        return completados, fallidos, len(self.datos)

    def listar_fallidos(self):
        """Retorna las claves de las carpetas con estado FALLIDO."""
        return [k for k, v in self.datos.items() if v.get("estado") == "FALLIDO"]

    def limpiar_fallidos(self):
        """Elimina las entradas FALLIDO para permitir su reprocesamiento."""
        fallidos = self.listar_fallidos()
        for clave in fallidos:
            del self.datos[clave]
        self._guardar()
        self.logger.info(f"♻ {len(fallidos)} carpetas fallidas marcadas para reprocesamiento")
        return len(fallidos)
