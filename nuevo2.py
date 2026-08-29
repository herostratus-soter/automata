import unicodedata
import pypdf
from google import genai # ia
from pathlib import Path #libreria para navegar y procesar rutas
from multiprocessing.dummy import Pool as ThreadPool #multihilo

import json
import pandas as pd

#--------------------funciones ia----------------------------


def config_gemini(apikey, modelo, contexto, schema):
    """configuracion de gemini que se llama solo una vez y
    entrega variables globales para usar en las llamadas de ia"""

    client = genai.Client(api_key=apikey)
    config = {
        "system_instruction": contexto,
        "temperature": 0.0,
        "response_mime_type": "application/json",
        "response_schema": schema,
        }
    return client, config, modelo


def esquemaods(ruta_ods, hoja="Hoja 1"):
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


def ia_inspector(archivo_nube, prompt):
    """
    Función pura: consulta con la IA gemini.
    Recibe una petición armada (ej. [archivo_subido, prompt])
    y devuelve el texto y los tokens.
    """
    response = CLIENTE.models.generate_content(
        model = MODELO,
        contents = [archivo_nube, prompt],
        config = CONFIG
        )

    return [
        response.text,
        response.usage_metadata.prompt_token_count,
        response.usage_metadata.candidates_token_count,
        response.usage_metadata.total_token_count,
        (response.usage_metadata.cached_content_token_count or 0)
        ]


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


def limpiar_texto(texto):
    """quita tildes, caracteres especiales y reemplaza espacios por guiones bajos"""

    normalizado = unicodedata.normalize('NFD', texto)
    limpio = ''.join(c for c in normalizado if unicodedata.category(c) != 'Mn')
    limpio = ''.join(c for c in limpio if c.isalnum() or c in (' ', '_', '-')).strip()
    return limpio.replace(' ', '_')


def sanear_carpeta(directorio):
    """renombra todos los archivos de la carpeta quitando tildes y caracteres especiales"""

    directorio_path = Path(directorio)
    for elemento in directorio_path.iterdir():
        if elemento.is_file() and elemento.suffix.lower() in FORMATOS:
            nombre_limpio = limpiar_texto(elemento.stem)
            nuevo_nombre = f"{nombre_limpio}{elemento.suffix.lower()}"
            nueva_ruta = elemento.parent / nuevo_nombre

            if elemento != nueva_ruta:
                elemento.rename(nueva_ruta)


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
    """toma un directorio y extrae una lista con la ruta de los archivos con formato valido"""

    ruta_archivos = []
    directorio_path = Path(directorio)
    elementos = list(directorio_path.iterdir()) # obtiene todo lo que hay en el directorio

    for elemento in elementos:
        if elemento.is_file():# Filtra que sea un archivo y no una carpeta que termine en esa extensión
            extension = elemento.suffix.lower() # obtiene sufijo

            if extension in formatos: # filtra por formato
                ruta_absoluta = elemento.resolve()
                ruta_archivos.append(ruta_absoluta) # guarda ruta absoluta

    return ruta_archivos


#----------------------------operaciones-------------------------------------


def reglasods(ruta_ods, hoja="Hoja 1"):
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


def get_id(directorio):
    """extrae el numero de identificacion del sujeto desde el nombre de la carpeta y tambien el nombre de la carpeta pariente"""

    entidad = Path(directorio).parent.name
    sujeto = Path(directorio).name
    id_dir = sujeto[:len(sujeto) - len(sujeto.lstrip("0123456789"))]
    return id_dir, sujeto, entidad


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
    3. Elimina el archivo remoto (ya no se necesita en la nube de Gemini).
    4. Renombra el PDF original en disco para que refleje la categoría detectada.
    5. Guarda el resultado como JSON individual en OUTPUT_JSON.

    peticion_archivo: tupla (ruta_archivo, datos_sujeto)
    devuelve: [resultado_dict, tokens_in, tokens_out, tokens_total, tokens_cache]
    """
    ruta_archivo, datos_sujeto = peticion_archivo

    # --- 1. Subida y consulta a la IA ---
    archivo_nube = CLIENTE.files.upload(file=ruta_archivo)
    prompt = f"id: {datos_sujeto['id']}\nsujeto: {datos_sujeto['sujeto']}"
    respuesta = ia_inspector(archivo_nube, prompt)

    # Ya tenemos la respuesta, no hace falta mantener el archivo en la nube de Gemini
    CLIENTE.files.delete(name=archivo_nube.name)

    # --- 2. Parseo de la respuesta ---
    resultado = json.loads(respuesta[0])

    # --- 3. Renombrar el documento original en disco ---
    # Nuevo nombre: <id_documento detectado>_<nombre original saneado><extensión original>
    nombre_limpio = limpiar_texto(ruta_archivo.stem)
    nueva_ruta_archivo = ruta_archivo.parent / f"{resultado['id_documento']}_{resultado['tipo_documento']}_{nombre_limpio}{ruta_archivo.suffix}"
    ruta_archivo.rename(nueva_ruta_archivo)

    # La ruta que guardamos en el resultado ya debe apuntar al archivo con su nombre nuevo
    resultado["ruta"] = str(nueva_ruta_archivo)

    # --- 4. Guardado del JSON individual (nombre igual que antes, sin tocar) ---
    nombre_json = f"{datos_sujeto['id']}_{resultado['id_documento']}_{nombre_limpio}.json"
    ruta_salida = OUTPUT_JSON / nombre_json
    ruta_salida.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # contar_tokens() espera esta forma: [resultado, tokens_in, tokens_out, tokens_all, tokens_cache]
    return [resultado] + respuesta[1:]


def operacion_dir(lista_carpetas):
    '''se le da la lista de las carpetas, busca los archivos que hay
    y a cada uno le hace una operacion utilizando un multihilo par agilizar'''

    global CONTEO_ARCHIVOS, CONTEO_DIR, PROMPT

    for carpeta in lista_carpetas:
        CONTEO_DIR += 1 #contar carpetas

        id_sujeto, sujeto, entidad = get_id(carpeta) #obtener el identificador del sujeto de la carpeta
        datos = {
            "id": id_sujeto,
            "sujeto": sujeto,
            "entidad": entidad,
            "carpeta": carpeta,
            }

        # --- PRE-PROCESAMIENTO DE ARCHIVOS ---
        sanear_carpeta(carpeta)                  # 1. Quita caracteres feos y espacios
        desbloquear_pdfs(carpeta, clave=id_sujeto) # 2. Desbloquea PDFs usando id_sujeto como clave

        ruta_archivos = get_archivos(carpeta, FORMATOS)
        CONTEO_ARCHIVOS += len(ruta_archivos)

        peticion_archivo = [] # creacion de lista pora que las peticioens sean (archivo + prompt)
        for ruta in ruta_archivos:
            peticion_archivo.append((ruta, datos))

        nombre_json = f"{CONTEO_DIR}_{id_sujeto}_resultado.json"
        respuestas = POOL.map(ciclo_archivo, peticion_archivo) #operacion de la IA multihilo
        procesar_respuestas(datos, respuestas, RUTA_SALIDA / nombre_json)
        contar_tokens(respuestas)

    POOL.close() #cerrar multihilo
    POOL.join()


#--------------------------CONFIG.PY----------------

APIKEY = "nothing"
#MODELO = "gemini-2.5-flash-lite"
MODELO = "gemini-3.1-flash-lite"
#MODELO = "gemini-2.5-flash"


DIR_TMP = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/BANCO_DE_BOGOTA_JUNIO_2026/ALEXANDRA BARRERA/1048325323   GONZALEZ FONSECA CARMEN CRISTINA/")
DIR_PADRE = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/")
RUTA_SALIDA = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/automata/tmp/")
OUTPUT_JSON = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/automata/tmp/")
OUTPUT_JSON.mkdir(parents=True, exist_ok=True)

FORMATOS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".docx"}

CONTEO_TOKENS_IN = 0
CONTEO_TOKENS_OUT = 0
CONTEO_TOKENS_ALL = 0
CONTEO_TOKENS_CACHE = 0
CONTEO_ARCHIVOS = 0
CONTEO_DIR = 0

POOL = ThreadPool(7)


#----------------------------------EJECUCION-----------------------

CONTEXTO_BASE = """Eres un identificador y examinador de documentos determinista. Examina cada archivo con OCR exhaustivo, sin importar el nombre del archivo, únicamente el contenido.

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

RUTA_ODS = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/reglas.ods")

FINALCONTEXT = CONTEXTO_BASE + reglasods(RUTA_ODS)
print(FINALCONTEXT)
SCHEMA = esquemaods(RUTA_ODS)

CLIENTE, CONFIG, MODELO = config_gemini(APIKEY, MODELO, FINALCONTEXT, SCHEMA)



carpeta = DIR_TMP
#buscar_dir(DIR_PADRE, ruta_carpetas)



id_sujeto, sujeto, entidad = get_id(carpeta) #obtener el identificador del sujeto de la carpeta
datos = {
    "id": id_sujeto,
    "sujeto": sujeto,
    "entidad": entidad,
    "carpeta": carpeta,
    }

# --- PRE-PROCESAMIENTO DE ARCHIVOS ---
sanear_carpeta(carpeta)                  # 1. Quita caracteres feos y espacios
desbloquear_pdfs(carpeta, clave=id_sujeto) # 2. Desbloquea PDFs usando id_sujeto como clave

ruta_archivos = get_archivos(carpeta, FORMATOS)
CONTEO_ARCHIVOS += len(ruta_archivos)

cont = 0
for ruta in ruta_archivos:

    print(cont,"---",ruta.name)
    cont += 1

peticion_archivo = [(ruta, datos) for ruta in ruta_archivos]

#peticion_archivo = [(ruta_archivos[9], datos)]

respuestas = POOL.map(ciclo_archivo, peticion_archivo)
POOL.close()
POOL.join()

contar_tokens(respuestas)








#operacion_dir(ruta_carpetas)





print(f"cantidad carpetas : {CONTEO_DIR}")
print(f"cantidad archivos : {CONTEO_ARCHIVOS}")
print(f"total tokens input: {CONTEO_TOKENS_IN}")
print(f"total tokens output: {CONTEO_TOKENS_OUT}")
print(f"total tokens total: {CONTEO_TOKENS_ALL}")


