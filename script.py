import pypdf
import json
import tempfile
import uuid
import shutil
import pandas as pd
from google import genai
from pathlib import Path
from multiprocessing.dummy import Pool as ThreadPool


#--------------------------CONFIGURACIÓN----------------

APIKEY = "nada"
CLIENTE = genai.Client(api_key=APIKEY)

MODELO_FLASH = "gemini-2.5-flash"      # modelo completo: para segmentar compilados (tarea más pesada)
MODELO_LITE = "gemini-3.1-flash-lite"  # modelo económico: para clasificar documentos sueltos


DIR_PADRE = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/")
OUTPUT_JSON = Path("/home/bdi/Documentos/prototipo_automatizacion/automata/tmp/")
OUTPUT_JSON.mkdir(parents=True, exist_ok=True)

RUTA_ODS = Path("/home/bdi/Documentos/prototipo_automatizacion/automata/reglas.ods")

FORMATOS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".docx"}

CONTEO_TOKENS_IN = 0
CONTEO_TOKENS_OUT = 0
CONTEO_TOKENS_ALL = 0
CONTEO_TOKENS_CACHE = 0
CONTEO_ARCHIVOS = 0
CONTEO_DIR = 0

POOL = ThreadPool(7)


#--------------------------CONTEXTOS DE LA IA----------------

# Contexto para la primera pasada: clasifica un documento suelto contra las 27 categorías.
CONTEXTO_VERIFICADOR = """Eres un identificador y examinador de documentos determinista. Examina cada archivo con OCR exhaustivo, sin importar el nombre del archivo, únicamente el contenido.

CLASIFICACIÓN: asigna el documento a uno de los tipos del catálogo siguiente, según su PROPÓSITO/CONTENIDO PRINCIPAL, no según su formato (carné, carta, certificado, constancia). Si no encaja claramente en ninguno, usa "otros".
"otros" es una respuesta válida y esperada, no un último recurso. Úsala con la misma comodidad que cualquier otra categoría del catálogo. Clasifica en una categoría específica solo si el documento cumple sus características centrales, no solo si comparte alguna palabra, tema, o mención superficial con ella. Ante duda razonable entre una categoría específica y "otros", responde "otros".

VERIFICACIÓN DE IDENTIDAD (número de identificación), reglas en este orden:
1. Si el documento no contiene ningún número de identificación de persona natural -> SIN_DATOS.
2. Si contiene un número de identificación y coincide exactamente con el id del sujeto entregado en la petición -> SI.
3. Si contiene un número de identificación distinto al del sujeto -> NO.

VERIFICACIÓN DE NOMBRE, reglas en este orden:
1. Si el documento no menciona ningún nombre de persona -> NO.
2. Considera que el nombre coincide (SI) si contiene las mismas palabras que el nombre del sujeto, sin importar el orden, mayúsculas/minúsculas, tildes, o si falta/sobra un segundo nombre o apellido.
3. Si el nombre encontrado comparte como máximo un apellido o nombre en común con el del sujeto -> NO.

Responde únicamente con la estructura de salida indicada, sin saludos ni texto adicional.
Además, incluye "razon_clasificacion": una explicación breve (máximo 15 palabras) de por qué elegiste ese tipo de documento y no otro parecido.

Catálogo de tipos de documento:
"""

# Contexto para trozos de compilados: el tipo ya viene sugerido por el segmentador, solo hay que confirmarlo.
CONTEXTO_VERIFICADOR_HEURISTICO = """Eres un identificador y examinador de documentos determinista.
Este archivo ya viene pre-clasificado por un paso de segmentación previo, con el tipo indicado más abajo.
Confirma esa clasificación si el documento realmente corresponde a ese tipo. Si al examinarlo ves que NO corresponde, usa "otros" y explica por qué en razon_clasificacion.

VERIFICACIÓN DE IDENTIDAD (número de identificación), reglas en este orden:
1. Si el documento no contiene ningún número de identificación de persona natural -> SIN_DATOS.
2. Si contiene un número de identificación y coincide exactamente con el id del sujeto entregado en la petición -> SI.
3. Si contiene un número de identificación distinto al del sujeto -> NO.

VERIFICACIÓN DE NOMBRE, reglas en este orden:
1. Si el documento no menciona ningún nombre de persona -> NO.
2. Considera que el nombre coincide (SI) si contiene las mismas palabras que el nombre del sujeto, sin importar el orden, mayúsculas/minúsculas, tildes, o si falta/sobra un segundo nombre o apellido.
3. Si el nombre encontrado comparte como máximo un apellido o nombre en común con el del sujeto -> NO.

Responde únicamente con la estructura de salida indicada, sin saludos ni texto adicional.
Además, incluye "razon_clasificacion": una explicación breve (máximo 15 palabras).

Tipo de documento sugerido para este archivo:
"""

# Contexto para el segmentador: solo delimita cortes de página, no verifica identidad ni nombre.
CONTEXTO_SEGMENTADOR = """Examina este PDF compilado, que contiene varios documentos distintos pegados en un mismo archivo.

Un documento nuevo EMPIEZA solo cuando cambia alguna de estas señales:
- Cambia el membrete, logo, o entidad emisora del documento.
- Cambia claramente el tipo de trámite o propósito del documento (ej. pasa de un certificado a un contrato).
- La numeración de página se reinicia (ej. vuelve a decir "Página 1 de X").

Un documento NO termina solo porque:
- Cambia el formato visual de una página a otra (texto corrido, tabla, firma) si sigue siendo el mismo trámite.
- Hay una firma, sello, o página de anexo que pertenece al mismo documento.
- La numeración de página continúa de forma consecutiva (ej. "Página 3 de 9" seguida de "Página 4 de 9") — eso indica que es EL MISMO documento multipágina, no uno nuevo por página.

Para cada segmento identificado, clasifícalo con el mismo criterio de precisión que usarías para un documento suelto: usa "otros" si no encaja claramente en ninguna categoría, no fuerces una categoría por parecido superficial.

Tener en cuenta que los cursos otorgados por Salesland pueden estar seguidos y parecer un documento continuo pero en realidad ser diferentes.

Catálogo de tipos de documento:
"""


#--------------------------LECTURA DEL CATÁLOGO (.ods)----------------


def ods_string(ruta_ods, hoja="Hoja 1"):
    """Convierte todas las filas del catálogo .ods en el bloque de texto que se pega al contexto."""

    df = pd.read_excel(ruta_ods, engine="odf", sheet_name=hoja)
    bloques = []
    for _, fila in df.iterrows():
        bloque = f'id_documento {fila["id"]} — tipo_documento: "{fila["documento"]}"\nDescripción: {fila["descripcion"]}'
        for i in range(1, 5):
            requisito, output = fila.get(f"requisito{i}"), fila.get(f"output{i}")
            if pd.notna(requisito):
                bloque += f"\nreq{i}: {requisito} -> formato esperado: {output}"
        bloques.append(bloque)
    return "\n\n".join(bloques)


def ods_fila_string(ruta_ods, id_documento, hoja="Hoja 1"):
    """Igual que ods_string, pero solo la fila de un id_documento puntual (para el prompt heurístico)."""

    df = pd.read_excel(ruta_ods, engine="odf", sheet_name=hoja)
    fila = df[df["id"] == id_documento].iloc[0]
    bloque = f'id_documento {fila["id"]} — tipo_documento: "{fila["documento"]}"\nDescripción: {fila["descripcion"]}'
    for i in range(1, 5):
        requisito, output = fila.get(f"requisito{i}"), fila.get(f"output{i}")
        if pd.notna(requisito):
            bloque += f"\nreq{i}: {requisito} -> formato esperado: {output}"
    return bloque


def schema_verificador(ruta_ods, hoja="Hoja 1"):
    """Arma el schema que fuerza la forma de salida del verificador de documentos sueltos."""

    df = pd.read_excel(ruta_ods, engine="odf", sheet_name=hoja)
    req = {f"req{i}": genai.types.Schema(type="STRING", nullable=True) for i in range(1, 5)}
    return genai.types.Schema(
        type="OBJECT",
        properties={
            "id_documento": genai.types.Schema(type="INTEGER", enum=[str(i) for i in df["id"]]),
            "tipo_documento": genai.types.Schema(type="STRING", enum=list(df["documento"])),
            "verificacion_identidad": genai.types.Schema(type="STRING", enum=["SI", "NO", "SIN_DATOS"]),
            "verificacion_nombre": genai.types.Schema(type="STRING", enum=["SI", "NO"]),
            "razon_clasificacion": genai.types.Schema(type="STRING"),
            "requerimientos": genai.types.Schema(type="OBJECT", properties=req, required=list(req)),
        },
        required=["id_documento", "tipo_documento", "verificacion_identidad", "verificacion_nombre", "razon_clasificacion", "requerimientos"],
    )


def schema_segmentador(ruta_ods, hoja="Hoja 1"):
    """Arma el schema del segmentador: lista de segmentos, cada uno con páginas + clasificación forzada."""

    df = pd.read_excel(ruta_ods, engine="odf", sheet_name=hoja)
    segmento = genai.types.Schema(
        type="OBJECT",
        properties={
            "pagina_inicio": genai.types.Schema(type="INTEGER"),
            "pagina_fin": genai.types.Schema(type="INTEGER"),
            "id_documento": genai.types.Schema(type="INTEGER", enum=[str(i) for i in df["id"]]),
            "tipo_documento": genai.types.Schema(type="STRING", enum=list(df["documento"])),
        },
        required=["pagina_inicio", "pagina_fin", "id_documento", "tipo_documento"],
    )
    return genai.types.Schema(
        type="OBJECT",
        properties={"segmentos": genai.types.Schema(type="ARRAY", items=segmento)},
        required=["segmentos"],
    )


#--------------------------LLAMADAS A LA IA----------------


def ia_inspector(archivo_nube, prompt, contexto, schema, modelo):
    """Hace una consulta a Gemini y devuelve el texto de respuesta junto con el conteo de tokens."""

    config = {
        "system_instruction": contexto,
        "temperature": 0.0,
        "response_mime_type": "application/json",
        "response_schema": schema,
    }
    response = CLIENTE.models.generate_content(model=modelo, contents=[archivo_nube, prompt], config=config)
    return [
        response.text,
        response.usage_metadata.prompt_token_count,
        response.usage_metadata.candidates_token_count,
        response.usage_metadata.total_token_count,
        (response.usage_metadata.cached_content_token_count or 0),
    ]


def contar_tokens(respuestas):
    """Suma los tokens de una lista de respuestas y los acumula en los contadores globales."""

    global CONTEO_TOKENS_IN, CONTEO_TOKENS_OUT, CONTEO_TOKENS_ALL, CONTEO_TOKENS_CACHE
    for res in respuestas:
        CONTEO_TOKENS_IN += res[1]
        CONTEO_TOKENS_OUT += res[2]
        CONTEO_TOKENS_ALL += res[3]
        CONTEO_TOKENS_CACHE += (res[4] or 0)


#--------------------------ARCHIVOS Y CARPETAS----------------


def patron(directorio_actual):
    """True si el nombre de la carpeta empieza con 6 dígitos (patrón de identificación)."""

    nombre = directorio_actual.name
    return len(nombre) >= 6 and nombre[:6].isdigit()


def buscar_dir(directorio, lista_resultados):
    """Recorre recursivamente un directorio y agrega a la lista las carpetas que cumplen el patrón."""

    for elemento in Path(directorio).iterdir():
        if elemento.is_dir():
            if patron(elemento):
                lista_resultados.append(elemento.resolve())
            buscar_dir(elemento, lista_resultados)  # sigue bajando aunque ya haya coincidido


def desbloquear_pdfs(directorio, clave):
    """Desencripta in-place los PDFs de una carpeta que tengan contraseña, usando la clave dada."""

    if not clave:
        return
    for elemento in Path(directorio).iterdir():
        if elemento.is_file() and elemento.suffix.lower() == ".pdf":
            try:
                reader = pypdf.PdfReader(elemento)
                if reader.is_encrypted and reader.decrypt(clave):
                    writer = pypdf.PdfWriter()
                    for page in reader.pages:
                        writer.add_page(page)
                    with open(elemento, "wb") as f:
                        writer.write(f)
            except Exception:
                pass  # PDF corrupto o clave incorrecta: se deja tal cual


def get_archivos(directorio, formatos):
    """Lista los archivos de formato válido en un directorio, sin tocarlos ni renombrarlos."""

    return [
        elemento.resolve()
        for elemento in Path(directorio).iterdir()
        if elemento.is_file() and elemento.suffix.lower() in formatos
    ]


def duplicar_temporal(ruta_original):
    """Crea una copia desechable de un archivo en el directorio temporal del sistema."""

    ruta_temp = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}{ruta_original.suffix}"
    shutil.copy2(ruta_original, ruta_temp)
    return ruta_temp


def obtener_id(directorio):
    """Extrae el id numérico del sujeto y el nombre de la carpeta/entidad pariente."""

    entidad = Path(directorio).parent.name
    sujeto = Path(directorio).name
    id_sujeto = sujeto[:len(sujeto) - len(sujeto.lstrip("0123456789"))]  # dígitos iniciales del nombre
    return id_sujeto, sujeto, entidad


#--------------------------PROCESAMIENTO DE UN ARCHIVO----------------


def _guardar_json_sin_colision(directorio_salida: Path, resultado: dict):
    """Guarda el JSON asegurando que si ya existe, le añade un contador (_1, _2...) para no sobrescribir."""
    base_nombre = f"{resultado['id_documento']}_{resultado['tipo_documento']}_{resultado.get('_sujeto_temp', '')}" # O usando los datos directos
    # Como tu lógica original usaba datos_sujeto['sujeto'], ajustamos el nombre base:
    # (Lo armamos limpio usando los campos del resultado)
    pass


def ciclo_archivo(peticion_archivo):
    """Clasifica un archivo suelto: trabaja sobre una copia temporal, el original nunca se toca."""

    ruta_original, datos_sujeto = peticion_archivo
    ruta_temp = duplicar_temporal(ruta_original)

    try:
        archivo_nube = CLIENTE.files.upload(file=ruta_temp)
        prompt = f"id: {datos_sujeto['id']}\nsujeto: {datos_sujeto['sujeto']}"
        contexto = CONTEXTO_VERIFICADOR + ods_string(RUTA_ODS)
        respuesta = ia_inspector(archivo_nube, prompt, contexto, schema_verificador(RUTA_ODS), MODELO_LITE)
        CLIENTE.files.delete(name=archivo_nube.name)  # ya no hace falta en la nube

        resultado = json.loads(respuesta[0])
        resultado["ruta"] = str(ruta_original)  # el json siempre apunta al archivo real, no a la copia

        # --- LÓGICA DE NOMBRE ÚNICO ---
        base_nombre = f"{resultado['id_documento']}_{resultado['tipo_documento']}" #_{datos_sujeto['sujeto']}
        ruta_json = datos_sujeto["salida"] / f"{base_nombre}.json"
        
        contador = 1
        while ruta_json.exists():
            ruta_json = datos_sujeto["salida"] / f"{base_nombre}_{contador}.json"
            contador += 1

        ruta_json.write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # -----------------------------

    finally:
        ruta_temp.unlink()  # la copia desaparece siempre, haya error o no

    return [resultado] + respuesta[1:]


def ciclo_archivo2(peticion):
    """Clasifica un trozo temporal de un compilado; el json referencia el compilado original + sus páginas."""

    ruta_seg, datos_sujeto, id_sugerido, tipo_sugerido, ruta_compilado_original, rango = peticion

    try:
        contexto = CONTEXTO_VERIFICADOR_HEURISTICO + ods_fila_string(RUTA_ODS, id_sugerido)
        archivo_nube = CLIENTE.files.upload(file=ruta_seg)
        prompt = f"id: {datos_sujeto['id']}\nsujeto: {datos_sujeto['sujeto']}\ntipo sugerido: {tipo_sugerido}"
        respuesta = ia_inspector(archivo_nube, prompt, contexto, schema_verificador(RUTA_ODS), MODELO_LITE)
        CLIENTE.files.delete(name=archivo_nube.name)

        resultado = json.loads(respuesta[0])
        resultado["ruta"] = f"{ruta_compilado_original} (páginas {rango})"  # nunca existió como archivo propio

        # --- LÓGICA DE NOMBRE ÚNICO ---
        base_nombre = f"{resultado['id_documento']}_{resultado['tipo_documento']}" #_{datos_sujeto['sujeto']}
        ruta_json = datos_sujeto["salida"] / f"{base_nombre}.json"
        
        contador = 1
        while ruta_json.exists():
            ruta_json = datos_sujeto["salida"] / f"{base_nombre}_{contador}.json"
            contador += 1

        ruta_json.write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # -----------------------------

    finally:
        ruta_seg.unlink()  # el trozo temporal desaparece siempre

    return [resultado] + respuesta[1:]
    
    
#--------------------------PROCESAMIENTO DE COMPILADOS----------------


def partir_pdf(ruta_pdf_temp, segmentos):
    """Parte una copia temporal de un compilado en un archivo temporal nuevo por cada segmento."""

    lector = pypdf.PdfReader(ruta_pdf_temp)
    nuevos = []
    for seg in segmentos:
        escritor = pypdf.PdfWriter()
        for pagina in range(seg["pagina_inicio"] - 1, seg["pagina_fin"]):  # -1: pypdf indexa desde 0
            escritor.add_page(lector.pages[pagina])

        ruta_seg = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex}.pdf"
        with open(ruta_seg, "wb") as f:
            escritor.write(f)

        rango = f"{seg['pagina_inicio']}-{seg['pagina_fin']}"
        nuevos.append((ruta_seg, seg["id_documento"], seg["tipo_documento"], rango))
    return nuevos


def procesar_compilado(respuestas, datos):
    """Detecta los 'compilado' en respuestas, los segmenta sobre una copia temporal y arma la petición extra."""

    compilados = [res[0] for res in respuestas if res[0]["tipo_documento"] == "compilado"]

    peticion_segunda = []
    respuestas_seg = []  # tokens del segmentador, aparte, para no perderlos del conteo total

    for compilado in compilados:
        ruta_original_compilado = Path(compilado["ruta"])
        ruta_temp_compilado = duplicar_temporal(ruta_original_compilado)

        try:
            schema = schema_segmentador(RUTA_ODS)
            contexto = CONTEXTO_SEGMENTADOR + ods_string(RUTA_ODS)
            archivo_nube = CLIENTE.files.upload(file=ruta_temp_compilado)
            respuesta_seg = ia_inspector(archivo_nube, "Segmenta este PDF.", contexto, schema, MODELO_FLASH)
            CLIENTE.files.delete(name=archivo_nube.name)
            respuestas_seg.append(respuesta_seg)

            segmentos = json.loads(respuesta_seg[0])["segmentos"]
            nuevos = partir_pdf(ruta_temp_compilado, segmentos)  # parte la copia, no el original
        finally:
            ruta_temp_compilado.unlink()  # la copia del compilado ya cumplió su función

        for ruta_seg, id_doc, tipo_doc, rango in nuevos:
            peticion_segunda.append((ruta_seg, datos, id_doc, tipo_doc, ruta_original_compilado, rango))

    return peticion_segunda, respuestas_seg


#--------------------------ORQUESTACIÓN----------------


def operacion_dir(lista_carpetas):
    """Recorre cada carpeta, clasifica sus archivos, y reprocesa los compilados que aparezcan."""

    global CONTEO_ARCHIVOS, CONTEO_DIR

    for carpeta in lista_carpetas:
        CONTEO_DIR += 1
        id_sujeto, sujeto, entidad = obtener_id(carpeta)

        carpeta_salida = OUTPUT_JSON / id_sujeto  # una subcarpeta de salida por sujeto
        carpeta_salida.mkdir(parents=True, exist_ok=True)
        datos = {"id": id_sujeto, "sujeto": sujeto, "entidad": entidad, "carpeta": carpeta, "salida": carpeta_salida}

        desbloquear_pdfs(carpeta, clave=id_sujeto)  # único paso que toca el original, y solo si estaba cifrado
        ruta_archivos = get_archivos(carpeta, FORMATOS)
        CONTEO_ARCHIVOS += len(ruta_archivos)

        # --- primera pasada: cada archivo se clasifica sobre su propia copia temporal ---
        peticion_primera = [(ruta, datos) for ruta in ruta_archivos]
        respuestas = POOL.map(ciclo_archivo, peticion_primera)

        # --- segunda pasada: solo para los que salieron como compilado ---
        peticion_segunda, respuestas_seg = procesar_compilado(respuestas, datos)
        if peticion_segunda:  # puede que esta carpeta no tenga ningún compilado
            respuestas += POOL.map(ciclo_archivo2, peticion_segunda)

        contar_tokens(respuestas + respuestas_seg)  # suma todo: normales + compilados + segmentador

    POOL.close()  # se cierra una sola vez, al terminar TODAS las carpetas
    POOL.join()


#--------------------------EJECUCIÓN----------------
DIR_TMP = Path("/home/bdi/Documentos/prototipo_automatizacion/TEMP/ANDREA_PEREZ/BANCO_DE_BOGOTA_JUNIO_2026/ALEXANDRA BARRERA/1118567238 NARANJO PATIÑO MARIA ALEJANDRA/")

operacion_dir([DIR_TMP])

print(f"cantidad carpetas : {CONTEO_DIR}")
print(f"cantidad archivos : {CONTEO_ARCHIVOS}")
print(f"total tokens input: {CONTEO_TOKENS_IN}")
print(f"total tokens output: {CONTEO_TOKENS_OUT}")
print(f"total tokens total: {CONTEO_TOKENS_ALL}")
