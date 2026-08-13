import os
from config import *
from lista_analistas import *

# Crea la carpeta principal del mes
os.mkdir(mes_actual)

# Crea la subcarpeta para cada analista
for analista in analistas:
    os.mkdir(f"{mes_actual}/{index_analista}{analista}")

# -----------------Creacion de archivo Excel--------------
# Copiar el archivo renombrándolo al mismo tiempo
os.system(f"cp {formato_excel} {mes_actual}/{mes_actual}{sufijo_excel}")