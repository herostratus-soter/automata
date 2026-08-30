import unicodedata
import pypdf
from google import genai # ia
from pathlib import Path #libreria para navegar y procesar rutas
from multiprocessing.dummy import Pool as ThreadPool #multihilo

import json
import pandas as pd

#--------------------funciones ia----------------------------

def schema_segmentador():
    """schema para la segunda pasada: identifica los documentos distintos dentro de un compilado"""

    segmento = genai.types.Schema(
        type="OBJECT",
        properties={
            "pagina_inicio": genai.types.Schema(type="INTEGER"),
            "pagina_fin": genai.types.Schema(type="INTEGER"),
        },
        required=["pagina_inicio", "pagina_fin"],
    )
    return genai.types.Schema(
        type="OBJECT",
        properties={
            "segmentos": genai.types.Schema(type="ARRAY", items=segmento),
        },
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






def procesar_respuestas(datos, respuestas, ruta_salida="resultado.json"):
    """recibe dos listas erarquía 1 y las respuestas para guardar el JSON."""

    metadatos = ""
    ramas_pegadas = ""

    for clave, valor in datos.items(): # crear metadatos
        metadatos += f'  "{clave}": "{valor}",\n'

    for res in respuestas: #pegar los .json pequeños
        ramas_pegadas += res[0] + ",\n"

    ramas_pegadas = ramas_pegadas.rstrip(",\n") # Quitar coma sobrante final
    tronco_json = f'''{{\n{metadatos}  "contenido": [\n{ramas_pegadas}\n  ]\n}}''' #montaje .json
    open(ruta_salida, "w", encoding="utf-8").write(tronco_json) #guardar json




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
    nombre_json = f"{datos_sujeto['id']}_{resultado['id_documento']}_{nueva_ruta_archivo.stem}.json"
    ruta_salida = OUTPUT_JSON / nombre_json
    ruta_salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")

    return [resultado] + respuesta[1:]





def operacion_dir(lista_carpetas):
    '''se le da la lista de las carpetas, busca los archivos que hay
    y a cada uno le hace una operacion utilizando un multihilo para agilizar'''

    global CONTEO_ARCHIVOS, CONTEO_DIR

    for carpeta in lista_carpetas:
        CONTEO_DIR += 1

        id_sujeto, sujeto, entidad = obtener_id(carpeta)
        datos = {"id": id_sujeto, "sujeto": sujeto, "entidad": entidad, "carpeta": carpeta}

        # --- PRE-PROCESAMIENTO ---
        desbloquear_pdfs(carpeta, clave=id_sujeto)  # primero desbloquear, luego renombrar
        ruta_archivos = get_archivos(carpeta, FORMATOS)
        CONTEO_ARCHIVOS += len(ruta_archivos)

        peticion_archivo = [(ruta, datos) for ruta in ruta_archivos]
        respuestas = POOL.map(ciclo_archivo, peticion_archivo)

        # --- DETECCIÓN Y REPROCESO DE COMPILADOS ---
        compilados = [res[0] for res in respuestas if res[0]["tipo_documento"] == "compilado"]

        peticion_extra = []


        ##METER ESTOE N UNA FUNCION PARECIDA A CICLO ARCHIVO
        for comp in compilados:
            ruta_comp = Path(comp["ruta"])
            archivo_nube = CLIENTE.files.upload(file=ruta_comp)
            respuesta_seg = ia_inspector(
                archivo_nube, "Segmenta este PDF.",
                CONTEXTO_SEGMENTADOR, schema_segmentador(), MODELO_FLASH
            )
            CLIENTE.files.delete(name=archivo_nube.name)
            segmentos = json.loads(respuesta_seg[0])["segmentos"]

            nuevas_rutas = partir_pdf(ruta_comp, segmentos)  # ver función abajo
            peticion_extra += [(nueva_ruta, datos) for nueva_ruta in nuevas_rutas]

        if peticion_extra:
            respuestas += POOL.map(ciclo_archivo, peticion_extra)

        contar_tokens(respuestas)

    POOL.close()
    POOL.join()

#--------------------------CONFIG.PY----------------

APIKEY = "nada"
CLIENTE = genai.Client(api_key=APIKEY)   # <- bug: usabas 'apikey' en minúscula, no existía esa variable

MODELO_FLASH = "gemini-2.5-flash"          # modelo completo: para el segmentador de compilados
MODELO_LITE = "gemini-3.1-flash-lite" # modelo económico: para la verificación normal de cada documento

DIR_TMP = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/BANCO_DE_BOGOTA_JUNIO_2026/ALEXANDRA BARRERA/1061692931 CIFUENTES SANJUAN OSCAR DANIEL/")
DIR_PADRE = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/")
RUTA_SALIDA = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/automata/tmp/")
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
Identifica cada documento independiente y devuelve la página donde empieza y la página donde termina cada uno, en orden.
No clasifiques el contenido, solo delimita los cortes entre un documento y el siguiente."""

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

operacion_dir([DIR_TMP])



#operacion_dir(ruta_carpetas)





print(f"cantidad carpetas : {CONTEO_DIR}")
print(f"cantidad archivos : {CONTEO_ARCHIVOS}")
print(f"total tokens input: {CONTEO_TOKENS_IN}")
print(f"total tokens output: {CONTEO_TOKENS_OUT}")
print(f"total tokens total: {CONTEO_TOKENS_ALL}")


