import os
import sys
from pathlib import Path
from google import genai

# Sube un nivel en la jerarquía de carpetas y añade la ruta a sys.path
parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

# Importa config.py
import config

originpath = Path(config.rutamaestro)
tmppath = Path("/home/bdi/Documentos/prototipo_automatizacion/TEMP/ANDRES_ANGULO/TIGO/32258650 PALACIOS PABON  LINA MARIA/")

# Cambiar al directorio de trabajo
os.chdir(tmppath)

# Inicializar cliente de Gemini
client = genai.Client(api_key=config.apikey)

# Obtener la lista de todos los archivos PDF en la carpeta
archivos_pdf = [f for f in os.listdir(".") if f.lower().endswith(".pdf")]

documento_encontrado = False

for pdf in archivos_pdf:
    print(f"Inspeccionando: {pdf}...")

    # 1. Cargar el PDF temporalmente a Gemini
    archivo_subido = client.files.upload(file=pdf)

    prompt = """
    Analiza este archivo PDF y responde lo siguiente:
    1. ¿Este documento es una Cédula de Ciudadanía o Documento de Identidad?
    2. Si NO es un documento de identidad, responde exactamente la palabra: NO_ES_CEDULA
    3. Si SÍ es un documento de identidad, extrae únicamente el número de documento y el nombre completo.

    Formato de respuesta si SÍ es documento de identidad:
    Número de Documento: <numero>
    Nombre Completo: <nombre_completo>
    """

    # 2. Consultar al modelo
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[archivo_subido, prompt]
    )

    resultado = response.text.strip()

    # 3. Eliminar el archivo de los servidores de Gemini para liberar espacio
    client.files.delete(name=archivo_subido.name)

    # 4. Verificar si Gemini encontró el documento de identidad
    if "NO_ES_CEDULA" not in resultado:
        print(f"¡Documento de identidad detectado en '{pdf}'!")

        # Guardar la información extraída en temporal.txt
        with open("temporal.txt", "w", encoding="utf-8") as f:
            f.write(resultado)

        documento_encontrado = True
        break  # Se detiene la búsqueda porque ya lo encontró

if not documento_encontrado:
    print("Se inspeccionaron todos los PDFs, pero no se encontró ninguna cédula.")