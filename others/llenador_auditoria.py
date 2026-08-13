import os
import openpyxl
from config import *
from lista_analistas import *

archivo_excel = f"{mes_actual}/{mes_actual}{sufijo_excel}"

# 1. Buscar las carpetas que inicien estrictamente con el prefijo
rutas = []
for raiz, carpetas, _ in os.walk(mes_actual):
    for carpeta in carpetas:
        if carpeta.startswith(index_colaborador):
            rutas.append(os.path.join(raiz, carpeta))

# 2. Cargar Excel y escribir directo en la columna a partir de la fila 3
wb = openpyxl.load_workbook(archivo_excel)
ws = wb.active

for fila, ruta in enumerate(rutas, start=3):
    ws.cell(row=fila, column=ruta_carpeta, value=ruta)

# 3. Guardar los cambios
wb.save(archivo_excel)