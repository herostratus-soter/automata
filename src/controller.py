import sys
from pathlib import Path

# Agregar la carpeta padre al path de Python para importar config, tokens, etc.
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Importación de configuración y métricas
import config
from tokens import tracker
from identificador import identificar
from inspector import inspeccionar


def main():
    # Configurar si se muestra el reporte de tokens en consola
    tracker.mostrar_reporte = config.MOSTRAR_TOKENS

    ruta_trabajo = Path(config.RUTA_TEMPORAL)

    # 1. Paso 1: Identificador
    identificar(str(ruta_trabajo))

    print("\n" + "="*50 + "\n")

    # 2. Paso 2: Inspector
    inspeccionar(ruta_trabajo)

    print("\nProceso de inspección finalizado con éxito.")

if __name__ == "__main__":
    main()
