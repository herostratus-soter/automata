"""
constructor.py — Lee los JSONs de salida y construye el Excel de contratación.

Flujo:
  1. Lee reglas_v2.ods para saber qué tipos de documento existen y qué requerimientos tiene cada uno.
  2. Arma las columnas del Excel: para cada tipo → existe, identidad, nombre, req1..reqN.
  3. Recorre tmp/ — cada subcarpeta es un contratado (su cédula).
  4. Dentro de cada subcarpeta, lee todos los JSONs y los agrupa por tipo de documento.
  5. Si hay duplicados del mismo tipo, elige el más fiable (identidad + nombre coinciden).
  6. Arma una fila por contratado y guarda el Excel.

El Excel tiene dos hojas:
  • "contratados" — la tabla principal (filas = contratados, columnas = requerimientos).
  • "leyenda"     — qué significa cada columna req1, req2... de cada tipo de documento.
"""

import json
import pandas as pd
from pathlib import Path

from config import RUTA_ODS, RUTA_SALIDA_JSON, RUTA_SALIDA_EXCEL, ANIO, MES


#--------------------------CONFIGURACIÓN----------------

NOMBRE_EXCEL = f"{ANIO}_{MES}_contratacion_automata.xlsx"
RUTA_EXCEL   = RUTA_SALIDA_EXCEL / NOMBRE_EXCEL


#--------------------------LECTURA DEL CATÁLOGO----------------


def leer_catalogo(ruta_ods, hoja="Hoja 1"):
    """Lee reglas_v2.ods y devuelve un diccionario ordenado por id.

    Estructura:
        { 1: { "documento": "documento_id", "reqs": [ {"id_requisito": "documento_id_tipo", "requisito": "...", "output": "..."}, ... ] },
          ... }
    """

    df = pd.read_excel(ruta_ods, engine="odf", sheet_name=hoja)
    catalogo = {}
    for i, (tipo_doc, grupo) in enumerate(df.groupby("tipo de documento", sort=False), 1):
        primera = grupo.iloc[0]
        reqs = []
        for _, fila in grupo.dropna(subset=["descripcion requisito"]).iterrows():
            reqs.append({
                "id_requisito": fila["id_requisito"],
                "requisito": fila["descripcion requisito"],
                "output": fila["output"]
            })
        catalogo[i] = {"documento": tipo_doc, "reqs": reqs}
    return catalogo


def construir_columnas(catalogo):
    """Arma la lista ordenada de columnas del Excel.

    Orden por cada tipo de documento:
        {tipo}_existe       → ¿se encontró al menos un documento de este tipo?
        {tipo}_numeroid     → verificación ecuménica: ¿la cédula del documento coincide?
        {tipo}_nombre       → verificación ecumenica: ¿el nombre coincide?
        {id_requisito}...   → requerimientos específicos identificados por su slug único
    """

    columnas = ["id", "sujeto", "entidad"]
    for id_doc in sorted(catalogo):
        tipo = catalogo[id_doc]["documento"]
        columnas.append(f"{tipo}_existe")
        columnas.append(f"{tipo}_numeroid")
        columnas.append(f"{tipo}_nombre")
        for req in catalogo[id_doc]["reqs"]:
            columnas.append(req["id_requisito"])
    return columnas


def construir_leyenda(catalogo):
    """Arma la hoja 'leyenda': explica qué significa cada columna de requisito."""

    filas = []
    for id_doc in sorted(catalogo):
        tipo = catalogo[id_doc]["documento"]
        for req in catalogo[id_doc]["reqs"]:
            filas.append({
                "columna_excel":    req["id_requisito"],
                "tipo_documento":   tipo,
                "requisito":        req["requisito"],
                "formato_esperado": req["output"],
            })
    return pd.DataFrame(filas)


#--------------------------LECTURA DE RESULTADOS (JSONs)----------------


def leer_jsons_contratado(carpeta_contratado):
    """Lee todos los JSONs de un contratado y los agrupa por tipo de documento.

    Retorna: { "documento_id": [json1], "referencia_laboral": [json1, json2], ... }
    """

    por_tipo = {}
    for archivo in sorted(Path(carpeta_contratado).glob("*.json")):
        with open(archivo, encoding="utf-8") as f:
            datos = json.load(f)
        tipo = datos["tipo_documento"]
        por_tipo.setdefault(tipo, []).append(datos)
    return por_tipo


def elegir_mejor(lista_jsons):
    """Cuando hay varios documentos del mismo tipo, elige el de mayor fiabilidad.

    La IA reporta un número de 0.0 a 1.0 en el campo 'fiabilidad'.
    Si empatan, se queda con el primero de la lista.
    """
    return max(lista_jsons, key=lambda doc: doc.get("fiabilidad", 0.0))


#--------------------------CONSTRUCCIÓN DEL EXCEL----------------


def extraer_info_contratado(por_tipo):
    """Extrae sujeto y entidad de la ruta del primer JSON disponible."""

    for jsons in por_tipo.values():
        ruta_texto = jsons[0].get("ruta", "")
        ruta_limpia = ruta_texto.split(" (páginas")[0]
        ruta = Path(ruta_limpia)
        sujeto  = ruta.parent.name
        entidad = ruta.parent.parent.name
        return sujeto, entidad
    return "", ""


def construir_fila(id_contratado, por_tipo, catalogo, columnas):
    """Arma una fila del Excel para un contratado.

    Los JSONs son planos: cada id_requisito es un campo al mismo nivel que tipo_documento.
    El catálogo dice qué id_requisitos tiene cada tipo → simplemente se leen del JSON.
    """

    sujeto, entidad = extraer_info_contratado(por_tipo)
    fila = {col: None for col in columnas}
    fila["id"]      = id_contratado
    fila["sujeto"]  = sujeto
    fila["entidad"] = entidad

    for id_doc in sorted(catalogo):
        tipo = catalogo[id_doc]["documento"]

        if tipo in por_tipo:
            mejor = elegir_mejor(por_tipo[tipo])
            fila[f"{tipo}_existe"]    = "SI"
            fila[f"{tipo}_numeroid"] = mejor.get("verificacion_identidad")
            fila[f"{tipo}_nombre"]    = mejor.get("verificacion_nombre")

            # leer cada id_requisito directamente del JSON plano
            for req in catalogo[id_doc]["reqs"]:
                fila[req["id_requisito"]] = mejor.get(req["id_requisito"])
        else:
            fila[f"{tipo}_existe"] = "NO"

    return fila


#--------------------------ORQUESTACIÓN----------------


def consolidar():
    """Lee todos los JSONs de tmp/, arma el DataFrame y guarda el Excel."""

    catalogo = leer_catalogo(RUTA_ODS)
    columnas = construir_columnas(catalogo)

    filas = []
    for carpeta in sorted(RUTA_SALIDA_JSON.iterdir()):
        if not carpeta.is_dir():
            continue
        por_tipo = leer_jsons_contratado(carpeta)
        if not por_tipo:
            continue  # carpeta vacía, la salta
        fila = construir_fila(carpeta.name, por_tipo, catalogo, columnas)
        filas.append(fila)

    df = pd.DataFrame(filas, columns=columnas)
    leyenda = construir_leyenda(catalogo)

    with pd.ExcelWriter(RUTA_EXCEL, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="contratados", index=False)
        leyenda.to_excel(writer, sheet_name="leyenda", index=False)

    print(f"✓ Excel generado: {RUTA_EXCEL}")
    print(f"  {len(filas)} contratados")
    print(f"  {len(columnas)} columnas")
    print(f"  Hoja 'leyenda' con {len(leyenda)} requerimientos documentados")


#--------------------------EJECUCIÓN----------------

consolidar()
