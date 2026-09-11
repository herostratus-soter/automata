"""Configuración separada del script principal — este archivo está en .gitignore."""

from pathlib import Path


# ─── Credenciales ───

APIKEY = "apikey"


# ─── Modelos de IA ───

MODELO_FLASH = "gemini-2.5-flash"       # modelo completo: para segmentar compilados (tarea pesada)
MODELO_LITE  = "gemini-3.1-flash-lite"  # modelo económico: para clasificar documentos sueltos


# ─── Período de contratación ───

ANIO = "2026"
MES  = "09"


# ─── Rutas ───

RUTA_ODS = Path(__file__).parent / "reglas_v2.ods"

# Directorio raíz con TODAS las carpetas de contratados (para procesamiento completo)
RUTA_PADRE = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/SERGIO_CRUZ/")

# Una carpeta específica para hacer pruebas localizadas
RUTA_PRUEBA = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/SERGIO_CRUZ/TIGO/39576253 GUZMAN PAEZ CARMENZA/")

# Donde se guardan los JSONs de cada contratado (una subcarpeta por cédula)
RUTA_SALIDA_JSON = Path(__file__).parent / "tmp"

# Donde se genera el Excel final de contratación
RUTA_SALIDA_EXCEL = Path(__file__).parent


# ─── Formatos de archivo aceptados ───

FORMATOS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".docx"}


# ─── Paralelismo ───

HILOS = 7


# ─── Resiliencia ───

RUTA_LOGS = Path(__file__).parent / "logs"
MAX_REINTENTOS = 5
ESPERA_BASE = 2.0  # segundos (backoff: 2s, 4s, 8s, 16s, 32s)
