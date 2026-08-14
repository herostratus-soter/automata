import sys
from pathlib import Path
from google import genai
from google.genai import types

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

client = genai.Client(api_key=config.APIKEY)


def consultar_ai(prompt, archivo_path=None, es_json=False):
    contents = [client.files.upload(file=Path(archivo_path))] if archivo_path else []
    contents.append(prompt)

    cfg = {"thinking_config": types.ThinkingConfig(thinking_budget=0)}
    if es_json:
        cfg["response_mime_type"] = "application/json"

    resp = client.models.generate_content(
        model=config.MODELO_DEFAULT,
        contents=contents,
        config=types.GenerateContentConfig(**cfg)
    )

    texto = resp.text.strip('\'" \n\r\t') if resp.text else ""
    meta = resp.usage_metadata
    inp = getattr(meta, 'prompt_token_count', 0) if meta else 0
    out = getattr(meta, 'candidates_token_count', 0) if meta else 0

    return [texto, inp, out]


def calcular_costo(inp, out):
    costo_inp = (inp / 1000000) * getattr(config, 'PRECIO_MILLON_INPUT_USD', 0.075)
    costo_out = (out / 1000000) * getattr(config, 'PRECIO_MILLON_OUTPUT_USD', 0.30)
    return costo_inp + costo_out


def reporte_tokens(inp, out, titulo="CONSUMO DE TOKENS"):
    costo = calcular_costo(inp, out)
    return (
        f"\n{'='*55}\n"
        f"          {titulo.upper()}\n"
        f"{'='*55}\n"
        f" Tokens de Entrada: {inp:>10,}\n"
        f" Tokens de Salida:  {out:>10,}\n"
        f"{'-'*55}\n"
        f" TOTAL TOKENS:      {inp + out:>10,}\n"
        f" Costo estimado:    ${costo:>10.6f} USD\n"
        f"{'='*55}\n"
    )
