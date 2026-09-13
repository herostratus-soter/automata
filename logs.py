"""
logs.py — Capa de resiliencia y logging para el procesamiento masivo de carpetas.

Componentes principales:
  - reintentar(): decorador con exponential backoff para llamadas a la API
  - EstadoLote: checklist persistente para monitorear el progreso en estado_lote.json
  - configurar_logs(): logging estructurado a archivos y consola
"""

import time
import json
import logging
import functools
from pathlib import Path
from datetime import datetime


# ===============================================================
# LOGGING
# ===============================================================


class AutoFlushFileHandler(logging.FileHandler):
    """FileHandler que fuerza el flush inmediato a disco tras escribir cada mensaje.

    Garantiza que no se pierdan logs si Colab o el proceso se interrumpe abruptamente.
    """
    def emit(self, record):
        super().emit(record)
        self.flush()


def configurar_logs(directorio_logs):
    """Configura el logger 'automata' con tres destinos:

      - ejecucion.log : registro completo (DEBUG+)
      - errores.log   : solo advertencias y errores (WARNING+)
      - consola       : información resumida (INFO+)

    Retorna el logger configurado. Idempotente (no duplica handlers).
    """
    directorio_logs = Path(directorio_logs)
    directorio_logs.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("automata")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Registro completo -> ejecucion.log (flush inmediato)
    h_todo = AutoFlushFileHandler(directorio_logs / "ejecucion.log", encoding="utf-8")
    h_todo.setLevel(logging.DEBUG)
    h_todo.setFormatter(fmt)

    # Solo errores -> errores.log (flush inmediato)
    h_err = AutoFlushFileHandler(directorio_logs / "errores.log", encoding="utf-8")
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


# ===============================================================
# RETRY CON EXPONENTIAL BACKOFF
# ===============================================================


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

    Esperas: base * 2^(intento-1) -> con base=2: 2s, 4s, 8s, 16s, 32s.
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
                                f"[ERROR] {fn.__name__} fallo definitivamente "
                                f"(intento {intento}/{max_intentos}): {e}"
                            )
                        raise
                    espera = base_espera * (2 ** (intento - 1))
                    logger.warning(
                        f"[RETRY] {fn.__name__} intento {intento}/{max_intentos} fallo "
                        f"({type(e).__name__}). Reintentando en {espera:.0f}s..."
                    )
                    time.sleep(espera)
        return wrapper
    return decorador


# ===============================================================
# CHECKLIST Y ESTADO DEL LOTE (RETROCOMPATIBLE)
# ===============================================================


class EstadoLote:
    """Checklist y registro persistente del lote de carpetas.

    Archivo: <directorio_salida>/estado_lote.json

    Estructura retrocompatible:
    {
      "52344909 ANGARITA FORERO MARISOL": {
        "estado": "COMPLETADO",
        "fecha": "2026-09-12T23:49:07",
        "archivos": 26
      },
      "1096230492 ALVARINO GARCIA ELIDA": {
        "estado": "FALLIDO",
        "fecha": "2026-09-13T00:46:40",
        "error": "Sequence index out of range"
      }
    }
    """

    ARCHIVO = "estado_lote.json"

    def __init__(self, directorio_salida):
        self.ruta = Path(directorio_salida) / self.ARCHIVO
        self.datos = self._cargar()
        self.logger = logging.getLogger("automata")

    def _cargar(self):
        if self.ruta.exists():
            try:
                with open(self.ruta, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _guardar(self):
        self.ruta.write_text(
            json.dumps(self.datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def inicializar_checklist(self, lista_carpetas):
        """Registra al inicio todas las carpetas del lote como PENDIENTE si no existen aun."""
        modificado = False
        for carpeta in lista_carpetas:
            clave = carpeta.name if isinstance(carpeta, Path) else Path(carpeta).name
            if clave not in self.datos:
                self.datos[clave] = {
                    "estado": "PENDIENTE",
                    "archivos": 0
                }
                modificado = True
        if modificado:
            self._guardar()

    @staticmethod
    def contar_jsons_reales(carpeta_salida):
        """Cuenta la cantidad real de archivos .json generados en disco (excluyendo 0_ecumenico.json)."""
        carpeta = Path(carpeta_salida)
        if not carpeta.exists() or not carpeta.is_dir():
            return 0
        conteo = 0
        for archivo in carpeta.glob("*.json"):
            if not (archivo.name.startswith("_") or archivo.name.startswith("0_")):
                conteo += 1
        return conteo

    def ya_completado(self, clave):
        """True si la carpeta ya fue procesada exitosamente (COMPLETADO o APROBADO)."""
        estado = self.datos.get(clave, {}).get("estado")
        return estado in ("COMPLETADO", "APROBADO")

    def marcar_en_proceso(self, clave):
        if clave not in self.datos:
            self.datos[clave] = {}
        self.datos[clave]["estado"] = "EN_PROCESO"
        self.datos[clave]["inicio"] = datetime.now().isoformat(timespec="seconds")
        self._guardar()

    def marcar_completado(self, clave, carpeta_salida):
        """Revisa la carpeta de salida real. Si genero al menos 1 JSON, marca COMPLETADO. De lo contrario, FALLIDO."""
        jsons_reales = self.contar_jsons_reales(carpeta_salida)
        if jsons_reales > 0:
            self.datos[clave] = {
                "estado": "COMPLETADO",
                "fecha": datetime.now().isoformat(timespec="seconds"),
                "archivos": jsons_reales
            }
            self._guardar()
            self.logger.info(f"  [OK] COMPLETADO ({jsons_reales} archivos JSON generados)")
        else:
            self.marcar_defectuoso(clave, "0 archivos JSON generados en la carpeta de salida", carpeta_salida)

    def marcar_defectuoso(self, clave, motivo, carpeta_salida=None):
        jsons_reales = self.contar_jsons_reales(carpeta_salida) if carpeta_salida else 0
        self.datos[clave] = {
            "estado": "FALLIDO",
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "error": str(motivo)[:500],
            "archivos": jsons_reales
        }
        self._guardar()
        self.logger.warning(f"  [DEFECTUOSO] {clave} -> {motivo}")

    def marcar_fallido(self, clave, error, carpeta_salida=None):
        self.marcar_defectuoso(clave, error, carpeta_salida)

    def listar_fallidos(self):
        """Devuelve las claves de las carpetas que quedaron con estado FALLIDO o DEFECTUOSO."""
        return [k for k, v in self.datos.items() if v.get("estado") in ("FALLIDO", "DEFECTUOSO")]

    def limpiar_fallidos(self):
        """Limpia las entradas defectuosas para que el modo reintentar las vuelva a procesar."""
        fallidos = self.listar_fallidos()
        for clave in fallidos:
            self.datos[clave] = {
                "estado": "PENDIENTE",
                "archivos": 0
            }
        self._guardar()
        self.logger.info(f"[REINTENTAR] {len(fallidos)} carpetas defectuosas marcadas para reprocesamiento")
        return len(fallidos)

    def resumen(self):
        """Retorna (completados, fallidos, pendientes, total)."""
        completados = sum(1 for v in self.datos.values() if v.get("estado") in ("COMPLETADO", "APROBADO"))
        fallidos = sum(1 for v in self.datos.values() if v.get("estado") in ("FALLIDO", "DEFECTUOSO"))
        pendientes = sum(1 for v in self.datos.values() if v.get("estado") in ("PENDIENTE", "EN_PROCESO"))
        return completados, fallidos, pendientes, len(self.datos)
