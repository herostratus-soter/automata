import unicodedata
import pypdf
from google import genai # ia
from pathlib import Path #libreria para navegar y procesar rutas
from multiprocessing.dummy import Pool as ThreadPool #multihilo
import json
import pandas as pd


#--------------------funciones ia----------------------------


def schema_segmentador(ruta_ods, hoja="Hoja 1"):
    """schema para la segunda pasada: identifica los documentos distintos dentro de un compilado,
    con clasificación forzada contra el mismo catálogo del verificador."""

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


def schema_verificador(ruta_ods, hoja="Hoja 1"):
    """crea el schema para la configuracion de gemini"""

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


def ia_inspector(archivo_nube, prompt, contexto, schema, modelo):
    """
    Función pura: consulta con la IA gemini.
    Recibe una petición armada (ej. [archivo_subido, prompt])
    y devuelve el texto y los tokens.
    """

    config = {
        "system_instruction": contexto,
        "temperature": 0.0,
        "response_mime_type": "application/json",
        "response_schema": schema,
        }

    response = CLIENTE.models.generate_content(
        model = modelo,
        contents = [archivo_nube, prompt],
        config = config
        )

    return [
        response.text,
        response.usage_metadata.prompt_token_count,
        response.usage_metadata.candidates_token_count,
        response.usage_metadata.total_token_count,
        (response.usage_metadata.cached_content_token_count or 0)
        ]


def contar_tokens(respuestas):
    """suma los tokens de entrada y salida de las respuestas y actualiza las globales"""

    global CONTEO_TOKENS_IN, CONTEO_TOKENS_OUT, CONTEO_TOKENS_ALL, CONTEO_TOKENS_CACHE

    token_dir_in = 0
    token_dir_out = 0
    token_dir_all = 0
    token_dir_cache = 0

    for res in respuestas:
        token_dir_in += res[1]
        token_dir_out += res[2]
        token_dir_all += res[3]
        token_dir_cache += (res[4] or 0)

    CONTEO_TOKENS_IN += token_dir_in
    CONTEO_TOKENS_OUT += token_dir_out
    CONTEO_TOKENS_ALL += token_dir_all
    CONTEO_TOKENS_CACHE += token_dir_cache

    return token_dir_in, token_dir_out, token_dir_all, token_dir_cache


#------------------- rutas y archivos ---------------------------


def patron(directorio_actual):
    """busca en el nombre del directorio un patron y devuelve True or False"""

    nombre = directorio_actual.name
    return len(nombre) >= 6 and nombre[:6].isdigit() #booleano. primeros 6 caracteres que sean numeros


def buscar_dir(directorio, lista_resultados):
    """desde un directorio padre busca en todos directorios de manera recursiva y guarda en una lista
    la ruta de todos los directorios cuyo nombre coincidan con el patron"""

    directorio_path = Path(directorio)
    elementos = list(directorio_path.iterdir())

    for elemento in elementos:
        if elemento.is_dir():
            if patron(elemento): #verificacion de patron falso o verdadero
                lista_resultados.append(elemento.resolve())

            buscar_dir(elemento, lista_resultados) #continua la busqueda


def desbloquear_pdfs(directorio, clave):
    """revisa si los pdfs de la carpeta estan encriptados y los desbloquea usando la clave"""

    if not clave:
        return

    directorio_path = Path(directorio)
    for elemento in directorio_path.iterdir():
        if elemento.is_file() and elemento.suffix.lower() == ".pdf":
            try:
                reader = pypdf.PdfReader(elemento)
                if reader.is_encrypted:
                    if reader.decrypt(clave):
                        writer = pypdf.PdfWriter()
                        for page in reader.pages:
                            writer.add_page(page)
                        with open(elemento, "wb") as f:
                            writer.write(f)
            except Exception:
                pass


def get_archivos(directorio, formatos):
    """toma un directorio, renombra cada archivo válido como tmp<index><extensión>,
    y devuelve la lista con las rutas ya renombradas"""

    ruta_archivos = []
    directorio_path = Path(directorio)
    elementos = list(directorio_path.iterdir()) # obtiene todo lo que hay en el directorio

    index = 0
    for elemento in elementos:
        if elemento.is_file():# Filtra que sea un archivo y no una carpeta que termine en esa extensión
            extension = elemento.suffix.lower() # obtiene sufijo

            if extension in formatos: # filtra por formato
                nueva_ruta = elemento.parent / f"tmp{index}{extension}"
                elemento.rename(nueva_ruta)
                index += 1

                ruta_archivos.append(nueva_ruta.resolve()) # guarda ruta absoluta ya renombrada

    return ruta_archivos


#----------------------------operaciones-------------------------------------


def ods_string(ruta_ods, hoja="Hoja 1"):
    """lee la hoja de calculo .ODS con las reglas (reglas.ods) para el contexto de la IA"""

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


def obtener_id(directorio):
    """extrae el numero de identificacion del sujeto desde el nombre de la carpeta y tambien el nombre de la carpeta pariente"""

    entidad = Path(directorio).parent.name
    sujeto = Path(directorio).name
    id_dir = sujeto[:len(sujeto) - len(sujeto.lstrip("0123456789"))]
    return id_dir, sujeto, entidad


def ciclo_archivo(peticion_archivo):
    """
    Procesa un solo archivo de principio a fin:
    1. Lo sube a Gemini.
    2. Le hace la única petición de clasificación + verificación.
    3. Elimina el archivo remoto.
    4. Renombra el archivo original en disco según la categoría detectada.
    5. Guarda el resultado como JSON individual en OUTPUT_JSON.
    """
    ruta_archivo, datos_sujeto = peticion_archivo

    # --- 1. Subida y consulta a la IA ---
    archivo_nube = CLIENTE.files.upload(file=ruta_archivo)
    prompt = f"id: {datos_sujeto['id']}\nsujeto: {datos_sujeto['sujeto']}"
    contexto = CONTEXTO_VERIFICADOR
    schema = schema_verificador(RUTA_ODS)
    modelo = MODELO_LITE

    respuesta = ia_inspector(archivo_nube, prompt, contexto, schema, modelo)
    CLIENTE.files.delete(name=archivo_nube.name)

    # --- 2. Parseo de la respuesta ---
    resultado = json.loads(respuesta[0])

    # --- 3. Renombrar el documento original en disco ---
    nueva_ruta_archivo = ruta_archivo.parent / f"{resultado['id_documento']}_{resultado['tipo_documento']}_{ruta_archivo.name}"
    ruta_archivo.rename(nueva_ruta_archivo)
    resultado["ruta"] = str(nueva_ruta_archivo)

    # --- 4. Guardado del JSON individual ---
    nombre_json = f"{resultado['id_documento']}_{nueva_ruta_archivo.stem}.json"
    ruta_salida = datos_sujeto["salida"] / nombre_json  # antes: OUTPUT_JSON / nombre_json
    ruta_salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    return [resultado] + respuesta[1:]


def ciclo_archivo2(peticion):
    """Como ciclo_archivo, pero el tipo ya viene sugerido: solo se manda esa fila del .ods."""
    ruta_archivo, datos_sujeto, id_sugerido, tipo_sugerido = peticion

    contexto = CONTEXTO_VERIFICADOR_HEURISTICO + ods_fila_string(RUTA_ODS, id_sugerido)  # solo 1 fila, no las 27
    schema = schema_verificador(RUTA_ODS)  # el schema sí queda completo, por si toca corregir el tipo sugerido

    archivo_nube = CLIENTE.files.upload(file=ruta_archivo)
    prompt = f"id: {datos_sujeto['id']}\nsujeto: {datos_sujeto['sujeto']}\ntipo sugerido: {tipo_sugerido}"
    respuesta = ia_inspector(archivo_nube, prompt, contexto, schema, MODELO_LITE)
    CLIENTE.files.delete(name=archivo_nube.name)  # ya no se necesita en la nube

    resultado = json.loads(respuesta[0])

    # renombrar el archivo en disco según lo que confirmó/corrigió la IA
    nueva_ruta = ruta_archivo.parent / f"{resultado['id_documento']}_{resultado['tipo_documento']}_{ruta_archivo.name}"
    ruta_archivo.rename(nueva_ruta)
    resultado["ruta"] = str(nueva_ruta)

    # guardar el JSON individual, igual que ciclo_archivo
    nombre_json = f"{resultado['id_documento']}_{nueva_ruta.stem}.json"
    (datos_sujeto["salida"] / nombre_json).write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")  # antes: OUTPUT_JSON / nombre_json

    return [resultado] + respuesta[1:]  # misma forma que ciclo_archivo, para que contar_tokens funcione igual


def ods_fila_string(ruta_ods, id_documento, hoja="Hoja 1"):
    """Igual que ods_string, pero solo la fila de un id_documento puntual."""
    df = pd.read_excel(ruta_ods, engine="odf", sheet_name=hoja)
    fila = df[df["id"] == id_documento].iloc[0]

    bloque = f'id_documento {fila["id"]} — tipo_documento: "{fila["documento"]}"\nDescripción: {fila["descripcion"]}'
    for i in range(1, 5):
        requisito, output = fila.get(f"requisito{i}"), fila.get(f"output{i}")
        if pd.notna(requisito):
            bloque += f"\nreq{i}: {requisito} -> formato esperado: {output}"
    return bloque


def partir_pdf(ruta_pdf, segmentos):
    """Parte un PDF en un archivo nuevo por cada segmento (pagina_inicio/fin/id/tipo)."""
    lector = pypdf.PdfReader(ruta_pdf)
    nuevas_rutas = []

    for i, seg in enumerate(segmentos):
        escritor = pypdf.PdfWriter()
        for pagina in range(seg["pagina_inicio"] - 1, seg["pagina_fin"]):  # -1: pypdf indexa desde 0, el segmentador desde 1
            escritor.add_page(lector.pages[pagina])

        ruta_nueva = ruta_pdf.parent / f"{ruta_pdf.stem}_seg{i}.pdf"
        with open(ruta_nueva, "wb") as f:
            escritor.write(f)

        nuevas_rutas.append((ruta_nueva, seg["id_documento"], seg["tipo_documento"]))  # tipo va suelto, no en el pdf

    return nuevas_rutas


def procesar_compilado(respuestas, datos):
    """Detecta los 'compilado', los segmenta trabajando sobre una copia temporal, y limpia todo al final."""
    compilados = [res[0] for res in respuestas if res[0]["tipo_documento"] == "compilado"]

    peticion_segunda = []
    respuestas_seg = []

    for compilado in compilados:
        ruta_original_compilado = Path(compilado["ruta"])  # el original, nunca se toca
        ruta_temp_compilado = duplicar_temporal(ruta_original_compilado)

        try:
            schema = schema_segmentador(RUTA_ODS)
            archivo_nube = CLIENTE.files.upload(file=ruta_temp_compilado)
            respuesta_seg = ia_inspector(archivo_nube, "Segmenta este PDF.", CONTEXTO_SEGMENTADOR, schema, MODELO_FLASH)
            CLIENTE.files.delete(name=archivo_nube.name)
            respuestas_seg.append(respuesta_seg)

            segmentos = json.loads(respuesta_seg[0])["segmentos"]
            nuevos = partir_pdf(ruta_temp_compilado, segmentos)  # parte la copia, no el original
        finally:
            ruta_temp_compilado.unlink()  # la copia del compilado ya cumplió su función

        for ruta_seg, id_doc, tipo_doc, rango in nuevos:
            peticion_segunda.append((ruta_seg, datos, id_doc, tipo_doc, ruta_original_compilado, rango))

    return peticion_segunda, respuestas_seg


def operacion_dir(lista_carpetas):
    """Recorre cada carpeta, clasifica sus archivos, y reprocesa los compilados que aparezcan."""
    global CONTEO_ARCHIVOS, CONTEO_DIR
    for carpeta in lista_carpetas:
        CONTEO_DIR += 1
        id_sujeto, sujeto, entidad = obtener_id(carpeta)

        carpeta_salida = OUTPUT_JSON / id_sujeto
        carpeta_salida.mkdir(parents=True, exist_ok=True)
        datos = {"id": id_sujeto, "sujeto": sujeto, "entidad": entidad, "carpeta": carpeta, "salida": carpeta_salida}

        desbloquear_pdfs(carpeta, clave=id_sujeto)  # sigue igual: desbloquea el original, una sola vez, antes de todo
        ruta_archivos = get_archivos(carpeta, FORMATOS)  # ya no renombra nada, solo lista
        CONTEO_ARCHIVOS += len(ruta_archivos)

        # --- primera pasada: cada archivo trabaja sobre su propia copia temporal ---
        peticion_primera = [(ruta, datos) for ruta in ruta_archivos]
        respuestas = POOL.map(ciclo_archivo, peticion_primera)

        # --- segunda pasada: compilados, también sobre copias temporales ---
        peticion_segunda, respuestas_seg = procesar_compilado(respuestas, datos)
        if peticion_segunda:
            respuestas += POOL.map(ciclo_archivo2, peticion_segunda)

        contar_tokens(respuestas + respuestas_seg)
    POOL.close()
    POOL.join()

#--------------------------CONFIG.PY----------------


APIKEY = "nada"
CLIENTE = genai.Client(api_key=APIKEY)   # <- bug: usabas 'apikey' en minúscula, no existía esa variable

MODELO_FLASH = "gemini-2.5-flash"          # modelo completo: para el segmentador de compilados
MODELO_LITE = "gemini-3.1-flash-lite" # modelo económico: para la verificación normal de cada documento

DIR_PADRE = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/")
OUTPUT_JSON = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/automata/tmp/")
OUTPUT_JSON.mkdir(parents=True, exist_ok=True)

RUTA_ODS = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/reglas.ods")

FORMATOS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".docx"}

CONTEO_TOKENS_IN = 0
CONTEO_TOKENS_OUT = 0
CONTEO_TOKENS_ALL = 0
CONTEO_TOKENS_CACHE = 0
CONTEO_ARCHIVOS = 0
CONTEO_DIR = 0

POOL = ThreadPool(7)


#----------------------------------CONTEXTOS DE LA IA-----------------------
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

Catálogo de tipos de documento:
""" + ods_string(RUTA_ODS)


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
""" + ods_string(RUTA_ODS)


#----------------------------------EJECUCION-----------------------



DIR_TMP = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/ANDRES_ANGULO/EXPANSION-MOVISTAR/1144035109 CANO ORTIZ JUAN CARLOS/")

operacion_dir([DIR_TMP])

print(f"cantidad carpetas : {CONTEO_DIR}")
print(f"cantidad archivos : {CONTEO_ARCHIVOS}")
print(f"total tokens input: {CONTEO_TOKENS_IN}")
print(f"total tokens output: {CONTEO_TOKENS_OUT}")
print(f"total tokens total: {CONTEO_TOKENS_ALL}")




