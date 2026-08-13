# automata

Sirve para revisar documentos

# 1. Crear y activar entorno virtual en donde tengas los entornos virtuales

python -m venv <nombre_de_entorno>
source <nombre_de_entorno>/bin/activate

ejemplo:

python -m venv ejemplo_env
source ejemplo_env/bin/activate

# 2. Clonar o entrar a la carpeta

cd automata

# 3. Instalar dependencias

pip install -r requirements.txt

# 4. Guardar dependencias

pip freeze > requirements.txt


# 5. Configuración

Antes de ejecutar el proyecto, debes crear el archivo de configuración a partir de la plantilla:

1. Copia el archivo `config.example.py` y renómbralo como `config.py`.
2. Abre `config.py` y edita las siguientes variables con tus datos:
   - `apikey`: Tu clave de API.
   - `rutamaestro`: La ruta al directorio maestro.
   - `rutatemporal`: La ruta al directorio temporal.
