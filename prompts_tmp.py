# ==============================================================================
# 1. SUPERDICCIONARIO DE CATEGORÍAS
# ==============================================================================

CATEGORIAS = {
    "documento_id": {
        "rename": "01_documento_id",
        "descripcion": "Documento de Identidad (Cédula de ciudadanía, cédula de extranjería, pasaporte, PPT). NO incluir licencias de conducción ni libretas militares.",
        "requerimientos_especificos": {
            "tipo_documento": "Buscar en el documento el tipo de documento de identidad (cédula, pasaporte, etc.) y guardarlo como string"
        }
    },
    "contrato_laboral": {
        "rename": "02_contrato_laboral",
        "descripcion": "Contrato de Trabajo, contrato laboral firmado, otrosí o adendas.",
        "requerimientos_especificos": {
            "fecha_inicio": "Fecha de inicio de labores",
            "esta_firmado": "Verificar si los espacios para firma del trabajador están firmados por el candidato"
        }
    },
    "curso_etica": {
        "rename": "03_curso_etica",
        "descripcion": "Certificado o constancia del Curso de Ética (Códigos de ética, SAGRILAFT, conducta).",
        "requerimientos_especificos": {
            "nombre_curso": "Nombre del curso impartido"
        }
    },
    "curso_transparencia": {
        "rename": "04_curso_transparencia",
        "descripcion": "Certificado o constancia del Curso de Transparencia o Anticorrupción (PTEE, anticorrupción).",
        "requerimientos_especificos": {
            "nombre_curso": "Nombre del curso impartido"
        }
    },
    "curso_cultura": {
        "rename": "05_curso_cultura",
        "descripcion": "Certificado o constancia del Curso de Cultura Organizacional (Inducción corporativa, SGSST, clima organizacional).",
        "requerimientos_especificos": {
            "nombre_curso": "Nombre del curso impartido"
        }
    },
    "pruebas_psicotecnicas": {
        "rename": "06_pruebas_psicotecnicas",
        "descripcion": "Resultados o informes de Pruebas Psicotécnicas.",
        "requerimientos_especificos": {}
    },
    "verificacion_referencias": {
        "rename": "07_verificacion_referencias",
        "descripcion": "Formato o informe de Verificación de Referencias.",
        "requerimientos_especificos": {}
    },
    "arl": {
        "rename": "08_arl",
        "descripcion": "Certificado de afiliación a ARL (Riesgos Laborales).",
        "requerimientos_especificos": {}
    },
    "ccf": {
        "rename": "09_ccf",
        "descripcion": "Certificado de afiliación a CCF (Caja de Compensación Familiar).",
        "requerimientos_especificos": {}
    },
    "examen_medico_ingreso": {
        "rename": "10_examen_medico_ingreso",
        "descripcion": "Concepto o examen médico ocupacional o de ingreso.",
        "requerimientos_especificos": {}
    },
    "antecedente_policia": {
        "rename": "11_antecedente_policia",
        "descripcion": "Certificado de Antecedentes de la Policía Nacional.",
        "requerimientos_especificos": {
            "tiene_antecedentes": "Verificar que NO registre antecedentes"
        }
    },
    "antecedente_procuraduria": {
        "rename": "12_antecedente_procuraduria",
        "descripcion": "Certificado de Antecedentes de la Procuraduría General.",
        "requerimientos_especificos": {
            "tiene_antecedentes": "Verificar que NO registre antecedentes"
        }
    },
    "antecedente_contraloria": {
        "rename": "13_antecedente_contraloria",
        "descripcion": "Certificado de Antecedentes Fiscales de la Contraloría.",
        "requerimientos_especificos": {
            "tiene_antecedentes": "Verificar que NO registre antecedentes"
        }
    },
    "cuenta_bancaria": {
        "rename": "14_cuenta_bancaria",
        "descripcion": "Certificación bancaria o soporte de Cuenta Bancaria para pago de nómina.",
        "requerimientos_especificos": {
            "numero_cuenta": "Número de cuenta bancaria registrado"
        }
    },
    "pension": {
        "rename": "15_pension",
        "descripcion": "Certificado de afiliación o historial de Pensiones (Protección, Porvenir, Colpensiones, etc.).",
        "requerimientos_especificos": {
            "es_valido": "Verificar que corresponda a un fondo de pensiones y/o cesantías"
        }
    },
    "cesantias": {
        "rename": "16_cesantias",
        "descripcion": "Certificado o constancia de afiliación a Cesantías.",
        "requerimientos_especificos": {
            "es_valido": "Verificar que corresponda a un fondo de pensiones y/o cesantías"
        }
    },
    "eps": {
        "rename": "17_eps",
        "descripcion": "Certificado de afiliación a EPS (Sura, Sanitas, Compensar, etc.) o ADRES.",
        "requerimientos_especificos": {}
    },
    "referencias": {
        "rename": "18_referencias",
        "descripcion": "Cartas o soportes generales de Referencias.",
        "requerimientos_especificos": {}
    },
    "estudios": {
        "rename": "19_estudios",
        "descripcion": "Títulos de estudio, diplomas, actas de grado o certificados académicos (Colegios, Universidades, SENA, diplomados).",
        "requerimientos_especificos": {
            "es_bachillerato": "Verificar si el título o estudio corresponde a bachillerato"
        }
    },
    "referencia_personal": {
        "rename": "20_referencia_personal",
        "descripcion": "Carta de Referencia Personal o familiar.",
        "requerimientos_especificos": {
            "fecha_reciente": "Verificar que la fecha sea reciente con relación al contrato",
            "esta_firmada": "Verificar que esté firmada por quien emite la referencia"
        }
    },
    "referencia_laboral": {
        "rename": "21_referencia_laboral",
        "descripcion": "Certificado Laboral o Referencia Laboral de empleos anteriores.",
        "requerimientos_especificos": {
            "indica_prestacion_servicio": "Corroborar que se indique que el candidato laboró o prestó servicios en la empresa",
            "esta_firmada": "Verificar que esté firmada"
        }
    },
    "hoja_de_vida": {
        "rename": "22_hoja_de_vida",
        "descripcion": "Hoja de Vida (HV) o Curriculum Vitae.",
        "requerimientos_especificos": {}
    },
    "formatos_para_la_contratacion": {
        "rename": "23_formatos_para_la_contratacion",
        "descripcion": "Formatos diligenciados para la contratación (autorizaciones, tratamiento de datos, listas de chequeo).",
        "requerimientos_especificos": {
            "conteo_hojas": "Verificar que como mínimo sean 9 hojas",
            "hojas_diligenciadas": "Verificar que las hojas estén diligenciadas y firmadas por el candidato"
        }
    }
}


# ==============================================================================
# 2. GENERADOR AUTOMÁTICO DE LA LISTA DE CATEGORÍAS PARA PROMPTS
# ==============================================================================

# Construye la lista de categorías dinámicamente desde el Superdiccionario
lista_prompt_lineas = [
    f"- {info['descripcion']} -> OUTPUT: {info['rename']}"
    for info in CATEGORIAS.values()
]
LISTA_CATEGORIAS_PROMPT = "\n".join(lista_prompt_lineas)


# ==============================================================================
# 3. PROMPTS DE CLASIFICACIÓN Y RENOMBRADO (FASE 1)
# ==============================================================================

PROMPT_POR_NOMBRE = f"""
Tu única tarea es analizar el NOMBRE DE UN ARCHIVO y clasificarlo dentro de UNA de las siguientes categorías predefinidas.

### LISTA DE CATEGORÍAS Y OUTPUTS PERMITIDOS:
{LISTA_CATEGORIAS_PROMPT}

### REGLA DE AMBIGÜEDAD (ULTRA ESTRICTO):
Cualquier nombre que contenga palabras genéricas como "curso", "diploma", "certificado", "certificacion", "acta", "soporte", "copia", "doc", "scan", "foto" o nombres de archivos numéricos/ambiguos DEBE SER RECHAZADO, A MENOS QUE el nombre especifique de forma 100% inconfundible la categoría exacta (por ejemplo: "antecedentes_policia.pdf" o "cedula_juan.pdf"). Si hay la más mínima duda o falta de claridad, RESPONDE SIEMPRE: REVISAR_CONTENIDO.

### REGLAS DE RESPUESTA (ESTRICTO):
1. Evalúa ÚNICAMENTE el texto del nombre del archivo que se te proporciona.
2. Si el nombre sugiere claramente y SIN AMBIGÜEDAD una categoría, responde ÚNICAMENTE con la clave del OUTPUT (ejemplo: {CATEGORIAS['documento_id']['rename']}).
3. Si el nombre es ambiguo, genérico o no coincide con claridad absoluta, responde exactamente: REVISAR_CONTENIDO
4. PROHIBIDO usar comillas, comillas simples, espacios al inicio o al final, saltos de línea, explicaciones o formato markdown. Devuelve SOLO la clave limpia.
"""

PROMPT_POR_CONTENIDO = f"""
Tu única tarea es analizar exhaustivamente el CONTENIDO VISUAL / TEXTUAL de este documento y clasificarlo dentro de UNA de las siguientes categorías predefinidas.

### LISTA DE CATEGORÍAS Y OUTPUTS PERMITIDOS:
{LISTA_CATEGORIAS_PROMPT}

### INSTRUCCIONES DE LECTURA Y PREVENCIÓN DE ERRORES:
1. LEE DETENIDAMENTE el título principal, encabezados, logos y el texto del cuerpo del documento antes de clasificar.
2. DISTINCIÓN CRÍTICA ENTRE "ESTUDIOS" Y "CURSOS CORPORATIVOS":
   - Títulos universitarios, actas de grado, bachillerato, SENA o diplomados educativos van a "{CATEGORIAS['estudios']['rename']}".
   - Certificados de capacitaciones empresariales, inducciones corporativas, cursos de ética, SAGRILAFT o transparencia NO son estudios formales; pertenecen a "{CATEGORIAS['curso_etica']['rename']}", "{CATEGORIAS['curso_transparencia']['rename']}" o "{CATEGORIAS['curso_cultura']['rename']}".
3. No asumas la categoría basándote en la primera palabra que veas; analiza el propósito global del documento.

### REGLAS DE RESPUESTA (ESTRICTO):
1. Si coincide claramente con alguna categoría, responde ÚNICAMENTE con la clave del OUTPUT (ejemplo: {CATEGORIAS['documento_id']['rename']}).
2. Si el documento NO coincide con ninguna categoría o es totalmente ilegible, responde exactamente: NO_CLASIFICADO
3. PROHIBIDO redactar explicaciones, justificaciones, saludos, comillas, saltos de línea o formato markdown. Devuelve SOLO la clave limpia.
"""

"""
lista = [
    "01documento_id",
    "02contrato_laboral",
    "03curso_etica",
    "04curso_transparencia",
    "05curso_cultura",
    "06pruebas_psicotecnicas",
    "07verificacion_referencias",
    "08arl",
    "09ccf";
    "10examen_medico_ingreso",
    "11antecedente_policia",
    "12antecedente_procuraduria",
    "13antecedente_contraloria",
    "14cuenta_bancaria",
    "15pension",
    "16cesantias",
    "17eps",
    "18referencias",
    "19estudios",
    "20refencia_personal"
    "21referenca_laboral",
    "22hoja_de_vida",
    "23formatos_para_la_contratacion"
    "24informe de datacredito"
    "25informe de bases"
    ]
    
______________________________________________________________________
______________________________________________________________________
______________________________________________________________________    
  
01documento_id = [
    "tipo de documento"
    ]

02contrato_laboral = [
    "fecha de inicio de labores",
    "los espacios para firma del trabajador esten firmados por el candidato"
    ]

03curso_etica = [
    ]

04curso_transparencia = [
    ]

05curso_cultura = [
    ]

06pruebas_psicotecnicas = [
    ]

07verificacion_referencias = [
    ]

08arl = [
    ]

09ccf = [
    ]

10examen_medico_ingreso = [
    ]

11antecedente_policia = [
    "no tener antecedentes"
    ]

12antecedente_procuraduria = [
    "no tener antecedentes"
    ]

13antecedente_contraloria = [
    "no tener antecedentes"
    ]

14cuenta_bancaria = [
    "numero de cuenta"
   ]

15pension = [
    "verificar que sea fondo de pensiones o de pensiones y cesantías"
    ]

16cesantias = [
    "verificar que sea fondo de cesantías o de pensiones y cesantías"

17epsoadress= [
    ]
18 estudios = [
    "que sean de bachillerato"
    ]
19refencia_personal = [
    "fecha",
    "firma"
    ]
 
20refencia_laboral = [
    ]

21hoja_de_vida = [
    ]

22formatos_para_la_contratacion = [
    "verificar que minimo sean 9 hojas",
    "verificar que las 9 hojas esten diligenciadas y firmadas por el candidato cuando corresponda"
    ]
23informe_datacredito = [
    "verificar si la persona tiene moras",
    "verificar si la persona tiene demandas"
    ]
24informe_bases = [
    "verificar si la persona tiene algún inconveniente que le impida ser contratado"
    ]
25visita_domiciliaria = [
    ]
26acuerdo_de_pago = [
    ]
27compilado

28otros

"""







