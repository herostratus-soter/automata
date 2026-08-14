import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import config
from ai import reporte_tokens
from identificador import identificar
from inspector import inspeccionar


def main():
    ruta_trabajo = Path(config.RUTA_TEMPORAL)

    # 1. Identificador
    inp_id, out_id = identificar(str(ruta_trabajo))
    # print(reporte_tokens(inp_id, out_id, "Reporte Identificador"))

    print("\n" + "=" * 50 + "\n")

    # 2. Inspector
    inp_ins, out_ins = inspeccionar(ruta_trabajo)
    # print(reporte_tokens(inp_ins, out_ins, "Reporte Inspector"))

    print("\nProceso de inspección finalizado con éxito.")

    # 3. Consumo Total
    if config.MOSTRAR_TOKENS:
        inp_total = (inp_id + inp_ins)*1000
        out_total = (out_id + out_ins)*1000
        print(reporte_tokens(inp_total, out_total, "Consumo Total del Proceso"))


if __name__ == "__main__":
    main()
