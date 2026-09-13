# Automata

Sistema de auditoria y verificacion masiva de documentos de contratacion mediante Inteligencia Artificial (Google Gemini).

El sistema procesa carpetas de contratados, clasifica sus documentos segun las reglas definidas en la plantilla de reglas (referenciada externamente en `RUTA_ODS`), evalua requisitos de identidad y nombre, genera evidencias en JSON y consolida un reporte final en Excel.

---

## Estructura del Proyecto

- `script.py`: Script principal de procesamiento e inspeccion documental con IA.
- `constructor.py`: Consolidador de resultados JSON a reporte Excel (`.xlsx`).
- `config.py`: Variables de configuracion local (API Key, rutas externas, modelos, limites).
- `config.example.py`: Plantilla de referencia para crear `config.py`.
- `logs.py`: Manejo de resiliencia, reintentos con backoff exponencial y checklist (`estado_lote.json`).
- `requirements.txt`: Lista de dependencias de Python necesarias.
- `logs/`: Directorio donde se guardan los archivos de registro de ejecucion.

---

## Entorno Virtual de Python (opcional pero recomendado)

Para aislar las librerias del proyecto sin alterar el Python global de tu sistema:

1. **Crear la carpeta del entorno virtual**:
   ```bash
   python3 -m venv env/mi_entorno
   ```

2. **Activar el entorno con `source`**:
   ```bash
    source env/mi_entorno/bin/activate
   ```

3. **Desactivar el entorno al finalizar**:
   ```bash
   deactivate
   ```

---

## Requisitos e Instalacion

Con el entorno virtual activo, instala las dependencias:

```bash
pip install -r requirements.txt
```

Crear el archivo de configuracion `config.py` a partir de la plantilla:

```bash
cp config.example.py config.py
```

Edita `config.py` e ingresa tu `APIKEY` de Gemini y configura `RUTA_ODS` apuntando a la ubicacion externa de tu archivo de reglas (`.ods`).

---

## Uso del Sistema

1. **Modo Prueba**: Procesa una muestra reducida de carpetas para validar la configuracion.
   ```bash
   python script.py prueba
   ```

2. **Modo Lote**: Procesa las carpetas encontradas en `RUTA_PADRE`. Salta automaticamente las carpetas aprobadas.
   ```bash
   python script.py lote
   ```

3. **Modo Reintentar**: Reprocesa unicamente las carpetas que quedaron en estado defectuoso en `estado_lote.json`.
   ```bash
   python script.py reintentar
   ```

4. **Consolidar Excel**: Genera el informe final `.xlsx` unificando los resultados guardados en `tmp/`.
   ```bash
   python constructor.py
   ```

---

## Control de Estado y Logs

- `tmp/estado_lote.json`: Registra el estado de cada carpeta (`COMPLETADO`, `FALLIDO`, `PENDIENTE`). Permite reanudar ejecuciones canceladas o interrumpidas sin reprocesar trabajo previo.
- `logs/ejecucion.log`: Historial detallado de auditoria y eventos.
- `logs/errores.log`: Historial exclusivo de advertencias y errores.
