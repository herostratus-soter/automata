import os
import sys
import json
from pathlib import Path
import pypdf
from google import genai
from google.genai import types

# Configuración de importaciones (carpeta padre primero)
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from tokens import tracker

MODEL_ID = config.MODELO_DEFAULT


# --- 1. LLAMADA ULTRA-RÁPIDA (BATCH) EN UNA SOLA PETICIÓN ---

def analizar_carpeta_en_lote(nombre_carpeta: str, archivos: list) -> tuple[str, str, bool]:
    """
    Envía todos los nombres de una sola vez a Gemini para que determine
    la cédula por consenso y el nombre completo en UNA SOLA respuesta JSON.
    """
    client = genai.Client(api_key=config.APIKEY)

    prompt = f"""
    Analiza los siguientes nombres de archivos y carpeta perteneciente a un usuario.

    Nombre de la carpeta: "{nombre_carpeta}"
    Archivos contenidos: {json.dumps(archivos, ensure_ascii=False)}

    Instrucciones:
    1. Extrae todas las cédulas/documentos de identidad que encuentres en los nombres.
    2. Determina la cédula principal por consenso.
    3. Extrae el Nombre y Apellido completo de la persona.

    Responde ÚNICAMENTE en formato JSON con la siguiente estructura (sin bloques markdown ni explicaciones):
    {{
        "cedula": "dígitos_o_NINGUNO",
        "nombre": "Apellido_Nombre_o_NINGUNO",
        "consenso_en_nombres": true_o_false
    }}
    """

    config_gen = types.GenerateContentConfig(
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0)
    )

    resp = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=config_gen
    )

    # Registro de tokens
    tracker.sumar(resp.usage_metadata)

    try:
        data = json.loads(resp.text.strip())
        cedula = data.get("cedula") if data.get("cedula") != "NINGUNO" else None
        nombre = data.get("nombre") if data.get("nombre") != "NINGUNO" else None
        consenso = data.get("consenso_en_nombres", False)
        return cedula, nombre, consenso
    except Exception:
        return None, None, False


# --- 2. ACCIONES SOBRE ARCHIVOS Y FORMATO ---

def desbloquear_pdf_si_encriptado(ruta_pdf: str, clave: str):
    try:
        reader = pypdf.PdfReader(ruta_pdf)
        if reader.is_encrypted and reader.decrypt(clave):
            writer = pypdf.PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            with open(ruta_pdf, "wb") as f:
                writer.write(f)
    except Exception:
        pass


def desbloquear_carpeta(ruta_carpeta: str, archivos: list, clave: str):
    if not clave:
        return
    for archivo in archivos:
        if archivo.lower().endswith(".pdf"):
            ruta_pdf = os.path.join(ruta_carpeta, archivo)
            desbloquear_pdf_si_encriptado(ruta_pdf, clave)


def formatear_registro(cedula: str, nombre: str) -> str:
    doc = cedula.strip() if cedula else "NO_DETECTADO"

    if nombre:
        nombre_limpio = "_".join(nombre.strip().split())
    else:
        nombre_limpio = "NO_DETECTADO"

    return f"{doc},{nombre_limpio}"


def guardar_id_txt(ruta_carpeta: str, cedula: str, nombre: str):
    ruta_txt = os.path.join(ruta_carpeta, "id.txt")
    registro = formatear_registro(cedula, nombre)

    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(registro)


# --- 3. FUNCIÓN PRINCIPAL ---

def identificar(ruta_carpeta: str):
    archivos = [f for f in os.listdir(ruta_carpeta) if not f.startswith(".")]
    nombre_carpeta = os.path.basename(os.path.normpath(ruta_carpeta))

    print(f"--- PROCESANDO CARPETA: {nombre_carpeta} ---")

    # UNA SOLA LLAMADA a Gemini con todos los nombres
    cedula_ganadora, nombre_ganador, hay_consenso = analizar_carpeta_en_lote(nombre_carpeta, archivos)

    # Reporte de si se requirió segunda pasada
    if hay_consenso and cedula_ganadora:
        print(f"[REPORTE ETAPAS] Cédula encontrada por consenso en nombres ({cedula_ganadora}). NO SE REQUIERE 2da pasada.")
    else:
        print("[REPORTE ETAPAS] No hubo consenso claro por nombres. Se requiere evaluación por contenido.")

    # Desbloqueo y guardado
    desbloquear_carpeta(ruta_carpeta, archivos, cedula_ganadora)
    guardar_id_txt(ruta_carpeta, cedula_ganadora, nombre_ganador)

    # Reporte de tokens consumidos
    tracker.reporte_final()
