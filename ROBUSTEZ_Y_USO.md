# Guía de Robustez, Resiliencia y Uso Masivo

Esta guía explica la arquitectura de seguridad, la capa de resiliencia y el uso eficiente del sistema de automatización para procesar carpetas masivas de contratación (700+ carpetas) sin riesgo de pérdidas de datos, fugas de memoria o consumo desmedido de tokens.

---

## 1. Estructura y Módulos

El sistema ha sido estructurado de manera modular sin alterar la lógica de negocio ni las reglas de clasificación:

```
automata/
├── config.py              # Credenciales, rutas, modelos de IA y parámetros de resiliencia (.gitignore)
├── robustez.py            # Módulo de resiliencia: Decorador Retry, Checkpointing y Logging
├── script_v2.py           # Pipeline principal enriquecido con la capa de robustez
├── constructor.py         # Auxiliar para la lectura y parseo del archivo ODS de reglas
├── generar_reglas_v2.py   # Generador de estructura de reglas en ODS
└── tmp/
    ├── estado_lote.json   # Checkpoint de progreso por carpeta (creado automáticamente)
    └── <CEDULA>/          # JSONs clasificados individuales y 0_ecumenico.json
```

---

## 2. Modos de Ejecución (CLI)

Siempre asegúrate de activar el entorno virtual antes de ejecutar:

```bash
source /home/real_home/vm-containers-envs/envs/automata_liz/bin/activate
cd /home/real_home/videodrome_estudio/desarrollo/tmp_automatizacion/automata
```

### Comandos disponibles:

1. **Modo Prueba (por defecto)**:
   Procesa una única carpeta configurada en `config.py` (`RUTA_PRUEBA`). Ideal para verificar reglas o cambios sin procesar todo el lote.
   ```bash
   python script_v2.py prueba
   ```

2. **Modo Lote (Procesamiento completo de 700+ carpetas)**:
   Recorre todas las carpetas dentro de `RUTA_PADRE`. Gracias al **checkpointing**, si el proceso se interrumpe (caída de internet, energía, Ctrl+C), al volver a ejecutar este comando continuará exactamente donde quedó, sin reprocesar carpetas ya completadas.
   ```bash
   python script_v2.py lote
   ```

3. **Modo Reintentar Carpetas Fallidas**:
   Limpia las marcas de error de `estado_lote.json` y vuelve a intentar el procesamiento solo de aquellas carpetas que sufrieron errores definitivos durante el lote previo.
   ```bash
   python script_v2.py reintentar
   ```

4. **Ayuda**:
   ```bash
   python script_v2.py --help
   ```

---

## 3. Mecanismos de Seguridad y Resiliencia Implementados

### A. Reintentos Automáticos ante Caídas de Red o Límites de API (Exponential Backoff)
- **Problema:** Si el internet se cae durante 1 minuto o Google GenAI retorna un error `429 Too Many Requests` o `503 Service Unavailable`, la ejecución fallaría en sistemas convencionales.
- **Solución:** `robustez.py` envuelve las llamadas API con el decorador `@reintentar(max_intentos=5, base_espera=2.0)`.
- **Estrategia:** Aplica backoff exponencial con tiempos de espera de **2s, 4s, 8s, 16s y 32s**.
- **Filtro Inteligente:** Distingue entre errores de red/cuota (que se reintentan automáticamente) y errores lógicos/estructurales (como archivos corruptos o JSON mal formados), los cuales no desperdician reintentos.

### B. Checkpointing Persistente por Carpeta (`estado_lote.json`)
- **Problema:** Si se procesan 700 carpetas y el servidor se apaga en la carpeta 450, no se deben gastar tokens re-clasificando las primeras 449 carpetas.
- **Solución:** Cada carpeta procesada exitosamente actualiza de manera atómica el archivo `tmp/estado_lote.json`.
- **Estados registrados:**
  - `EN_PROCESO`: Se registra el inicio del trabajo sobre una cédula.
  - `COMPLETADO`: Se confirma la escritura correcta del JSON de la carpeta. En futuras ejecuciones, el script salta esta carpeta en milisegundos (`⏭ Saltando (ya completado)`).
  - `FALLIDO`: Registra el motivo del fallo para permitir diagnóstico o reintento postergado.

### C. Aislamiento de Errores a Nivel de Archivo y Carpeta
- **Problema:** Un PDF corrupto o con contraseña no debe detener el procesamiento de los demás archivos de la persona ni suspender las demás carpetas del lote.
- **Solución:**
  1. `ciclo_archivo` y `ciclo_archivo2` capturan excepciones por archivo, registran el error en los logs y retornan `None`, permitiendo que los archivos válidos continúen procesándose.
  2. `desbloquear_pdfs` intenta remover contraseñas comunes (como la cédula) y si un PDF está dañado, no rompe la iteración.
  3. `operacion_dir` captura excepciones por carpeta, marca la carpeta en `estado_lote.json` como `FALLIDO` y continúa con la siguiente carpeta del lote.

### D. Gestión Limpia de Recursos Temporales
- **Problema:** El cortado de PDFs compilados crea archivos temporales que pueden llenar el disco duro si ocurren excepciones intermedias.
- **Solución:** Todas las operaciones de subida a la nube GenAI y de archivos temporales locales están protegidas por bloques `try...finally`.
  - Los archivos subidos a la API de Gemini se eliminan inmediatamente con `eliminar_archivo(archivo_nube.name)`.
  - Los archivos PDF segmentados en `/tmp` se borran en la cláusula `finally` de cada función.

---

## 4. Buenas Prácticas y Ahorro de Tokens

1. **Uso Diferenciado de Modelos de IA:**
   - **`MODELO_LITE` (`gemini-3.1-flash-lite`)**: Se utiliza para clasificar documentos sueltos y extraer requisitos. Es ultrarrápido y extremadamente económico.
   - **`MODELO_FLASH` (`gemini-2.5-flash`)**: Se reserva únicamente para el segmentador de PDFs compilados (multipágina pesados) que requieren mayor ventana de contexto y capacidad deductiva.

2. **Evitar Reprocesamiento Redundante:**
   - No elimines `tmp/estado_lote.json` salvo que quieras reprocesar intencionalmente todo el lote desde cero.
   - Utiliza `python script_v2.py reintentar` para abordar fallos sin repetir carpetas exitosas.

3. **Paralelismo Optimizado (`config.py`):**
   - El número de hilos concurrente está ajustado en `HILOS = 7`.
   - Esto maximiza el rendimiento manteniendo la tasa de peticiones por minuto (RPM) dentro de los límites seguros de la API de Google GenAI.

---

## 5. Protocolo de Diagnóstico y Logs

El sistema escribe logs estructurados en el directorio `logs/`:

- `logs/ejecucion.log`: Contiene el registro detallado paso a paso (DEBUG).
- `logs/errores.log`: Registra únicamente advertencias (`WARNING`) y errores (`ERROR/CRITICAL`), facilitando una revisión rápida sin leer miles de líneas normales.
- **Consola:** Muestra el progreso resumido y claro en tiempo real con indicadores visuales (`▶`, `✓`, `⏭`, `⟳`, `⚠`, `✗`).

Si una carpeta falla en el lote, puedes auditar la causa exacta en `logs/errores.log` buscando el nombre de la carpeta o cédula.
