"""
script_v2.py — Verificador automático de carpetas de contratación.

Adaptado para leer reglas_v2.ods (formato vertical: una fila por requerimiento).
La configuración vive en config.py (credenciales, rutas, modelos).

Cambios respecto al script original:
  • La configuración se importa de config.py en vez de estar hardcodeada.
  • Las funciones de lectura del catálogo (ods_string, ods_fila_string,
    schema_verificador, schema_segmentador) ahora leen el formato vertical
    agrupando por id de documento.
  • El catálogo se lee del disco UNA sola vez y se cachea en memoria
    (antes se releía en cada llamada a la IA).
  • Los cursos Salesland ahora son 4 tipos independientes
    (curso_etica, curso_cultura, curso_transparencia, curso_otro).
  • La cantidad de campos req1..reqN se calcula automáticamente
    según el tipo con más requerimientos en el catálogo.
  • Se eliminó la función _guardar_json_sin_colision (estaba vacía).
  • El resto de la lógica es IDÉNTICA al script original.
"""

import sys
import time
import pypdf
import json
import tempfile
import uuid
import shutil
import pandas as pd
from google import genai
from pathlib import Path
from multiprocessing.dummy import Pool as ThreadPool

from config import (
    APIKEY, MODELO_FLASH, MODELO_LITE,
    RUTA_ODS, RUTA_SALIDA_JSON, RUTA_PRUEBA, RUTA_PADRE,
    FORMATOS, HILOS,
    RUTA_LOGS, MAX_REINTENTOS, ESPERA_BASE,
)

from robustez import reintentar, EstadoLote, configurar_logs


#--------------------------CONFIGURACIÓN----------------

CLIENTE = genai.Client(api_key=APIKEY)

OUTPUT_JSON = RUTA_SALIDA_JSON
OUTPUT_JSON.mkdir(parents=True, exist_ok=True)

CONTEO_TOKENS_IN = 0
CONTEO_TOKENS_OUT = 0
CONTEO_TOKENS_ALL = 0
CONTEO_TOKENS_CACHE = 0
CONTEO_ARCHIVOS = 0
CONTEO_DIR = 0

POOL = ThreadPool(HILOS)

log = configurar_logs(RUTA_LOGS)


#--------------------------CONTEXTOS DE LA IA----------------

# Contexto para la primera pasada: clasifica un documento suelto contra todas las categorías.
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
Incluye "fiabilidad": un número de 0.0 a 1.0 que indica qué tan seguro estás de la clasificación (1.0 = certeza total, 0.0 = pura conjetura).

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
Incluye "fiabilidad": un número de 0.0 a 1.0 que indica qué tan seguro estás de la clasificación.

Tipo de documento sugerido para este archivo:
"""

# Contexto para la segunda pasada: el tipo ya se conoce, solo evalúa los requisitos específicos.
CONTEXTO_REQUISITOS = """Eres un evaluador determinista de requisitos documentales.
Ya se clasificó este documento. Ahora evalúa ÚNICAMENTE los requisitos indicados, siguiendo estrictamente el formato esperado de cada uno.
Devuelve exactamente los campos indicados, sin agregar ni omitir ninguno. No devuelvas null a menos que el dato realmente no exista o no sea legible en el documento.
Responde únicamente con la estructura de salida indicada, sin texto adicional.

Requisitos a evaluar:
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

Tener en cuenta que los certificados de cursos otorgados por Salesland (curso_etica, curso_cultura, curso_transparencia, curso_otro) pueden estar seguidos y parecer un documento continuo pero en realidad ser certificados diferentes.

Catálogo de tipos de documento:
"""


#--------------------------LECTURA DEL CATÁLOGO (.ods)----------------
#
# Estas funciones leen reglas_v2.ods (formato vertical).
# Cada fila del catálogo tiene: id | documento | descripcion | requisito | output
# Un tipo de documento puede tener 0, 1 o varias filas (una por requerimiento).
# Las funciones agrupan por id para reconstruir el bloque de texto de cada tipo.
#
# El catálogo se cachea en _cache_ods para no releer el disco en cada hilo.


_cache_ods = {}


def _leer_ods(ruta_ods, hoja="Hoja 1"):
    """Lee el catálogo una sola vez y lo mantiene en memoria para no releer el disco."""

    clave = (str(ruta_ods), hoja)
    if clave not in _cache_ods:
        _cache_ods[clave] = pd.read_excel(ruta_ods, engine="odf", sheet_name=hoja)
    return _cache_ods[clave]


def reqs_por_tipo(ruta_ods, tipo_documento, hoja="Hoja 1"):
    """Devuelve la lista de requisitos de un tipo: [{id_requisito, descripcion, output}, ...].
    Lista vacía si el tipo no tiene requisitos.
    """
    df = _leer_ods(ruta_ods, hoja)
    grupo = df[df["tipo de documento"] == tipo_documento].dropna(subset=["descripcion requisito"])
    return [
        {"id_requisito": str(fila["id_requisito"]).strip(), "descripcion": fila["descripcion requisito"], "output": fila["output"]}
        for _, fila in grupo.iterrows()
    ]


def ods_string(ruta_ods, hoja="Hoja 1"):
    """Convierte todas las filas del catálogo en el bloque de texto que se pega al contexto."""

    df = _leer_ods(ruta_ods, hoja)
    bloques = []
    for i, (tipo_doc, grupo) in enumerate(df.groupby("tipo de documento", sort=False), 1):
        primera = grupo.iloc[0]
        bloque = f'id_documento {i} — tipo_documento: "{tipo_doc}"\nDescripción: {primera["descripcion tipo de documento"]}'
        reqs_con_dato = grupo.dropna(subset=["descripcion requisito"])
        for j, (_, fila) in enumerate(reqs_con_dato.iterrows(), 1):
            bloque += f"\nreq{j}: {fila['descripcion requisito']} -> formato esperado: {fila['output']}"
        bloques.append(bloque)
    return "\n\n".join(bloques)


def ods_fila_string(ruta_ods, id_documento, hoja="Hoja 1"):
    """Igual que ods_string, pero solo el bloque de un id_documento puntual (para el prompt heurístico)."""

    df = _leer_ods(ruta_ods, hoja)
    tipos_unicos = df["tipo de documento"].unique()

    if isinstance(id_documento, int) and 1 <= id_documento <= len(tipos_unicos):
        tipo_doc = tipos_unicos[id_documento - 1]
        id_num = id_documento
    elif str(id_documento) in tipos_unicos:
        tipo_doc = str(id_documento)
        id_num = list(tipos_unicos).index(tipo_doc) + 1
    else:
        return ""

    grupo = df[df["tipo de documento"] == tipo_doc]
    primera = grupo.iloc[0]
    bloque = f'id_documento {id_num} — tipo_documento: "{tipo_doc}"\nDescripción: {primera["descripcion tipo de documento"]}'
    reqs_con_dato = grupo.dropna(subset=["descripcion requisito"])
    for j, (_, fila) in enumerate(reqs_con_dato.iterrows(), 1):
        bloque += f"\nreq{j}: {fila['descripcion requisito']} -> formato esperado: {fila['output']}"
    return bloque


def schema_clasificador(ruta_ods, hoja="Hoja 1"):
    """Schema para el paso 1: solo clasificación y verificación de identidad/nombre. Sin requisitos."""

    df = _leer_ods(ruta_ods, hoja)
    tipos = list(df["tipo de documento"].unique())
    ids_validos = [str(i + 1) for i in range(len(tipos))]

    return genai.types.Schema(
        type="OBJECT",
        properties={
            "id_documento": genai.types.Schema(type="INTEGER", enum=ids_validos),
            "tipo_documento": genai.types.Schema(type="STRING", enum=tipos),
            "verificacion_identidad": genai.types.Schema(type="STRING", enum=["SI", "NO", "SIN_DATOS"]),
            "verificacion_nombre": genai.types.Schema(type="STRING", enum=["SI", "NO"]),
            "razon_clasificacion": genai.types.Schema(type="STRING"),
            "fiabilidad": genai.types.Schema(type="NUMBER"),
        },
        required=["id_documento", "tipo_documento", "verificacion_identidad", "verificacion_nombre", "razon_clasificacion", "fiabilidad"],
    )


def schema_requisitos(reqs):
    """Schema para el paso 2: exactamente los campos id_requisito del tipo detectado, nada más.

    reqs: lista de {id_requisito, descripcion, output} del tipo.
    Devuelve None si la lista está vacía (tipo sin requisitos → no hay paso 2).
    """
    if not reqs:
        return None
    props = {req["id_requisito"]: genai.types.Schema(type="STRING", nullable=True) for req in reqs}
    return genai.types.Schema(
        type="OBJECT",
        properties=props,
        required=list(props),
    )


def schema_segmentador(ruta_ods, hoja="Hoja 1"):
    """Arma el schema del segmentador: lista de segmentos, cada uno con páginas + clasificación forzada."""

    df = _leer_ods(ruta_ods, hoja)
    tipos = list(df["tipo de documento"].unique())
    ids_validos = [str(i + 1) for i in range(len(tipos))]

    segmento = genai.types.Schema(
        type="OBJECT",
        properties={
            "pagina_inicio": genai.types.Schema(type="INTEGER"),
            "pagina_fin": genai.types.Schema(type="INTEGER"),
            "id_documento": genai.types.Schema(type="INTEGER", enum=ids_validos),
            "tipo_documento": genai.types.Schema(type="STRING", enum=tipos),
        },
        required=["pagina_inicio", "pagina_fin", "id_documento", "tipo_documento"],
    )
    return genai.types.Schema(
        type="OBJECT",
        properties={"segmentos": genai.types.Schema(type="ARRAY", items=segmento)},
        required=["segmentos"],
    )


#--------------------------LLAMADAS A LA IA----------------


@reintentar(max_intentos=MAX_REINTENTOS, base_espera=ESPERA_BASE)
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


@reintentar(max_intentos=MAX_REINTENTOS, base_espera=ESPERA_BASE)
def subir_archivo(ruta):
    """Sube un archivo a la API de Gemini con reintentos automáticos."""
    return CLIENTE.files.upload(file=ruta)


def eliminar_archivo(nombre):
    """Elimina un archivo de la API de Gemini (best-effort, sin reintentos)."""
    try:
        CLIENTE.files.delete(name=nombre)
    except Exception:
        pass


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


def _guardar_json(resultado, datos_sujeto):
    """Guarda el resultado en un JSON con nombre único dentro de la carpeta de salida del sujeto."""

    base_nombre = f"{resultado['id_documento']}_{resultado['tipo_documento']}"
    ruta_json = datos_sujeto["salida"] / f"{base_nombre}.json"
    contador = 1
    while ruta_json.exists():
        ruta_json = datos_sujeto["salida"] / f"{base_nombre}_{contador}.json"
        contador += 1
    ruta_json.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")


def _sumar_tokens(r1, r2):
    """Suma los conteos de tokens de dos respuestas de la IA."""
    return [r1[0], r1[1] + r2[1], r1[2] + r2[2], r1[3] + r2[3], (r1[4] or 0) + (r2[4] or 0)]


def ciclo_archivo(peticion_archivo):
    """Clasifica un archivo suelto en dos pasos:
    1. Clasifica el tipo de documento.
    2. Si el tipo tiene requisitos, evalúa exactamente los de ese tipo (schema a medida).
    """

    ruta_original, datos_sujeto = peticion_archivo
    ruta_temp = duplicar_temporal(ruta_original)

    try:
        archivo_nube = subir_archivo(ruta_temp)
        prompt = f"id: {datos_sujeto['id']}\nsujeto: {datos_sujeto['sujeto']}"

        # Paso 1: clasificar
        respuesta1 = ia_inspector(archivo_nube, prompt, CONTEXTO_VERIFICADOR + ods_string(RUTA_ODS), schema_clasificador(RUTA_ODS), MODELO_LITE)
        resultado = json.loads(respuesta1[0])
        respuesta_final = respuesta1

        # Paso 2: evaluar requisitos propios del tipo detectado
        reqs = reqs_por_tipo(RUTA_ODS, resultado["tipo_documento"])
        if reqs:
            contexto_req = CONTEXTO_REQUISITOS + "\n".join(f"- {r['id_requisito']}: {r['descripcion']} -> formato: {r['output']}" for r in reqs)
            respuesta2 = ia_inspector(archivo_nube, prompt, contexto_req, schema_requisitos(reqs), MODELO_LITE)
            resultado.update(json.loads(respuesta2[0]))
            respuesta_final = _sumar_tokens(respuesta1, respuesta2)

        eliminar_archivo(archivo_nube.name)

        resultado["ruta"] = str(ruta_original)
        _guardar_json(resultado, datos_sujeto)

        return [resultado] + respuesta_final[1:]

    except Exception as e:
        log.error(f"✗ Archivo falló: {ruta_original.name} → {e}")
        return None

    finally:
        ruta_temp.unlink()


def ciclo_archivo2(peticion):
    """Clasifica un trozo de compilado en dos pasos (tipo ya sugerido por el segmentador)."""

    ruta_seg, datos_sujeto, id_sugerido, tipo_sugerido, ruta_compilado_original, rango = peticion

    try:
        archivo_nube = subir_archivo(ruta_seg)
        prompt = f"id: {datos_sujeto['id']}\nsujeto: {datos_sujeto['sujeto']}\ntipo sugerido: {tipo_sugerido}"

        # Paso 1: clasificar (confirmar o corregir el tipo sugerido)
        respuesta1 = ia_inspector(archivo_nube, prompt, CONTEXTO_VERIFICADOR_HEURISTICO + ods_fila_string(RUTA_ODS, id_sugerido), schema_clasificador(RUTA_ODS), MODELO_LITE)
        resultado = json.loads(respuesta1[0])
        respuesta_final = respuesta1

        # Paso 2: evaluar requisitos del tipo efectivo (puede diferir del sugerido si la IA lo corrigió)
        reqs = reqs_por_tipo(RUTA_ODS, resultado["tipo_documento"])
        if reqs:
            contexto_req = CONTEXTO_REQUISITOS + "\n".join(f"- {r['id_requisito']}: {r['descripcion']} -> formato: {r['output']}" for r in reqs)
            respuesta2 = ia_inspector(archivo_nube, prompt, contexto_req, schema_requisitos(reqs), MODELO_LITE)
            resultado.update(json.loads(respuesta2[0]))
            respuesta_final = _sumar_tokens(respuesta1, respuesta2)

        eliminar_archivo(archivo_nube.name)

        resultado["ruta"] = f"{ruta_compilado_original} (páginas {rango})"
        _guardar_json(resultado, datos_sujeto)

        return [resultado] + respuesta_final[1:]

    except Exception as e:
        log.error(f"✗ Segmento falló: {ruta_compilado_original.name} ({rango}) → {e}")
        return None

    finally:
        ruta_seg.unlink()


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
            archivo_nube = subir_archivo(ruta_temp_compilado)
            respuesta_seg = ia_inspector(archivo_nube, "Segmenta este PDF.", contexto, schema, MODELO_FLASH)
            eliminar_archivo(archivo_nube.name)
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
    """Recorre cada carpeta con checkpointing: salta completadas, aísla fallos, registra progreso."""

    global CONTEO_ARCHIVOS, CONTEO_DIR

    estado = EstadoLote(OUTPUT_JSON)

    try:
        for carpeta in lista_carpetas:
            clave = carpeta.name

            # ── Saltar carpetas ya procesadas ──
            if estado.ya_completado(clave):
                log.info(f"⏭ Saltando (ya completado): {clave}")
                continue

            estado.marcar_en_proceso(clave)
            t0 = time.time()

            try:
                CONTEO_DIR += 1
                id_sujeto, sujeto, entidad = obtener_id(carpeta)
                cliente = carpeta.parent.name
                asesor  = carpeta.parent.parent.name
                nombre_contratado = sujeto[len(id_sujeto):].strip() if id_sujeto and sujeto.startswith(id_sujeto) else sujeto
                if not nombre_contratado:
                    nombre_contratado = sujeto

                carpeta_salida = OUTPUT_JSON / id_sujeto
                carpeta_salida.mkdir(parents=True, exist_ok=True)

                datos = {
                    "id": id_sujeto,
                    "sujeto": sujeto,
                    "nombre_contratado": nombre_contratado,
                    "entidad": entidad,
                    "cliente": cliente,
                    "asesor": asesor,
                    "carpeta": carpeta,
                    "salida": carpeta_salida,
                }

                desbloquear_pdfs(carpeta, clave=id_sujeto)
                ruta_archivos = get_archivos(carpeta, FORMATOS)
                CONTEO_ARCHIVOS += len(ruta_archivos)

                log.info(f"▶ [{CONTEO_DIR}/{len(lista_carpetas)}] {clave} ({len(ruta_archivos)} archivos)")

                # --- primera pasada ---
                peticion_primera = [(ruta, datos) for ruta in ruta_archivos]
                respuestas_raw = POOL.map(ciclo_archivo, peticion_primera)
                archivos_fallidos = sum(1 for r in respuestas_raw if r is None)
                respuestas = [r for r in respuestas_raw if r is not None]

                # --- segunda pasada (compilados) ---
                peticion_segunda, respuestas_seg = procesar_compilado(respuestas, datos)
                if peticion_segunda:
                    respuestas_comp = POOL.map(ciclo_archivo2, peticion_segunda)
                    archivos_fallidos += sum(1 for r in respuestas_comp if r is None)
                    respuestas += [r for r in respuestas_comp if r is not None]

                contar_tokens(respuestas + respuestas_seg)

                # --- JSON ecuménico de la carpeta ---
                ecumenico = {
                    "numero_de_identidad_del_contratado": datos["id"],
                    "nombre_del_contratado":               datos["nombre_contratado"],
                    "ruta_carpeta":                        str(datos["carpeta"]),
                    "cliente":                             datos["cliente"],
                    "asesor":                              datos["asesor"],
                }
                (carpeta_salida / "0_ecumenico.json").write_text(
                    json.dumps(ecumenico, ensure_ascii=False, indent=2), encoding="utf-8"
                )

                if archivos_fallidos:
                    log.warning(f"⚠ {clave}: {archivos_fallidos} archivo(s) fallaron")

                estado.marcar_completado(clave, archivos=len(ruta_archivos) - archivos_fallidos)
                log.debug(f"  Tiempo: {time.time() - t0:.1f}s")

            except KeyboardInterrupt:
                estado.marcar_fallido(clave, "Interrumpido por el usuario")
                log.warning(f"⚠ Interrumpido durante: {clave}")
                raise

            except Exception as e:
                estado.marcar_fallido(clave, e)
                log.error(f"✗ Carpeta falló: {clave} → {e}", exc_info=True)
                continue

    finally:
        POOL.close()
        POOL.join()

    # ── Resumen final ──
    completados, fallidos, total = estado.resumen()
    log.info(f"═══ Lote finalizado: {completados} completados, {fallidos} fallidos, {total} total ═══")
    if fallidos:
        log.warning(f"Carpetas fallidas: {estado.listar_fallidos()}")


#--------------------------EJECUCIÓN----------------

MODO = sys.argv[1].lower() if len(sys.argv) > 1 else "prueba"

if MODO in ("--help", "-h", "help", "ayuda"):
    print("""
Uso: python script_v2.py [MODO]

Modos disponibles:
  prueba     - Ejecuta el proceso en la carpeta de pruebas configurada (RUTA_PRUEBA). (Por defecto)
  lote       - Procesa todas las carpetas dentro de RUTA_PADRE con checkpointing (salta las ya completadas).
  reintentar - Limpia el estado de las carpetas marcadas como FALLIDO en el lote y reejecuta el lote.

Ejemplos:
  python script_v2.py prueba
  python script_v2.py lote
  python script_v2.py reintentar
""")
    sys.exit(0)

if MODO == "reintentar":
    log.info("♻ Limpiando carpetas fallidas para reprocesamiento…")
    _estado_tmp = EstadoLote(OUTPUT_JSON)
    _estado_tmp.limpiar_fallidos()
    MODO = "lote"

if MODO == "lote":
    log.info(f"═══ Inicio lote completo: {RUTA_PADRE} ═══")
    carpetas = []
    buscar_dir(RUTA_PADRE, carpetas)
    log.info(f"Carpetas encontradas: {len(carpetas)}")
    operacion_dir(carpetas)
else:
    log.info(f"═══ Modo prueba: {RUTA_PRUEBA} ═══")
    operacion_dir([RUTA_PRUEBA])

log.info(f"cantidad carpetas  : {CONTEO_DIR}")
log.info(f"cantidad archivos  : {CONTEO_ARCHIVOS}")
log.info(f"total tokens input : {CONTEO_TOKENS_IN}")
log.info(f"total tokens output: {CONTEO_TOKENS_OUT}")
log.info(f"total tokens total : {CONTEO_TOKENS_ALL}")

