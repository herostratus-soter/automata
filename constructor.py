"""
constructor.py — Lee los JSONs de salida y construye/actualiza el Excel de contratación.

Flujo:
  1. Lee reglas_v2.ods para saber qué tipos existen y qué requerimientos tiene cada uno.
  2. Arma las columnas del Excel (primeras columnas son la extracción ecuménica).
  3. Si el Excel ya existe, carga las filas previas — no sobreescribe registros no procesados.
  4. Por cada subcarpeta en tmp/, lee 0_ecumenico.json + JSONs de documentos.
  5. Actualiza o inserta la fila del contratado (clave: numero de identidad del contratado).
  6. Guarda el Excel con la hoja principal más la leyenda.
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

    Primeras columnas: ecuménico de la carpeta/contratado.
    Luego: columnas de cada tipo de documento.
    """

    columnas = [
        "numero de identidad del contratado",
        "nombre del contratado",
        "ruta_carpeta",
        "cliente",
        "asesor",
    ]
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


from logs import EstadoLote


#--------------------------LECTURA DE RESULTADOS (JSONs)----------------


def leer_jsons_contratado(carpeta_contratado):
    """Lee todos los JSONs de un contratado y los agrupa por tipo de documento.

    Retorna: (por_tipo_dict, conteo_corruptos)
    """

    por_tipo = {}
    corruptos = 0
    for archivo in sorted(Path(carpeta_contratado).glob("*.json")):
        if archivo.name.startswith("_") or archivo.name.startswith("0_"):
            continue  # saltar 0_ecumenico.json y similares
        try:
            with open(archivo, encoding="utf-8") as f:
                datos = json.load(f)
            tipo = datos.get("tipo_documento")
            if tipo:
                por_tipo.setdefault(tipo, []).append(datos)
        except Exception as e:
            corruptos += 1
            print(f"[ADVERTENCIA] JSON corrupto o ilegible en {archivo.name} ({carpeta_contratado.name}): {e}")
            continue
    return por_tipo, corruptos


def elegir_mejor(lista_jsons):
    """Cuando hay varios documentos del mismo tipo, elige el de mayor fiabilidad.

    La IA reporta un número de 0.0 a 1.0 en el campo 'fiabilidad'.
    Si empatan, se queda con el primero de la lista.
    """
    return max(lista_jsons, key=lambda doc: doc.get("fiabilidad", 0.0))


#--------------------------CONSTRUCCIÓN DEL EXCEL----------------


def leer_ecumenico(carpeta_contratado):
    """Lee 0_ecumenico.json de la carpeta del contratado. Devuelve {} si no existe o está dañado."""
    ruta = Path(carpeta_contratado) / "0_ecumenico.json"
    if not ruta.exists():
        return {}
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def extraer_info_contratado(por_tipo, carpeta_name):
    """Fallback: extrae id y nombre si no hay 0_ecumenico.json."""

    id_sujeto = carpeta_name[:len(carpeta_name) - len(carpeta_name.lstrip("0123456789"))]
    nombre_contratado = carpeta_name[len(id_sujeto):].strip() if id_sujeto and carpeta_name.startswith(id_sujeto) else carpeta_name
    if not nombre_contratado:
        nombre_contratado = carpeta_name
    return id_sujeto, nombre_contratado


def construir_fila(id_contratado, carpeta_contratado, por_tipo, catalogo, columnas):
    """Arma una fila del Excel para un contratado.

    Los JSONs son planos: cada id_requisito es un campo al mismo nivel que tipo_documento.
    El catálogo dice qué id_requisitos tiene cada tipo -> simplemente se leen del JSON.
    """

    eco = leer_ecumenico(carpeta_contratado)

    num_id = eco.get("numero_de_identidad_del_contratado") or eco.get("id") or id_contratado
    nom_contratado = eco.get("nombre_del_contratado")

    if not nom_contratado or not num_id:
        fb_id, fb_nom = extraer_info_contratado(por_tipo, Path(carpeta_contratado).name)
        if not num_id:
            num_id = fb_id or id_contratado
        if not nom_contratado:
            nom_contratado = fb_nom

    fila = {col: None for col in columnas}
    fila["numero de identidad del contratado"] = num_id
    fila["nombre del contratado"]               = nom_contratado
    fila["ruta_carpeta"]                        = eco.get("ruta_carpeta", "")
    fila["cliente"]                             = eco.get("cliente", "")
    fila["asesor"]                              = eco.get("asesor", "")

    for id_doc in sorted(catalogo):
        tipo = catalogo[id_doc]["documento"]

        if tipo in por_tipo:
            mejor = elegir_mejor(por_tipo[tipo])
            fila[f"{tipo}_existe"]   = "SI"
            fila[f"{tipo}_numeroid"] = mejor.get("verificacion_identidad")
            fila[f"{tipo}_nombre"]   = mejor.get("verificacion_nombre")

            # leer cada id_requisito directamente del JSON plano
            for req in catalogo[id_doc]["reqs"]:
                fila[req["id_requisito"]] = mejor.get(req["id_requisito"])
        else:
            fila[f"{tipo}_existe"] = "NO"

    return fila


#--------------------------ORQUESTACIÓN----------------


def consolidar():
    """Lee JSONs de tmp/, actualiza/inserta filas en el Excel sin borrar las previas."""

    print("==================================================")
    print(" CONSOLIDADOR DE EXCEL - AUTOMATA")
    print("==================================================")

    estado_lote = EstadoLote(RUTA_SALIDA_JSON)

    print(f"[INFO] Leyendo catalogo desde: {RUTA_ODS.name}")
    catalogo = leer_catalogo(RUTA_ODS)
    columnas = construir_columnas(catalogo)
    leyenda  = construir_leyenda(catalogo)

    # Cargar filas existentes del Excel si ya existe (modo append/update)
    filas_existentes = {}  # { num_id: fila_dict }
    col_id = "numero de identidad del contratado"
    if RUTA_EXCEL.exists():
        print(f"[INFO] Cargando Excel anterior: {RUTA_EXCEL.name}")
        df_prev = pd.read_excel(RUTA_EXCEL, sheet_name="contratados", dtype=str)
        key_col = col_id if col_id in df_prev.columns else ("id" if "id" in df_prev.columns else df_prev.columns[0])
        for _, row in df_prev.iterrows():
            key = str(row[key_col])
            filas_existentes[key] = row.to_dict()

    print(f"[INFO] Escaneando carpetas de salida en: {RUTA_SALIDA_JSON}")
    carpetas_salida = [c for c in sorted(RUTA_SALIDA_JSON.iterdir()) if c.is_dir()]
    total_carpetas = len(carpetas_salida)

    print(f"[INFO] Carpetas encontradas para consolidar: {total_carpetas}")
    print("--------------------------------------------------")

    for i, carpeta in enumerate(carpetas_salida, 1):
        por_tipo, corruptos = leer_jsons_contratado(carpeta)
        eco_existe = (carpeta / "0_ecumenico.json").exists()
        
        # Conteo de JSONs de documentos (sin contar el ecuménico)
        cant_jsons = sum(len(v) for v in por_tipo.values())
        
        if corruptos > 0:
            estado_lote.marcar_defectuoso(
                carpeta.name,
                f"JSON corrupto o ilegible detectado en constructor ({corruptos} error/es)",
                carpeta
            )

        if not por_tipo and not eco_existe:
            print(f"[SALTAR] [{i}/{total_carpetas}] {carpeta.name} -> Vacia (0 JSONs), saltando.")
            continue
        
        print(f"[PROCESANDO] [{i}/{total_carpetas}] {carpeta.name} ({cant_jsons} JSONs de documentos)")

        fila = construir_fila(carpeta.name, carpeta, por_tipo, catalogo, columnas)
        id_key = str(fila["numero de identidad del contratado"])
        filas_existentes[id_key] = fila  # sobreescribe o añade este contratado


    # Reconstruir DataFrame respetando el orden de columnas actual
    todas = list(filas_existentes.values())
    df = pd.DataFrame(todas, columns=columnas)

    # Convertir a numérico si los IDs son enteros pura cifra (elimina la comilla "'" en Excel)
    if col_id in df.columns:
        s = df[col_id].astype(str)
        es_num = s.str.isdigit()
        no_cero_inicial = ~s.str.startswith("0") | (s == "0")
        if (es_num & no_cero_inicial).all():
            df[col_id] = pd.to_numeric(df[col_id], errors="coerce").astype("Int64")

    print("--------------------------------------------------")
    print(f"[INFO] Guardando Excel final en: {RUTA_EXCEL}")
    with pd.ExcelWriter(RUTA_EXCEL, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="contratados", index=False)
        leyenda.to_excel(writer, sheet_name="leyenda", index=False)

    print("==================================================")
    print(f"[OK] Excel actualizado exitosamente!")
    print(f"  - Total contratados en Excel: {len(todas)}")
    print(f"  - Total columnas generadas : {len(columnas)}")
    print("==================================================")



#--------------------------EJECUCIÓN----------------

if __name__ == "__main__":
    consolidar()

