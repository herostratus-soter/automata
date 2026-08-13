import sys
from pathlib import Path
from google import genai
from google.genai import types
import docx
import unicodedata

# Configuración desde carpeta padre
sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from prompts_tmp import *

FORMATOS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".docx"}

# Lista oficial de respuestas válidas esperadas
CLAVES_VALIDAS = {
    "01_documento_id", "02_contrato_laboral", "03_curso_etica", "04_curso_transparencia",
    "05_curso_cultura", "06_pruebas_psicotecnicas", "07_verificacion_referencias",
    "08_arl", "09_ccf", "10_examen_medico_ingreso", "11_antecedente_policia",
    "12_antecedente_procuraduria", "13_antecedente_contraloria", "14_cuenta_bancaria",
    "15_pension", "16_cesantias", "17_eps", "18_referencias", "19_estudios",
    "20_referencia_personal", "21_referencia_laboral", "22_hoja_de_vida",
    "23_formatos_para_la_contratacion", "REVISAR_CONTENIDO", "NO_CLASIFICADO"
}

class TokenTracker:
    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0

    def sumar(self, usage_metadata):
        """Acumula los tokens devueltos por la respuesta de Gemini."""
        if usage_metadata:
            self.input_tokens += getattr(usage_metadata, 'prompt_token_count', 0)
            self.output_tokens += getattr(usage_metadata, 'candidates_token_count', 0)

    def reporte_final(self):
        """Muestra en consola el resumen detallado de consumo y costos."""
        total = self.input_tokens + self.output_tokens
        # Precios base aproximados de Gemini 2.5 Flash
        costo_input = (self.input_tokens / 1_000_000) * 0.075
        costo_output = (self.output_tokens / 1_000_000) * 0.30
        costo_total = costo_input + costo_output

        print("\n" + "=" * 55)
        print("         RESUMEN DE CONSUMO DE TOKENS (GEMINI)")
        print("=" * 55)
        print(f" Tokens de Entrada (Input Prompt):   {self.input_tokens:>10,}")
        print(f" Tokens de Salida  (Output Text):    {self.output_tokens:>10,}")
        print("-" * 55)
        print(f" TOTAL TOKENS CONSUMIDOS:            {total:>10,}")
        print(f" Costo aproximado estimado:          ${costo_total:>10.6f} USD")
        print("=" * 55 + "\n")

# Instancia global que acumulará todo el proceso
tracker = TokenTracker()

def limpiar_texto(texto): # Quita tildes, caracteres especiales y espacios
    normalizado = unicodedata.normalize('NFD', texto)
    limpio = ''.join(c for c in normalizado if unicodedata.category(c) != 'Mn')
    limpio = ''.join(c for c in limpio if c.isalnum() or c in (' ', '_', '-')).strip()
    return limpio.replace(' ', '_')

def sanear_archivos(directorio, tag="temp"): # Elimina caracteres raros del nombre
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

def leer_word(path): # Extrae texto plano de un .docx
    doc = docx.Document(path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])

def peticion(contents, client):
    """
    Función centralizada para realizar llamadas a la API de Gemini.
    - Desactiva el thinking_budget para evitar respuestas parlanchinas.
    - Suma automáticamente los tokens consumidos al tracker.
    - Retorna el texto limpio de comillas y espacios.
    """
    config_gen = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0)
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=config_gen
    )

    # Registro centralizado de tokens
    tracker.sumar(response.usage_metadata)

    # Limpieza estricta del resultado
    return response.text.strip('\'" \n\r\t')

def consultar_nombre(nombre_archivo, client): # Pasada 1: Clasificación por String
    prompt = f"Nombre del archivo: {nombre_archivo}\n\n{PROMPT_POR_NOMBRE}"

    # Llamada modularizada
    res_limpia = peticion(prompt, client)

    # Validación de seguridad
    if res_limpia not in CLAVES_VALIDAS:
        return "REVISAR_CONTENIDO"

    return res_limpia

def consultar_contenido(archivo, client): # Pasada 2: OCR / Visión
    ext = archivo.suffix.lower()

    # Preparación de contenidos según el tipo de archivo
    if ext == ".docx":
        texto = leer_word(archivo)
        contents = [f"Contenido Word:\n{texto}", PROMPT_POR_CONTENIDO]
        remote = None
    else:
        remote = client.files.upload(file=archivo)
        contents = [remote, PROMPT_POR_CONTENIDO]

    # Llamada modularizada
    res_limpia = peticion(contents, client)

    # Limpieza del archivo remoto subido (si aplica)
    if remote:
        client.files.delete(name=remote.name)

    # Validación de seguridad
    if res_limpia not in CLAVES_VALIDAS:
        return "NO_CLASIFICADO"

    return res_limpia

def aplicar_nombre_final(archivo, clasificacion, index_indeterminado, conteo): # Asigna el nombre final
    if clasificacion in ("REVISAR_CONTENIDO", "NO_CLASIFICADO"):
        nuevo_stem = f"00_indeterminado_{index_indeterminado:02d}"
    else:
        conteo[clasificacion] = conteo.get(clasificacion, 0) + 1
        cantidad = conteo[clasificacion]

        if cantidad == 1:
            nuevo_stem = clasificacion
        else:
            nuevo_stem = f"{clasificacion}_{cantidad}"

    # Protección de seguridad contra nombres demasiado largos en el SO
    if len(nuevo_stem) > 60:
        nuevo_stem = f"00_indeterminado_{index_indeterminado:02d}"

    nueva_ruta = archivo.parent / f"{nuevo_stem}{archivo.suffix}"
    print(f"  [Resultado Final] '{archivo.name}' -> '{nueva_ruta.name}'")
    return archivo.rename(nueva_ruta)

def inspeccionar(directorio, client): # Coordina el flujo completo
    print(f"Directorio de trabajo: {directorio.resolve()}\n")

    conteo_categorias = {}
    archivos = sanear_archivos(directorio)

    print("\n--- FASE 2: Clasificación por Nombre (Ahorro de Tokens) ---")
    pendientes = []

    for archivo in archivos:
        resultado = consultar_nombre(archivo.name, client)

        if resultado != "REVISAR_CONTENIDO":
            print(f"  [Por Nombre] '{archivo.name}' -> {resultado}")
            aplicar_nombre_final(archivo, resultado, 0, conteo_categorias)
        else:
            print(f"  [Indeterminado por Nombre] '{archivo.name}' -> Requiere OCR/Contenido")
            pendientes.append(archivo)

    if pendientes:
        print("\n--- FASE 3: Clasificación por Contenido (Archivos Ambiguos) ---")
        idx_indeterminado = 1

        for archivo in pendientes:
            resultado = consultar_contenido(archivo, client)
            print(f"  [Por Contenido] '{archivo.name}' -> {resultado}")

            aplicar_nombre_final(archivo, resultado, idx_indeterminado, conteo_categorias)
            if resultado == "NO_CLASIFICADO":
                idx_indeterminado += 1
    else:
        print("\n¡Todos los archivos se clasificaron en la Fase 2! 0 tokens gastados en OCR.")

# Punto de entrada principal
if __name__ == "__main__":
    client = genai.Client(api_key=config.apikey)

    # Ejecutamos el flujo de inspección
    inspeccionar(Path(config.rutatemporal), client)
    print("\nProceso finalizado con éxito.")

    # Muestra el reporte financiero/técnico de tokens
    tracker.reporte_final()
