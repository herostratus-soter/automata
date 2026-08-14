import os
import sys
import json
from pathlib import Path
import pypdf

sys.path.append(str(Path(__file__).resolve().parent.parent))
from ai import consultar_ai


# --- 1. CONSULTA AI EN LOTE ---

def analizar_carpeta_en_lote(nombre_carpeta, archivos):
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

    res_raw, inp, out = consultar_ai(prompt, es_json=True)
    data = json.loads(res_raw)

    cedula = data.get("cedula") if data.get("cedula") != "NINGUNO" else None
    nombre = data.get("nombre") if data.get("nombre") != "NINGUNO" else None
    consenso = data.get("consenso_en_nombres", False)

    return [cedula, nombre, consenso, inp, out]


# --- 2. ACCIONES SOBRE ARCHIVOS Y FORMATO ---

def desbloquear_pdf_si_encriptado(ruta_pdf, clave):
    reader = pypdf.PdfReader(ruta_pdf)
    if reader.is_encrypted and reader.decrypt(clave):
        writer = pypdf.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with open(ruta_pdf, "wb") as f:
            writer.write(f)


def desbloquear_carpeta(ruta_carpeta, archivos, clave):
    if not clave:
        return
    for archivo in archivos:
        if archivo.lower().endswith(".pdf"):
            ruta_pdf = os.path.join(ruta_carpeta, archivo)
            desbloquear_pdf_si_encriptado(ruta_pdf, clave)


def formatear_registro(cedula, nombre):
    doc = cedula.strip() if cedula else "NO_DETECTADO"
    nombre_limpio = "_".join(nombre.strip().split()) if nombre else "NO_DETECTADO"
    return f"{doc},{nombre_limpio}"


def guardar_id_txt(ruta_carpeta, cedula, nombre):
    ruta_txt = os.path.join(ruta_carpeta, "id.txt")
    registro = formatear_registro(cedula, nombre)
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(registro)


# --- 3. FUNCIÓN PRINCIPAL ---

def identificar(ruta_carpeta):
    archivos = [f for f in os.listdir(ruta_carpeta) if not f.startswith(".")]
    nombre_carpeta = os.path.basename(os.path.normpath(ruta_carpeta))

    print(f"--- PROCESANDO CARPETA: {nombre_carpeta} ---")

    cedula_ganadora, nombre_ganador, hay_consenso, inp, out = analizar_carpeta_en_lote(nombre_carpeta, archivos)

    if hay_consenso and cedula_ganadora:
        print(f"[REPORTE ETAPAS] Cédula encontrada por consenso en nombres ({cedula_ganadora}). NO SE REQUIERE 2da pasada.")
    else:
        print("[REPORTE ETAPAS] No hubo consenso claro por nombres. Se requiere evaluación por contenido.")

    desbloquear_carpeta(ruta_carpeta, archivos, cedula_ganadora)
    guardar_id_txt(ruta_carpeta, cedula_ganadora, nombre_ganador)

    return [inp, out]
