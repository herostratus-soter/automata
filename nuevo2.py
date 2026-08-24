import unicodedata
import pypdf
from google import genai # ia
from pathlib import Path #libreria para navegar y procesar rutas
from multiprocessing.dummy import Pool as ThreadPool #multihilo


#--------------------funciones ia----------------------------


def config_gemini(apikey, modelo, contexto):
    """configuracion de gemini que se llama solo una vez y
    entrega variables globales para usar en las llamadas de ia"""

    client = genai.Client(api_key=apikey)
    config = {
        "system_instruction": contexto,
        "temperature": 0.0,
        #"response_mime_type": "application/json",
        }
    return client, config, modelo


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


def ia_inspector_tmp(peticion):
    ruta_archivo = peticion[0]

    # Extraemos solo el nombre del archivo para identificarlo en la prueba
    nombre_archivo = Path(ruta_archivo).name

    # Generamos un JSON falso que simula la respuesta de la IA para ese archivo
    json_falso = f'{{"archivo_procesado": "{nombre_archivo}", "estado": "ok", "analisis": "prueba exitosa"}}'

    # Simulamos el conteo de tokens: 150 de entrada, 50 de salida
    tokens_in = 150
    tokens_out = 50

    return [json_falso, tokens_in, tokens_out]


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
    """Gestiona la carga, hace peticiones en cascada y elimina el archivo."""

    ruta_archivo, datos_sujeto = peticion_archivo
    archivo_nube = CLIENTE.files.upload(file=ruta_archivo)

    print(ruta_archivo.name)
    print(ruta_archivo.name)
    # Corrección 2: Usar comillas simples dentro del diccionario en el f-string
    prompt_1 = f"id: {datos_sujeto['id']}\n" + PROMPT
    print("prompt_1: ",prompt_1)
    peticion_1 = ia_inspector(archivo_nube, prompt_1)

    # Corrección 3: Limpiar corchetes sobrantes
    archivo_tipo = peticion_1[0].strip()
    prompt_2_texto = DIC_PROMPTS.get(archivo_tipo, DIC_PROMPTS['03_OTRO'])
    prompt_2 = f"id: {datos_sujeto['id']}\n" + prompt_2_texto

    print("prompt_2: ",prompt_2)
    peticion_2 = ia_inspector(archivo_nube, prompt_2)

    print("peticion 1")
    print("res: ",peticion_1[0])
    print("tk in: ",peticion_1[1])
    print("tk out: ",peticion_1[2])
    print("tk all: ",peticion_1[3])
    print("tk cache: ",peticion_1[4])
    print("peticion 2")
    print("res: ",peticion_2[0])
    print("tk in: ",peticion_2[1])
    print("tk out: ",peticion_2[2])
    print("tk all: ",peticion_2[3])
    print("tk cache: ",peticion_2[4])
    # Aquí armarías lo que vas a retornar basado en peticion_1 y peticion_2
    CLIENTE.files.delete(name=archivo_nube.name)
    return peticion_2



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

CONTEXTO = "identificador y examinador de archivos determinista. La salida de los prompts unicamente seran texto explicito, nada de saludos ni exageracion. debes examinar con el OCR exhaustivamente los documentos sin importar el nombre de estos. unicamente importa el contenido."

PROMPT = """Examina el archivo con OCR exhaustivo. Clasifica el documento según su PROPÓSITO/CONTENIDO PRINCIPAL, sin importar el formato (carné, carta, certificado, constancia).

Reglas de clasificación (revisa en este orden):

1. 01_CEDULA: el archivo es una foto o escaneo del documento de identidad (cédula) de la persona, por delante y/o detrás, con foto del rostro. Es el documento físico en sí, no una mención de él.

2. 02_EPS: el documento certifica, confirma o reporta la afiliación de una persona a una EPS (Entidad Promotora de Salud), sin importar si es un carné físico, una carta de una EPS, o un certificado/constancia de afiliación. Ejemplos de encabezados típicos: "Certificado de Afiliación", "Constancia de Afiliación EPS", cartas emitidas por una EPS confirmando régimen contributivo/subsidiado. Identifica esto por el CONTENIDO (habla de afiliación, régimen, cotizante, EPS) no solo por si menciona una cédula.

3. 03_OTRO: cualquier documento que no encaje en las dos categorías anteriores, incluyendo certificados de otras entidades (Contraloría, Procuraduría, cámaras de comercio, certificados laborales, etc.) aunque mencionen el número o tipo de cédula de una persona dentro del texto.

IMPORTANTE: no clasifiques por el tipo de emisor (si es "una carta" o "un certificado") sino por el TEMA del documento. Una carta de una EPS sobre afiliación es 01_EPS, no 03_OTRO.

Responde únicamente con una de estas tres palabras exactas: 01_CEDULA, 01_EPS, 03_OTRO. Sin explicaciones, sin saludos, sin texto adicional."""

DIC_PROMPTS = {
    '01_CEDULA': "devuelve la palabra: soy una cedula + la fecha de expedicion en formato aaaammdd. Si no encuentras explícitamente escrita la fecha de expedición en el documento, responde exactamente: FECHA_NO_ENCONTRADA. No inventes ni calcules la fecha a partir de otros datos como códigos de verificación.",

    '02_EPS': "devuelve el nombre de la EPS en mayúsculas, seguido de un guion y el Estado_Actual o Estado_Afiliación si aparece en el documento (ej: VIGENTE, CANCELADA). Si no encuentras el nombre de la EPS, responde: EPS_NO_ENCONTRADA.",

    '03_OTRO': """devuelve la palabra: otro + el título real del documento.

El título es el encabezado principal o el nombre del trámite/certificado que aparece normalmente en la parte superior del documento (ej: 'CERTIFICADO DE ANTECEDENTES FISCALES', 'CONSTANCIA DE AFILIACIÓN', 'CARTA LABORAL').

NO uses como título valores que aparezcan dentro de tablas de datos, campos como 'Tipo Documento', 'Nombre', 'Identificación' ni ningún dato personal del sujeto. Ignora esos campos aunque contengan palabras como 'cédula' o 'ciudadanía'.

Si no puedes identificar un título claro, responde: TITULO_NO_ENCONTRADO."""
}

APIKEY = "nada"
MODELO = "gemini-2.5-flash-lite"

DIR_TMP = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/BANCO_DE_BOGOTA_JUNIO_2026/ALEXANDRA BARRERA/1005189477 DUARTE ROJAS MARIAN ANDREA/")
DIR_PADRE = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/")
RUTA_SALIDA = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/automata/tmp/")



FORMATOS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".docx"}

CLIENTE, CONFIG, MODELO = config_gemini(APIKEY, MODELO, CONTEXTO)


CONTEO_TOKENS_IN = 0
CONTEO_TOKENS_OUT = 0
CONTEO_TOKENS_ALL = 0
CONTEO_TOKENS_CACHE = 0


CONTEO_ARCHIVOS = 0
CONTEO_DIR = 0

POOL = ThreadPool(7)


#----------------------------------EJECUCION-----------------------


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
for ruta in ruta_archivos:
    print(ruta.name)


peticion_archivo = [(ruta_archivos[17],datos)] # creacion de lista pora que las peticioens sean (archivo + prompt)

nombre_json = f"{CONTEO_DIR}_{id_sujeto}_resultado.json"

respuestas = []
for peticion in peticion_archivo:
    out = ciclo_archivo(peticion)
    respuestas.append(out)

procesar_respuestas(datos, respuestas, RUTA_SALIDA / nombre_json)
contar_tokens(respuestas)









#operacion_dir(ruta_carpetas)





print(f"cantidad carpetas : {CONTEO_DIR}")
print(f"cantidad archivos : {CONTEO_ARCHIVOS}")
print(f"total tokens input: {CONTEO_TOKENS_IN}")
print(f"total tokens output: {CONTEO_TOKENS_OUT}")
print(f"total tokens total: {CONTEO_TOKENS_ALL}")
