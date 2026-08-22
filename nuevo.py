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
        "response_mime_type": "application/json",
    }
    return client, config, modelo


def ia_inspector(peticion):
    """consulta con la IA gemini.
    recibe una peticion que incluye la ruta de un archivo y un prompt,
    y devuelve el resultado de la consulta y los tokens gastados(in/out)"""

    input_archivo = CLIENTE.files.upload(file=peticion[0])
    prompt = peticion[1]
    response = CLIENTE.models.generate_content(
        model=MODELO,
        contents=[input_archivo, prompt],
        config=CONFIG
    )
    CLIENTE.files.delete(name=input_archivo.name)
    # Devuelves texto, tokens_entrada, tokens_salida
    return [
        response.text,
        response.usage_metadata.prompt_token_count,
        response.usage_metadata.candidates_token_count
        # RETORNAR COSTO
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


def get_archivos(directorio, formatos):
    """toma un directorio y extrae una lista con la rut de los archivos con formato valido"""

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

    global CONTEO_TOKENS_IN, CONTEO_TOKENS_OUT

    token_dir_in = 0
    token_dir_out = 0

    for res in respuestas:
        token_dir_in += res[1]
        token_dir_out += res[2]

    CONTEO_TOKENS_IN += token_dir_in
    CONTEO_TOKENS_OUT += token_dir_out


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


def operacion_dir(lista_carpetas):
    '''se le da la lista de las carpetas, busca los archivos que hay
    y a cada uno le hace una operacion utilizando un multihilo par agilizar'''

    global CONTEO_ARCHIVOS, CONTEO_DIR, PROMPT

    for carpeta in lista_carpetas:
        CONTEO_DIR += 1 #contar carpetas

        id_sujeto, sujeto, entidad = get_id(carpeta) #obtener el identificador del sujeto de la carpeta
        prompt = sujeto + "\n" + PROMPT #incluye a la persona en el prompt

        ruta_archivos = get_archivos(carpeta, FORMATOS)
        CONTEO_ARCHIVOS += len(ruta_archivos)

        peticiones = [] # creacion de lista pora que las peticioens sean (archivo + prompt)
        for ruta in ruta_archivos:
            peticiones.append((ruta, prompt))

        datos = {
            "id": id_sujeto,
            "sujeto": sujeto,
            "entidad": entidad,
            "carpeta": carpeta,
        }

        nombre_json = f"{CONTEO_DIR}_{id_sujeto}_resultado.json"
        respuestas = POOL.map(ia_inspector_tmp, peticiones) #operacion de la IA multihilo
        procesar_respuestas(datos, respuestas, RUTA_SALIDA / nombre_json)
        contar_tokens(respuestas)

    POOL.close() #cerrar multihilo
    POOL.join()


#--------------------------CONFIG.PY----------------

CONTEXTO = "Instrucciones fijas del sistema."
PROMPT = "Extrae los datos en formato JSON según el esquema."





APIKEY = "ejemplo"
MODELO = "gemini-2.5-flash-lite"

DIR_PADRE = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/TEMP/")
RUTA_SALIDA = Path("/home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/automata/tmp/")



FORMATOS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".docx"}

CLIENTE, CONFIG, MODELO = config_gemini(APIKEY, MODELO, CONTEXTO)


CONTEO_TOKENS_IN = 0
CONTEO_TOKENS_OUT = 0
CONTEO_ARCHIVOS = 0
CONTEO_DIR = 0

POOL = ThreadPool(7)







#----------------------------------EJECUCION-----------------------


ruta_carpetas = []
buscar_dir(DIR_PADRE,ruta_carpetas)
operacion_dir(ruta_carpetas)





print(f"cantidad carpetas : {CONTEO_DIR}")
print(f"cantidad archivos : {CONTEO_ARCHIVOS}")
print(f"total tokens input: {CONTEO_TOKENS_IN}")
print(f"total tokens output: {CONTEO_TOKENS_OUT}")





















































