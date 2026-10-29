#!/usr/bin/env python3
"""
inventario.py — Inventario y migración de JSONs existentes.

Escanea todas las carpetas de salida, valida los JSONs generados
por ejecuciones anteriores, crea _estado_carpeta.json (checklist
interno) para cada carpeta, y corrige estado_lote.json (checklist
global) basándose en lo que realmente existe en disco.

╔══════════════════════════════════════════════════════╗
║  NO usa la API de Gemini.  NO gasta tokens.         ║
║  Se ejecuta UNA SOLA VEZ antes de:                  ║
║    python script.py reintentar                      ║
╚══════════════════════════════════════════════════════╝

Uso:
    python inventario.py
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

from config import RUTA_PADRE, RUTA_SALIDA_JSON, FORMATOS
from logs import EstadoLote, EstadoCarpeta


# ════════════════════════════════════════════════════════
# Funciones copiadas de script.py (no se importa script.py
# porque tiene código top-level que ejecuta el procesamiento)
# ════════════════════════════════════════════════════════


def patron(directorio):
    """True si el nombre empieza con 6+ dígitos (cédula)."""
    nombre = directorio.name
    return len(nombre) >= 6 and nombre[:6].isdigit()


def buscar_dir(directorio, lista):
    """Busca recursivamente carpetas que cumplen el patrón."""
    for elem in Path(directorio).iterdir():
        if elem.is_dir():
            if patron(elem):
                lista.append(elem.resolve())
            buscar_dir(elem, lista)


def get_archivos(directorio, formatos):
    """Lista archivos de formato válido."""
    return [
        elem.resolve()
        for elem in Path(directorio).iterdir()
        if elem.is_file() and elem.suffix.lower() in formatos
    ]


def obtener_id(directorio):
    """Extrae el ID numérico del nombre de la carpeta."""
    sujeto = Path(directorio).name
    id_sujeto = sujeto[:len(sujeto) - len(sujeto.lstrip("0123456789"))]
    return id_sujeto, sujeto


# ════════════════════════════════════════════════════════
# Validación de JSONs
# ════════════════════════════════════════════════════════


CAMPOS_REQUERIDOS = {"tipo_documento", "ruta"}


def validar_json(ruta_json):
    """Valida estructura de un JSON de salida.

    Retorna (contenido_dict, lista_errores).
    Si lista_errores está vacía, el JSON es válido.
    """
    errores = []
    try:
        with open(ruta_json, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"JSON inválido: {e}"]
    except Exception as e:
        return None, [f"No se pudo leer: {e}"]

    if not isinstance(data, dict):
        return None, ["JSON no es un diccionario"]

    for campo in CAMPOS_REQUERIDOS:
        if campo not in data:
            errores.append(f"Falta campo '{campo}'")

    if "fiabilidad" in data:
        try:
            f = float(data["fiabilidad"])
            if not (0 <= f <= 1):
                errores.append(f"Fiabilidad fuera de rango: {f}")
        except (ValueError, TypeError):
            errores.append(f"Fiabilidad no numérica: {data['fiabilidad']}")

    return data, errores


def es_segmento(ruta_en_json):
    """True si la ruta indica un segmento extraído de un compilado."""
    return "páginas" in ruta_en_json or "paginas" in ruta_en_json


# ════════════════════════════════════════════════════════
# Lógica principal
# ════════════════════════════════════════════════════════


def inventariar_carpeta(carpeta_salida, archivos_entrada):
    """Escanea una carpeta de salida y crea/actualiza su _estado_carpeta.json.

    Retorna dict con estadísticas:
      {migrados, jsons_total, jsons_invalidos, clasificados, compilados,
       compilados_segmentados, compilados_pendientes, archivos_faltantes}
    """
    stats = {
        "migrados": 0,
        "jsons_total": 0,
        "jsons_invalidos": 0,
        "jsons_invalidos_detalle": [],
        "clasificados": 0,
        "compilados": 0,
        "compilados_segmentados": 0,
        "compilados_pendientes": 0,
        "archivos_faltantes": 0,
        "segmentos_total": 0,
    }

    ec = EstadoCarpeta(carpeta_salida)

    # Si ya tiene _estado_carpeta.json, no migrar
    if ec.ruta.exists():
        return None  # señal de "ya existía"

    nombres_entrada = {a.name for a in archivos_entrada}
    compilados_con_segmentos = set()
    archivos_clasificados = {}  # nombre → mejor resultado (mayor fiabilidad)

    # Leer todos los JSONs de salida
    jsons = sorted(carpeta_salida.glob("*.json"))
    jsons_reales = [j for j in jsons if not j.name.startswith(("0_", "_"))]
    stats["jsons_total"] = len(jsons_reales)

    for json_path in jsons_reales:
        data, errores = validar_json(json_path)

        if errores:
            stats["jsons_invalidos"] += 1
            stats["jsons_invalidos_detalle"].append({
                "archivo": json_path.name,
                "errores": errores,
            })
            continue

        ruta_json = data.get("ruta", "")
        tipo_doc = data.get("tipo_documento", "")
        fiabilidad = data.get("fiabilidad", 0)

        # ¿Es un segmento de compilado?
        if es_segmento(ruta_json):
            ruta_comp = ruta_json.split(" (páginas")[0].split(" (paginas")[0]
            compilados_con_segmentos.add(Path(ruta_comp).name)
            stats["segmentos_total"] += 1
            continue

        # Clasificación de archivo original
        nombre = Path(ruta_json).name
        if nombre in nombres_entrada:
            # Quedarse con el de mayor fiabilidad si hay duplicados
            existente = archivos_clasificados.get(nombre)
            if not existente or fiabilidad > existente.get("fiabilidad", 0):
                archivos_clasificados[nombre] = {
                    "tipo_documento": tipo_doc,
                    "fiabilidad": fiabilidad,
                    "ruta": ruta_json,
                }

    # Registrar en el checklist interno
    for nombre, info in archivos_clasificados.items():
        ec.actualizar_archivo(
            nombre,
            estado="COMPLETADO",
            tipo_documento=info["tipo_documento"],
            fiabilidad=info["fiabilidad"],
            ruta=info["ruta"],
            migrado=True,
        )
        stats["clasificados"] += 1

        if info["tipo_documento"] == "compilado":
            stats["compilados"] += 1
            if nombre in compilados_con_segmentos:
                ec.datos["archivos"][nombre]["segmentacion"] = "COMPLETADO"
                stats["compilados_segmentados"] += 1
            else:
                ec.datos["archivos"][nombre]["segmentacion"] = "FALLIDO"
                stats["compilados_pendientes"] += 1

    stats["archivos_faltantes"] = len(archivos_entrada) - len(archivos_clasificados)
    stats["migrados"] = len(archivos_clasificados)

    if archivos_clasificados:
        ec.registrar_iteracion(
            "MIGRADO", len(archivos_clasificados), len(archivos_clasificados), 0,
            "Inventario automático desde JSONs existentes"
        )
        ec.guardar()

    return stats


def main():
    OUTPUT_JSON = Path(RUTA_SALIDA_JSON)

    print("=" * 70)
    print("  INVENTARIO Y MIGRACIÓN DE JSONS EXISTENTES")
    print("  Este script NO gasta tokens de IA.")
    print("=" * 70)
    print(f"  Carpeta fuente:  {RUTA_PADRE}")
    print(f"  Carpeta salida:  {OUTPUT_JSON}")
    print("=" * 70)

    # ── 1. Encontrar carpetas de entrada ──
    carpetas_entrada = []
    buscar_dir(Path(RUTA_PADRE), carpetas_entrada)
    print(f"\n[1/4] Carpetas de entrada encontradas: {len(carpetas_entrada)}")

    # Mapeo: id_sujeto → carpeta de entrada
    mapa_entrada = {}
    for carpeta in carpetas_entrada:
        id_sujeto, _ = obtener_id(carpeta)
        mapa_entrada[id_sujeto] = carpeta

    # ── 2. Escanear carpetas de salida ──
    if not OUTPUT_JSON.exists():
        print("ERROR: No existe la carpeta de salida. Nada que inventariar.")
        sys.exit(1)

    carpetas_salida = sorted([d for d in OUTPUT_JSON.iterdir() if d.is_dir()])
    print(f"[2/4] Carpetas de salida encontradas: {len(carpetas_salida)}")

    # Contadores globales
    total = 0
    ya_tenian = 0
    migradas = 0
    sin_jsons = 0
    sin_entrada = 0
    completadas = 0
    parciales = 0
    jsons_total = 0
    jsons_invalidos = 0
    segmentos_total = 0
    compilados_total = 0
    compilados_seg_ok = 0
    compilados_seg_pend = 0
    errores_graves = []

    for carpeta in carpetas_salida:
        id_sujeto = carpeta.name
        total += 1

        carpeta_entrada = mapa_entrada.get(id_sujeto)
        if not carpeta_entrada:
            sin_entrada += 1
            continue

        archivos_entrada = get_archivos(carpeta_entrada, FORMATOS)
        if not archivos_entrada:
            continue

        resultado = inventariar_carpeta(carpeta, archivos_entrada)

        if resultado is None:
            ya_tenian += 1
            continue

        if resultado["migrados"] == 0:
            sin_jsons += 1
            continue

        migradas += 1
        jsons_total += resultado["jsons_total"]
        jsons_invalidos += resultado["jsons_invalidos"]
        segmentos_total += resultado["segmentos_total"]
        compilados_total += resultado["compilados"]
        compilados_seg_ok += resultado["compilados_segmentados"]
        compilados_seg_pend += resultado["compilados_pendientes"]

        if resultado["archivos_faltantes"] == 0 and resultado["compilados_pendientes"] == 0:
            completadas += 1
        else:
            parciales += 1

        if resultado["jsons_invalidos"] > 0:
            for det in resultado["jsons_invalidos_detalle"]:
                errores_graves.append(f"{id_sujeto}/{det['archivo']}: {det['errores']}")

        # Progreso cada 50 carpetas
        if migradas % 50 == 0:
            print(f"  ... {migradas} carpetas migradas ...")

    # ── 3. Corregir estado_lote.json ──
    print(f"\n[3/4] Corrigiendo estado_lote.json...")

    estado = EstadoLote(OUTPUT_JSON)
    corregidos_a_completado = 0
    corregidos_a_parcial = 0

    for carpeta_entrada in carpetas_entrada:
        clave = carpeta_entrada.name
        id_sujeto, _ = obtener_id(carpeta_entrada)
        carpeta_salida = OUTPUT_JSON / id_sujeto

        if not carpeta_salida.exists():
            continue

        ec = EstadoCarpeta(carpeta_salida)
        if not ec.ruta.exists():
            continue

        estado_actual = estado.datos.get(clave, {}).get("estado", "")
        if estado_actual in ("COMPLETADO", "APROBADO"):
            continue  # no tocar las ya aprobadas

        total_ok, total_fail, total_rastreados = ec.resumen()
        comps_pend = len(ec.compilados_pendientes())
        archivos = get_archivos(carpeta_entrada, FORMATOS)
        faltantes = len(archivos) - total_rastreados

        if faltantes <= 0 and comps_pend == 0 and total_fail == 0:
            # Todo está en orden → COMPLETADO
            estado.marcar_completado(clave, carpeta_salida)
            corregidos_a_completado += 1
        elif total_ok > 0:
            # Hay progreso parcial
            motivo_partes = []
            if faltantes > 0:
                motivo_partes.append(f"{faltantes} archivo(s) sin clasificar")
            if comps_pend > 0:
                motivo_partes.append(f"{comps_pend} compilado(s) sin segmentar")
            if total_fail > 0:
                motivo_partes.append(f"{total_fail} archivo(s) con error")
            motivo = ", ".join(motivo_partes)

            estado.marcar_parcial(
                clave, motivo, carpeta_salida,
                archivos_ok=total_ok,
                archivos_fallidos=total_fail + max(0, faltantes) + comps_pend,
            )
            corregidos_a_parcial += 1

    # ── 4. Resumen final ──
    comp, fall, parc, pend, total_lote = estado.resumen()

    print(f"\n[4/4] Inventario completado.")
    print()
    print("=" * 70)
    print("  RESUMEN DEL INVENTARIO")
    print("=" * 70)
    print(f"  Carpetas de salida escaneadas:       {total}")
    print(f"  Ya tenían checklist (_estado_):       {ya_tenian}")
    print(f"  Migradas en esta ejecución:           {migradas}")
    print(f"  Sin JSONs (vacías):                   {sin_jsons}")
    print(f"  Sin carpeta de entrada:               {sin_entrada}")
    print("-" * 70)
    print(f"  JSONs analizados:                     {jsons_total}")
    print(f"    → Clasificaciones de archivos:      {jsons_total - segmentos_total - jsons_invalidos}")
    print(f"    → Segmentos de compilados:           {segmentos_total}")
    print(f"    → JSONs con estructura inválida:    {jsons_invalidos}")
    print("-" * 70)
    print(f"  Compilados encontrados:               {compilados_total}")
    print(f"    → Ya segmentados (con segmentos):   {compilados_seg_ok}")
    print(f"    → Pendientes de segmentación:       {compilados_seg_pend}")
    print("-" * 70)
    print(f"  Carpetas migradas → COMPLETADO:       {corregidos_a_completado}")
    print(f"  Carpetas migradas → PARCIAL:          {corregidos_a_parcial}")
    print()
    print("=" * 70)
    print("  ESTADO GLOBAL (estado_lote.json)")
    print("=" * 70)
    print(f"  ✅ COMPLETADO:   {comp:>5}")
    print(f"  🔶 PARCIAL:      {parc:>5}")
    print(f"  ❌ FALLIDO:      {fall:>5}")
    print(f"  ⏳ PENDIENTE:    {pend:>5}")
    print(f"  📊 TOTAL:        {total_lote:>5}")
    print("-" * 70)
    print(f"  → Carpetas que necesitan `reintentar`: {fall + parc}")
    print(f"    (solo se gastarán tokens en segmentación de compilados)")
    print("=" * 70)

    if errores_graves:
        print(f"\n⚠ JSONs con estructura inválida ({len(errores_graves)}):")
        for e in errores_graves[:30]:
            print(f"  {e}")
        if len(errores_graves) > 30:
            print(f"  ... y {len(errores_graves) - 30} más")

    print("\n✅ Listo. Ahora ejecuta:  python script.py reintentar")


if __name__ == "__main__":
    main()
