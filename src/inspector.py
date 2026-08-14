import os
import sys
import json
from pathlib import Path
import docx
import unicodedata
from google import genai
from google.genai import types

# Configuración desde carpeta padre
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from prompts_tmp import PROMPT_POR_NOMBRE, PROMPT_POR_CONTENIDO
from tokens import tracker  # Importamos el rastreador centralizado

MODEL_ID = config.MODELO_DEFAULT

FORMATOS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".docx"}

CLAVES_VALIDAS = [
    "01_documento_id", "02_contrato_laboral", "03_curso_etica", "04_curso_transparencia",
    "05_curso_cultura", "06_pruebas_psicotecnicas", "07_verificacion_referencias",
    "08_arl", "09_ccf", "10_examen_medico_ingreso", "11_antecedente_policia",
    "12_antecedente_procuraduria", "13_antecedente_contraloria", "14_cuenta_bancaria",
    "15_pension", "16_cesantias", "17_eps", "18_referencias", "19_estudios",
    "20_referencia_personal", "21_referencia_laboral", "22_hoja_de_vida",
    "23_formatos_para_la_contratacion", "REVISAR_CONTENIDO"
]


# --- UTILIDADES DE ARCHIVO Y TEXTO ---

def limpiar_texto(texto: str) -> str:
    normalizado = unicodedata.normalize('NFD', texto)
    limpio = ''.join(c for c in normalizado if unicodedata.category(c) != 'Mn')
    limpio = ''.join(c for c in limpio if c.isalnum() or c in (' ', '_', '-')).strip()
    return limpio.replace(' ', '_')


def sanear_archivos(directorio: Path, tag="temp") -> list[Path]:
    print("--- FASE 1: Saneando nombres de archivo ---")
    archivos = []
    i = 1

    for item in directorio.iterdir():
        if item.is_file() and item.suffix.lower() in FORMATOS:
            if item.name.startswith(f"{tag}_"):
                archivos.append(item)
            else:
                nombre_limpio = limpiar_texto(item.stem)
                nuevo_nombre = f"{tag}_{i:02d}_{nombre_limpio}{item.suffix}"
                nueva_ruta = item.parent / nuevo_nombre
                print(f"  [Saneando] '{item.name}' -> '{nuevo_nombre}'")
                archivos.append(item.rename(nueva_ruta))
                i += 1

    return archivos


def leer_word(path: Path) -> str:
    doc = docx.Document(path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])


# --- CONSULTAS A LA IA (CON TRACKING DE TOKENS) ---

def peticion(contents, client: genai.Client, es_json: bool = False) -> str:
    """
    Realiza la llamada a Gemini, desactiva el pensamiento innecesario,
    registra los tokens consumidos y retorna la respuesta.
    """
    config_kwargs = {
        "thinking_config": types.ThinkingConfig(thinking_budget=0)
    }

    if es_json:
        config_kwargs["response_mime_type"] = "application/json"

    config_gen = types.GenerateContentConfig(**config_kwargs)

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=contents,
        config=config_gen
    )

    # Registro automático de tokens consumidos
    tracker.sumar(response.usage_metadata)

    return response.text.strip('\'" \n\r\t')


def consultar_nombres_lote(archivos: list[Path], client: genai.Client) -> dict:
    """
    ULTRA-RÁPIDO: Clasifica TODOS los nombres de archivo en UNA SOLA llamada HTTP.
    Retorna un diccionario: { "nombre_archivo.pdf": "categoria_asignada" }
    """
    lista_nombres = [a.name for a in archivos]

    prompt = f"""
    Clasifica los siguientes nombres de archivo según el tipo de documento correspondiente.

    Lista de archivos a analizar:
    {json.dumps(lista_nombres, ensure_ascii=False)}

    Categorías válidas permitidas:
    {json.dumps(CLAVES_VALIDAS, ensure_ascii=False)}

    Regla: Si el nombre del archivo es ambiguo, no está claro o no coincide con precisión con una categoría, asigna "REVISAR_CONTENIDO".

    Responde ÚNICAMENTE un JSON estructurado donde la clave sea el NOMBRE EXACTO del archivo y el valor sea la CATEGORÍA asignada.
    Instrucciones adicionales de contexto: {PROMPT_POR_NOMBRE}
    """

    res_raw = peticion(prompt, client, es_json=True)

    try:
        resultado_json = json.loads(res_raw)
        # Normalizar asegurando que cada archivo tenga una clave válida
        clasificaciones = {}
        for archivo in archivos:
            cat = resultado_json.get(archivo.name, "REVISAR_CONTENIDO")
            clasificaciones[archivo.name] = cat if cat in CLAVES_VALIDAS else "REVISAR_CONTENIDO"
        return clasificaciones
    except Exception:
        # Fallback de seguridad en caso de error de parseo
        return {archivo.name: "REVISAR_CONTENIDO" for archivo in archivos}


def consultar_contenido(archivo: Path, client: genai.Client) -> str:
    """
    Evaluación individual por contenido (OCR / Visión / Texto Word) para archivos ambiguos.
    """
    ext = archivo.suffix.lower()

    if ext == ".docx":
        texto = leer_word(archivo)
        contents = [f"Contenido Word:\n{texto}", PROMPT_POR_CONTENIDO]
        remote = None
    else:
        remote = client.files.upload(file=archivo)
        contents = [remote, PROMPT_POR_CONTENIDO]

    res_limpia = peticion(contents, client)

    if remote:
        client.files.delete(name=remote.name)

    if res_limpia not in CLAVES_VALIDAS and res_limpia != "NO_CLASIFICADO":
        return "NO_CLASIFICADO"

    return res_limpia


# --- RENOMBRADO Y FLUJO PRINCIPAL ---

def aplicar_nombre_final(archivo: Path, clasificacion: str, index_indeterminado: int, conteo: dict) -> Path:
    if clasificacion in ("REVISAR_CONTENIDO", "NO_CLASIFICADO"):
        nuevo_stem = f"00_indeterminado_{index_indeterminado:02d}"
    else:
        conteo[clasificacion] = conteo.get(clasificacion, 0) + 1
        cantidad = conteo[clasificacion]
        nuevo_stem = clasificacion if cantidad == 1 else f"{clasificacion}_{cantidad}"

    if len(nuevo_stem) > 60:
        nuevo_stem = f"00_indeterminado_{index_indeterminado:02d}"

    nueva_ruta = archivo.parent / f"{nuevo_stem}{archivo.suffix}"
    print(f"  [Resultado Final] '{archivo.name}' -> '{nueva_ruta.name}'")
    return archivo.rename(nueva_ruta)


def inspeccionar(directorio: Path):
    """
    Función de entrada para el módulo inspector.
    Crea internamente su cliente de Gemini usando config.APIKEY.
    """
    client = genai.Client(api_key=config.APIKEY)
    print(f"Directorio de trabajo: {directorio.resolve()}\n")

    conteo_categorias = {}
    archivos = sanear_archivos(directorio)

    if not archivos:
        print("No se encontraron archivos válidos para procesar.")
        return

    print("\n--- FASE 2: Clasificación por Nombre en Lote (Pasada 1 Ultra-rápida) ---")

    # 1 sola llamada a la API para evaluar todos los nombres
    clasificaciones = consultar_nombres_lote(archivos, client)

    pendientes = []

    for archivo in archivos:
        resultado = clasificaciones.get(archivo.name, "REVISAR_CONTENIDO")

        if resultado != "REVISAR_CONTENIDO":
            print(f"  [Por Nombre] '{archivo.name}' -> {resultado}")
            aplicar_nombre_final(archivo, resultado, 0, conteo_categorias)
        else:
            print(f"  [Indeterminado por Nombre] '{archivo.name}' -> Requiere 2da Pasada (OCR/Contenido)")
            pendientes.append(archivo)

    # Reporte de necesidad de segunda pasada
    if pendientes:
        print(f"\n[REPORTE ETAPAS] Se requiere 2da pasada por contenido para {len(pendientes)} archivo(s).")
        print("--- FASE 3: Clasificación por Contenido (Pasada 2) ---")
        idx_indeterminado = 1

        for archivo in pendientes:
            resultado = consultar_contenido(archivo, client)
            print(f"  [Por Contenido] '{archivo.name}' -> {resultado}")

            aplicar_nombre_final(archivo, resultado, idx_indeterminado, conteo_categorias)
            if resultado in ("REVISAR_CONTENIDO", "NO_CLASIFICADO"):
                idx_indeterminado += 1
    else:
        print("\n[REPORTE ETAPAS] ¡NO FUE NECESARIA LA 2da PASADA! Todos los archivos se clasificaron por nombre.")

    # Muestra el informe financiero/técnico de consumo de tokens
    tracker.reporte_final()
