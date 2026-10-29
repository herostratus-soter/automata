import os
import json
import pandas as pd
from pathlib import Path
from multiprocessing.dummy import Pool as ThreadPool

from config import RUTA_ODS, RUTA_SALIDA_JSON, RUTA_SALIDA_EXCEL, ANIO, MES, HILOS
from logs import EstadoLote, EstadoCarpeta


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


#--------------------------LECTURA EN UNA SOLA PASADA (OPTIMIZADA)----------------


def leer_carpeta_contratado(carpeta_contratado):
    """Lee todos los JSONs de una carpeta en una sola pasada de disco usando os.scandir.

    Retorna: (por_tipo_dict, eco_dict, errores_detalle, cant_jsons)
      errores_detalle: lista de {"archivo": str, "error": str}
    """

    por_tipo = {}
    eco_dict = {}
    errores_detalle = []
    cant_jsons = 0

    try:
        with os.scandir(carpeta_contratado) as it:
            archivos_ordenados = sorted(it, key=lambda e: e.name)
            for entry in archivos_ordenados:
                if not entry.name.endswith(".json") or entry.name.startswith("_"):
                    continue

                if entry.name == "0_ecumenico.json":
                    try:
                        with open(entry.path, encoding="utf-8") as f:
                            eco_dict = json.load(f)
                    except Exception as e:
                        errores_detalle.append({
                            "archivo": entry.name,
                            "error": f"Ecuménico ilegible: {e}",
                        })
                else:
                    try:
                        with open(entry.path, encoding="utf-8") as f:
                            datos = json.load(f)
                        tipo = datos.get("tipo_documento")
                        if tipo:
                            por_tipo.setdefault(tipo, []).append(datos)
                            cant_jsons += 1
                        else:
                            errores_detalle.append({
                                "archivo": entry.name,
                                "error": "JSON sin campo 'tipo_documento'",
                            })
                    except Exception as e:
                        errores_detalle.append({
                            "archivo": entry.name,
                            "error": f"JSON corrupto: {e}",
                        })
    except Exception as e:
        errores_detalle.append({
            "archivo": str(carpeta_contratado.name),
            "error": f"Error leyendo carpeta: {e}",
        })

    return por_tipo, eco_dict, errores_detalle, cant_jsons


def elegir_mejor(lista_jsons):
    """Cuando hay varios documentos del mismo tipo, elige el de mayor fiabilidad.

    La IA reporta un número de 0.0 a 1.0 en el campo 'fiabilidad'.
    Si empatan, se queda con el primero de la lista.
    """
    return max(lista_jsons, key=lambda doc: doc.get("fiabilidad", 0.0))


def extraer_info_contratado(por_tipo, carpeta_name):
    """Fallback: extrae id y nombre si no hay 0_ecumenico.json."""

    id_sujeto = carpeta_name[:len(carpeta_name) - len(carpeta_name.lstrip("0123456789"))]
    nombre_contratado = carpeta_name[len(id_sujeto):].strip() if id_sujeto and carpeta_name.startswith(id_sujeto) else carpeta_name
    if not nombre_contratado:
        nombre_contratado = carpeta_name
    return id_sujeto, nombre_contratado


def construir_fila(id_contratado, carpeta_contratado, por_tipo, eco_dict, catalogo, columnas):
    """Arma una fila del Excel para un contratado sin hacer llamadas adicionales a disco."""

    num_id = eco_dict.get("numero_de_identidad_del_contratado") or eco_dict.get("id") or id_contratado
    nom_contratado = eco_dict.get("nombre_del_contratado")

    if not nom_contratado or not num_id:
        fb_id, fb_nom = extraer_info_contratado(por_tipo, Path(carpeta_contratado).name)
        if not num_id:
            num_id = fb_id or id_contratado
        if not nom_contratado:
            nom_contratado = fb_nom

    fila = {col: None for col in columnas}
    fila["numero de identidad del contratado"] = num_id
    fila["nombre del contratado"]               = nom_contratado
    fila["ruta_carpeta"]                        = eco_dict.get("ruta_carpeta", "")
    fila["cliente"]                             = eco_dict.get("cliente", "")
    fila["asesor"]                              = eco_dict.get("asesor", "")

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


def _procesar_una_carpeta(args):
    """Procesa una carpeta de forma aislada (ejecutado en paralelo en el ThreadPool).

    Detecta errores y documentos faltantes para reportar a los checklists.
    """
    carpeta, catalogo, columnas = args
    por_tipo, eco_dict, errores_detalle, cant_jsons = leer_carpeta_contratado(carpeta)

    if not por_tipo and not eco_dict:
        return None

    fila = construir_fila(carpeta.name, carpeta, por_tipo, eco_dict, catalogo, columnas)

    # Detectar documentos faltantes del catálogo
    docs_faltantes = []
    for id_doc in sorted(catalogo):
        tipo = catalogo[id_doc]["documento"]
        if tipo not in por_tipo:
            docs_faltantes.append(tipo)

    return {
        "clave": carpeta.name,
        "carpeta": carpeta,
        "fila": fila,
        "errores_detalle": errores_detalle,
        "docs_faltantes": docs_faltantes,
        "cant_jsons": cant_jsons,
    }


#--------------------------ORQUESTACIÓN----------------


def consolidar():
    """Lee JSONs de salida, construye el Excel y reporta errores a los checklists.

    Flujo:
      1. Lee catálogo de documentos (reglas_v2.ods)
      2. Escanea carpetas de salida en paralelo
      3. Construye fila del Excel para cada contratado
      4. Detecta errores: JSONs corruptos, documentos faltantes
      5. Reporta errores a estado_lote.json Y _estado_carpeta.json
      6. Genera/actualiza el Excel consolidado
    """

    print("==================================================")
    print(" CONSOLIDADOR DE EXCEL - AUTOMATA")
    print("==================================================")

    estado_lote = EstadoLote(RUTA_SALIDA_JSON)

    print(f"[INFO] Leyendo catalogo desde: {RUTA_ODS.name}")
    catalogo = leer_catalogo(RUTA_ODS)
    columnas = construir_columnas(catalogo)
    leyenda  = construir_leyenda(catalogo)
    tipos_catalogo = {catalogo[i]["documento"] for i in catalogo}

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

    num_hilos = min(HILOS, 16) if (HILOS and HILOS > 0) else 10
    print(f"[INFO] Carpetas encontradas para consolidar: {total_carpetas} (procesando con {num_hilos} hilos)")
    print("--------------------------------------------------")

    pool = ThreadPool(num_hilos)
    tareas = [(c, catalogo, columnas) for c in carpetas_salida]

    # Estadísticas de la consolidación
    procesadas = 0
    carpetas_con_errores = 0
    total_jsons_corruptos = 0
    total_docs_faltantes = 0
    reportes_detalle = []  # para escribir al final fuera del pool

    for res in pool.imap_unordered(_procesar_una_carpeta, tareas):
        if res is None:
            continue

        procesadas += 1
        errores = res["errores_detalle"]
        faltantes = res["docs_faltantes"]
        tiene_problemas = bool(errores) or bool(faltantes)

        if tiene_problemas:
            carpetas_con_errores += 1

        if errores:
            total_jsons_corruptos += len(errores)

        if faltantes:
            total_docs_faltantes += len(faltantes)

        # Guardar para reportar después (fuera del pool, thread-safe)
        if tiene_problemas:
            reportes_detalle.append({
                "clave": res["clave"],
                "carpeta": res["carpeta"],
                "errores": errores,
                "faltantes": faltantes,
            })

        fila = res["fila"]
        id_key = str(fila["numero de identidad del contratado"])
        filas_existentes[id_key] = fila
        print(f"[PROCESANDO] [{procesadas}/{total_carpetas}] {res['clave']} ({res['cant_jsons']} JSONs)")

    pool.close()
    pool.join()

    # ── Reportar errores a los checklists (thread-safe, después del pool) ──
    if reportes_detalle:
        print(f"\n[INFO] Reportando errores de {len(reportes_detalle)} carpetas a los checklists...")

    for reporte in reportes_detalle:
        clave = reporte["clave"]
        carpeta = reporte["carpeta"]
        errores = reporte["errores"]
        faltantes = reporte["faltantes"]

        # ── Reportar a _estado_carpeta.json (checklist interno) ──
        ec = EstadoCarpeta(carpeta)
        if errores:
            for err in errores:
                ec.actualizar_archivo(
                    err["archivo"],
                    error_constructor=err["error"],
                )
        if faltantes:
            ec.actualizar_archivo(
                "_docs_faltantes",
                documentos_faltantes=faltantes,
                nota="Documentos del catálogo no encontrados en los JSONs de salida",
            )
        ec.guardar()

        # ── Reportar a estado_lote.json (checklist global) ──
        partes_motivo = []
        if errores:
            partes_motivo.append(f"{len(errores)} JSON(s) con error")
        if faltantes:
            partes_motivo.append(f"{len(faltantes)} documento(s) faltante(s)")
        motivo = "Constructor: " + ", ".join(partes_motivo)

        # Solo degradar el estado, nunca mejorar (si ya está COMPLETADO, lo dejamos)
        estado_actual = estado_lote.datos.get(clave, {}).get("estado", "")
        if estado_actual not in ("COMPLETADO", "APROBADO"):
            detalle = []
            for err in errores[:5]:
                detalle.append(err)
            for falt in faltantes[:5]:
                detalle.append({"archivo": falt, "error": "Documento no encontrado"})
            estado_lote.marcar_parcial(
                clave, motivo, carpeta,
                archivos_ok=0,
                archivos_fallidos=len(errores) + len(faltantes),
                detalle_fallos=detalle,
            )

    # Reconstruir DataFrame respetando el orden de columnas actual
    todas = list(filas_existentes.values())
    df = pd.DataFrame(todas, columns=columnas)

    # Convertir a numérico si los IDs son enteros pura cifra
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

    # ── Resumen final ──
    print("==================================================")
    print(f"  RESUMEN DE CONSOLIDACIÓN")
    print("==================================================")
    print(f"  Contratados en el Excel:         {len(todas)}")
    print(f"  Columnas generadas:              {len(columnas)}")
    print(f"  Tipos de documento en catálogo:   {len(tipos_catalogo)}")
    print("--------------------------------------------------")
    if carpetas_con_errores:
        print(f"  ⚠ Carpetas con problemas:       {carpetas_con_errores}")
        print(f"    → JSONs corruptos/inválidos:   {total_jsons_corruptos}")
        print(f"    → Documentos faltantes:        {total_docs_faltantes}")
        print(f"  (Errores reportados a estado_lote.json y _estado_carpeta.json)")
    else:
        print(f"  ✅ Sin errores detectados")
    print("==================================================")


#--------------------------EJECUCIÓN----------------

if __name__ == "__main__":
    consolidar()

