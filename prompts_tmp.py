PROMPT_POR_NOMBRE = """
Tu única tarea es analizar el NOMBRE DE UN ARCHIVO y clasificarlo dentro de UNA de las siguientes categorías predefinidas.

### LISTA DE CATEGORÍAS Y OUTPUTS PERMITIDOS:
- Documento de Identidad (Cédula, pasaporte, PPT). -> OUTPUT: 01_documento_id
- Contrato de Trabajo, contrato laboral, otrosi. -> OUTPUT: 02_contrato_laboral
- Certificado o constancia del Curso de Ética. -> OUTPUT: 03_curso_etica
- Certificado o constancia del Curso de Transparencia o Anticorrupción. -> OUTPUT: 04_curso_transparencia
- Certificado o constancia del Curso de Cultura Organizacional. -> OUTPUT: 05_curso_cultura
- Resultados o informes de Pruebas Psicotécnicas. -> OUTPUT: 06_pruebas_psicotecnicas
- Formato o informe de Verificación de Referencias. -> OUTPUT: 07_verificacion_referencias
- Certificado de afiliación a ARL (Riesgos Laborales). -> OUTPUT: 08_arl
- Certificado de afiliación a CCF (Caja de Compensación). -> OUTPUT: 09_ccf
- Examen Médico Ocupacional o de Ingreso. -> OUTPUT: 10_examen_medico_ingreso
- Certificado de Antecedentes de la Policía. -> OUTPUT: 11_antecedente_policia
- Certificado de Antecedentes de la Procuraduría. -> OUTPUT: 12_antecedente_procuraduria
- Certificado de Antecedentes de la Contraloría. -> OUTPUT: 13_antecedente_contraloria
- Certificación bancaria o Cuenta Bancaria. -> OUTPUT: 14_cuenta_bancaria
- Certificado o historial de Pensiones (Protección, Porvenir, Colpensiones). -> OUTPUT: 15_pension
- Certificado de afiliación a Cesantías. -> OUTPUT: 16_cesantias
- Certificado de afiliación a EPS (Sura, Sanitas, Compensar, ADRES). -> OUTPUT: 17_eps
- Cartas o soportes generales de Referencias. -> OUTPUT: 18_referencias
- Títulos de estudio, diplomas, actas de grado. -> OUTPUT: 19_estudios
- Carta de Referencia Personal o familiar. -> OUTPUT: 20_referencia_personal
- Certificado Laboral o Referencia Laboral anterior. -> OUTPUT: 21_referencia_laboral
- Hoja de Vida (HV) o Curriculum Vitae. -> OUTPUT: 22_hoja_de_vida
- Formatos para contratación (autorizaciones, tratamiento datos). -> OUTPUT: 23_formatos_para_la_contratacion

### REGLA DE AMBIGÜEDAD (ULTRA ESTRICTO):
Cualquier nombre que contenga palabras genéricas como "curso", "diploma", "certificado", "certificacion", "acta", "soporte", "copia", "doc", "scan", "foto" o nombres de archivos numéricos/ambiguos DEBE SER RECHAZADO, A MENOS QUE el nombre especifique de forma 100% inconfundible la categoría exacta (por ejemplo: "antecedentes_policia.pdf" o "cedula_juan.pdf"). Si hay la más mínima duda o falta de claridad, RESPONDE SIEMPRE: REVISAR_CONTENIDO.

### REGLAS DE RESPUESTA (ESTRICTO):
1. Evalúa ÚNICAMENTE el texto del nombre del archivo que se te proporciona.
2. Si el nombre sugiere claramente y SIN AMBIGÜEDAD una categoría, responde ÚNICAMENTE con la clave del OUTPUT (ejemplo: 01_documento_id).
3. Si el nombre es ambiguo, genérico o no coincide con claridad absoluta, responde exactamente: REVISAR_CONTENIDO
4. PROHIBIDO usar comillas, comillas simples, espacios al inicio o al final, saltos de línea, explicaciones o formato markdown. Devuelve SOLO la clave limpia.
"""

PROMPT_POR_CONTENIDO = """
Tu única tarea es analizar exhaustivamente el CONTENIDO VISUAL / TEXTUAL de este documento y clasificarlo dentro de UNA de las siguientes categorías predefinidas.

### LISTA DE CATEGORÍAS Y OUTPUTS PERMITIDOS:
- Documento de Identidad (Cédula de ciudadanía, cédula de extranjería, pasaporte, PPT). NO incluir licencias de conducción ni libretas militares. -> OUTPUT: 01_documento_id
- Contrato de Trabajo, contrato laboral firmado, otrosi o adendas. -> OUTPUT: 02_contrato_laboral
- Certificado o constancia del Curso de Ética (Códigos de ética, SAGRILAFT, conducta). -> OUTPUT: 03_curso_etica
- Certificado o constancia del Curso de Transparencia o Anticorrupción (PTEE, anticorrupción). -> OUTPUT: 04_curso_transparencia
- Certificado o constancia del Curso de Cultura Organizacional (Inducción corporativa, SGSST, clima organizacional). -> OUTPUT: 05_curso_cultura
- Resultados o informes de Pruebas Psicotécnicas. -> OUTPUT: 06_pruebas_psicotecnicas
- Formato o informe de Verificación de Referencias. -> OUTPUT: 07_verificacion_referencias
- Certificado de afiliación a ARL (Riesgos Laborales). -> OUTPUT: 08_arl
- Certificado de afiliación a CCF (Caja de Compensación Familiar). -> OUTPUT: 09_ccf
- Concepto de Examen Médico Ocupacional o de Ingreso. -> OUTPUT: 10_examen_medico_ingreso
- Certificado de Antecedentes de la Policía Nacional. -> OUTPUT: 11_antecedente_policia
- Certificado de Antecedentes de la Procuraduría General. -> OUTPUT: 12_antecedente_procuraduria
- Certificado de Antecedentes Fiscales de la Contraloría. -> OUTPUT: 13_antecedente_contraloria
- Certificación bancaria o soporte de Cuenta Bancaria para pago de nómina. -> OUTPUT: 14_cuenta_bancaria
- Certificado de afiliación o historia de Pensiones (Protección, Porvenir, Colpensiones, etc.). -> OUTPUT: 15_pension
- Certificado o constancia de afiliación a Cesantías. -> OUTPUT: 16_cesantias
- Certificado de afiliación a EPS (Sura, Sanitas, Compensar, etc.) o ADRES. -> OUTPUT: 17_eps
- Cartas o soportes generales de Referencias. -> OUTPUT: 18_referencias
- Títulos de estudio, diplomas, actas de grado o certificados académicos (Colegios, Universidades, SENA, diplomados técnicos/profesionales). -> OUTPUT: 19_estudios
- Carta de Referencia Personal o familiar. -> OUTPUT: 20_referencia_personal
- Certificado Laboral o Referencia Laboral de empleos anteriores (Certificaciones de empresas sobre cargos y fechas). -> OUTPUT: 21_referencia_laboral
- Hoja de Vida (HV) o Curriculum Vitae. -> OUTPUT: 22_hoja_de_vida
- Formatos diligenciados para la contratación (autorizaciones, tratamiento de datos, listas de chequeo). -> OUTPUT: 23_formatos_para_la_contratacion

### INSTRUCCIONES DE LECTURA Y PREVENCIÓN DE ERRORES:
1. LEE DETENIDAMENTE el título principal, encabezados, logos y el texto del cuerpo del documento antes de clasificar.
2. DISTINCIÓN CRÍTICA ENTRE "ESTUDIOS" Y "CURSOS CORPORATIVOS":
   - Títulos universitarios, actas de grado, bachillerato, SENA o diplomados educativos van a "19_estudios".
   - Certificados de capacitaciones empresariales, inducciones corporativas, cursos de ética, SAGRILAFT o transparencia NO son estudios formales; pertenecen a "03_curso_etica", "04_curso_transparencia" o "05_curso_cultura".
3. No asumas la categoría basándote en la primera palabra que veas; analiza el propósito global del documento.

### REGLAS DE RESPUESTA (ESTRICTO):
1. Si coincide claramente con alguna categoría, responde ÚNICAMENTE con la clave del OUTPUT (ejemplo: 01_documento_id).
2. Si el documento NO coincide con ninguna categoría o es totalmente ilegible, responde exactamente: NO_CLASIFICADO
3. PROHIBIDO redactar explicaciones, justificaciones, saludos, comillas, saltos de línea o formato markdown. Devuelve SOLO la clave limpia.
"""
