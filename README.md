# Automata: Sistema de Auditoría y Verificación Masiva de Documentación

**Automata** es un sistema modular en Python diseñado para la automatización, inspección y auditoría masiva de carpetas de contratación laboral. Utiliza modelos de Inteligencia Artificial de la suite **Google GenAI (Gemini)** para clasificar documentos, verificar identidades y nombres, evaluar el cumplimiento de requisitos normativos y consolidar reportes ejecutivos en Excel.

El sistema está optimizado para procesar grandes volúmenes de información (como lotes de 700+ carpetas de personas y 25+ GB de documentos en PDF e imágenes) garantizando resiliencia ante caídas de red, límites de API y desconexiones imprevistas gracias a su arquitectura de reintentos exponenciales y *checkpointing* persistente.

---

## 📸 Descripción General del Sistema

El proceso de verificación documental de contratación suele involucrar miles de archivos desorganizados, carpetas nombradas por número de cédula, documentos en PDF o imágenes sueltas y archivos "compilados" que contienen múltiples documentos pegados en un solo PDF.

**Automata** automatiza este flujo mediante las siguientes fases:

1. **Exploración y Desbloqueo**: Recorre la estructura de la carpeta padre, detecta carpetas asociadas a contratados (identificadas por su cédula) y desbloquea automáticamente PDFs protegidos con contraseña usando el número de identificación como clave.
2. **Inspección con IA (Fase 1)**: Sube cada archivo a la API de Gemini y lo clasifica dentro de un catálogo predefinido de tipos documentales (definido en `reglas_v2.ods`), validando si el documento pertenece al sujeto auditado (verificación de cédula y nombre).
3. **Segmentación Inteligente de Compilados**: Detecta PDFs multipágina que contienen varios trámites pegados y utiliza el modelo `gemini-2.5-flash` para identificar los puntos de corte por página y fragmentar el PDF en segmentos independientes para su posterior clasificación.
4. **Evaluación de Requisitos (Fase 2)**: Para cada tipo de documento detectado, evalúa los requisitos específicos exigidos en la matriz normativamente definida.
5. **Persistencia en JSON**: Almacena los hallazgos en archivos JSON individuales por persona dentro del directorio `tmp/`, acompañados de un archivo resumen (`0_ecumenico.json`).
6. **Consolidación en Excel**: Reúne todos los JSONs generados y construye un libro de Excel (`.xlsx`) estructurado con una hoja principal de estado por contratado y una hoja de leyenda explicativa.

---

## 🧩 Arquitectura del Proyecto

El sistema se divide en módulos desacoplados y enfocados:

```text
automata/
├── README.md              # Documentación general y guía de uso
├── config.py              # Parámetros de configuración, credenciales y rutas (.gitignore)
├── config.example.py      # Plantilla base de configuración
├── script_v2.py           # Pipeline principal de orquestación y consulta a Gemini
├── robustez.py            # Capa de resiliencia: Exponential Backoff, Checkpointing y Logs
├── constructor.py         # Módulo de lectura de JSONs y consolidación a Excel
├── reglas_v2.ods          # Catálogo de tipos de documento y requisitos (LibreOffice / Excel)
├── requirements.txt       # Dependencias de librerías Python
├── logs/                  # Registros de ejecución y auditoría de errores
└── tmp/                   # Checkpoint (estado_lote.json) y JSONs procesados por cédula
```

### Descripción de Módulos:

- **`script_v2.py`**: Es el motor principal del pipeline. Lee el catálogo de reglas, realiza llamadas a la API de Gemini utilizando hilos concurrentes (`ThreadPool`), gestiona los dos pasos de inspección y coordina la segmentación de compilados.
- **`robustez.py`**: Proporciona el decorador `@reintentar` con backoff exponencial para absorber errores 429/503/caídas de red, la clase `EstadoLote` para el control de progreso (*checkpointing*) y la configuración del sistema de registros (*logging*).
- **`constructor.py`**: Lee los JSONs resultantes en `tmp/` junto con el archivo de reglas `reglas_v2.ods` para compilar la matriz final en Excel.
- **`reglas_v2.ods`**: Define el catálogo de documentos (cédula, antecedentes, certificados de estudio, cursos, etc.) y los campos de requisitos a verificar.

---

## 🛠️ Requisitos e Instalación

### Dependencias de Python

Instala las librerías necesarias ejecutando:

```bash
pip install -r requirements.txt
```

Las dependencias principales son:
- `google-genai`: SDK oficial de Google GenAI / Gemini.
- `pypdf`: Procesamiento, lectura y segmentación de archivos PDF.
- `pandas`: Manejo de datos y generación de matrices.
- `openpyxl`: Motor de lectura/escritura de archivos Excel (`.xlsx`).
- `odfpy`: Lectura de archivos de hoja de cálculo OpenDocument (`.ods`).

---

## ⚙️ Configuración (`config.py`)

El archivo `config.py` almacena las variables de entorno, claves de API y rutas de trabajo.

```python
from pathlib import Path

# ─── Credenciales de Gemini ───
APIKEY = "TU_API_KEY_DE_GEMINI_AQUI"

# ─── Modelos de IA ───
MODELO_FLASH = "gemini-2.5-flash"       # Reservado para segmentación de compilados pesados
MODELO_LITE  = "gemini-3.1-flash-lite"  # Usado para clasificación y evaluación de requisitos

# ─── Período de contratación ───
ANIO = "2026"
MES  = "09"

# ─── Rutas del Sistema ───
RUTA_ODS = Path(__file__).parent / "reglas_v2.ods"

# Directorio raíz con TODAS las carpetas de contratados (para procesamiento completo)
RUTA_PADRE = Path("/ruta/a/tu/carpeta_padre")

# Carpeta específica para realizar pruebas
RUTA_PRUEBA = RUTA_PADRE / "1018293847 PEREZ GOMEZ JUAN"

# Salidas
RUTA_SALIDA_JSON = Path(__file__).parent / "tmp"
RUTA_SALIDA_EXCEL = Path(__file__).parent
RUTA_LOGS = Path(__file__).parent / "logs"

# Formatos aceptados
FORMATOS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".docx"}

# ─── Paralelismo y Resiliencia ───
HILOS = 7
MAX_REINTENTOS = 5
ESPERA_BASE = 2.0
```

---

## 🚀 Modos de Ejecución

### 1. Ejecución Local (CLI)

En tu entorno local (Linux / macOS / Windows), ejecuta desde la terminal:

```bash
# 1. Modo Prueba (Audita una sola carpeta configurada en RUTA_PRUEBA)
python script_v2.py prueba

# 2. Modo Lote (Audita todas las carpetas dentro de RUTA_PADRE con checkpointing)
python script_v2.py lote

# 3. Modo Reintentar (Reejecuta solo las carpetas que marcaron error en el lote previo)
python script_v2.py reintentar

# 4. Consolidar resultados en Excel
python constructor.py
```

---

### 2. Ejecución en Google Colab con Google Drive

Automata está completamente adaptado para ejecutarse en entornos en la nube como **Google Colab** consumiendo carpetas almacenadas en **Google Drive**.

#### Ventajas del diseño en la nube:
- **Lectura Bajo Demanda (No requiere `cp` ni `mv`)**: Aunque la carpeta padre tenga **25 GB**, el sistema no copia ni mueve el volumen total al disco local de Colab. Lee y transmite los archivos carpeta por carpeta directamente desde Drive.
- **Independencia de Cuentas**: La cuenta de Google Drive donde residen los PDFs puede ser diferente a la cuenta dueña de la `APIKEY` de Gemini.

#### Guía Paso a Paso en Colab:

**Paso 1: Montar Google Drive**
```python
from google.colab import drive
drive.mount('/content/drive')
```

**Paso 2: Instalar Dependencias**
```bash
!pip install -q google-genai pypdf pandas openpyxl odfpy
```

**Paso 3: Ubicarse en el Directorio del Proyecto**
```python
%cd /content/drive/MyDrive/automata
```

**Paso 4: Ejecutar Auditoría en Modo Lote**
```bash
!python script_v2.py lote
```

**Paso 5: Consolidar a Excel**
```python
!python constructor.py
```

---

## 🛡️ Robustez, Resiliencia y Checkpointing

Automata incluye un sistema de tolerancia a fallos pensado para ejecuciones desatendidas:

### 1. Checkpointing Persistente (`tmp/estado_lote.json`)
Cada carpeta procesada actualiza atómicamente el archivo `estado_lote.json`. Si el proceso se interrumpe por caída de energía, límite de tiempo de Colab o corte de red, al reiniciar `python script_v2.py lote`, Automata:
- Lee el registro de estados.
- Omite en milisegundos las carpetas marcadas como `COMPLETADO`.
- Continúa exactamente en la carpeta donde ocurrió la interrupción, sin gastar cuota de API ni tiempo redundante.

### 2. Reintentos con Backoff Exponencial (`robustez.py`)
Todas las llamadas a la API de Gemini están protegidas por el decorador `@reintentar(max_intentos=5, base_espera=2.0)`.
- Si la API responde con errores de límite de cuota (`429`), servicio no disponible (`503`) o desconexiones de red, el sistema espera **2s, 4s, 8s, 16s y 32s** antes de reintentar.
- Los errores lógicos (archivos corruptos o JSONs malformados) se capturan sin consumir reintentos innecesarios.

### 3. Aislamiento de Errores por Archivo y Carpeta
- Un PDF corrupto o con contraseña incorrecta no interrumpe el procesamiento de los demás archivos de esa persona.
- Una carpeta con errores críticos se marca como `FALLIDO` en el estado del lote y el sistema continúa inmediatamente con la siguiente carpeta.

---

## 📊 Registros de Diagnóstico (Logs)

Automata escribe registros en el directorio `logs/`:

- **`logs/ejecucion.log`**: Registro exhaustivo (nivel `DEBUG`) con el detalle de cada archivo procesado y tokens consumidos.
- **`logs/errores.log`**: Registro filtrado (nivel `WARNING` / `ERROR`) que permite identificar rápidamente qué carpetas o archivos sufrieron inconvenientes sin revisar miles de líneas normadas.

---

## 💡 Estimación de Costos y Recursos

- **Google Colab**: $0 USD (Gratis).
- **Google Gemini API**: Utilizando el modelo `gemini-3.1-flash-lite`, procesar un lote masivo de **700 carpetas (~25 GB)** tiene un costo aproximado de **$0.20 a $1.50 USD** en total si se utiliza una API Key en modalidad Pay-As-You-Go. En la modalidad gratuita (Free Tier), el costo es **$0 USD**, aunque se recomienda reducir el parámetro `HILOS = 2` para respetar el límite de 15 peticiones por minuto.
