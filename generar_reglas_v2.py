"""Genera reglas_v2.ods — catálogo plano con descripciones enriquecidas e id_requisito."""

import pandas as pd
from pathlib import Path

# ─── Datos: (tipo de documento, descripcion tipo de documento, id_requisito, Descripcion requisito, output) ───
filas = [

    # ── 1. Documento de identidad ──
    ("documento_id",
     "Tarjeta pequeña horizontal (tamaño carné), frente y reverso, con foto de rostro y solo datos mínimos de identidad: cédula de ciudadanía o PPT. Nunca formulario, tabla o texto corrido, aunque mencione cédula.",
     "documento_id_tipo",
     "tipo de documento de identidad: verificar si es cédula de ciudadanía (CC) o permiso por protección temporal (PPT)",
     '"CC" o "PPT"'),

    # ── 2. Contrato laboral (2 requerimientos) ──
    ("contrato_laboral",
     "Contrato de trabajo entre empleador y empleado: cargo, salario, horario, tipo de contrato, fecha de inicio, y firmas de ambas partes al iniciar la relación laboral.",
     "contrato_laboral_fecha",
     "fecha de inicio de labores pactada en el contrato de trabajo",
     "formato:aaaammdd"),

    ("contrato_laboral",
     "Contrato de trabajo entre empleador y empleado: cargo, salario, horario, tipo de contrato, fecha de inicio, y firmas de ambas partes al iniciar la relación laboral.",
     "contrato_laboral_firma",
     "correctamente firmado: los espacios para la firma del trabajador/candidato deben tener firma autógrafa, manuscrita o digital visible",
     '"SI" o "NO"'),

    # ── 3. Curso ética ──
    ("curso_etica",
     "Certificado individual del curso 'código de ética y conducta - SAGRILAFT' otorgado por Salesland al empleado. Si el archivo contiene varios certificados juntos, no es esta categoría sino un compilado.",
     "curso_etica_titulo",
     "corresponde al titulo del curso: verificar que diga 'código de ética' o 'código de ética y conducta'",
     "STRING"),

    # ── 4. Curso cultura ──
    ("curso_cultura",
     "Certificado individual del curso 'inducción cultura' otorgado por Salesland al empleado. Si el archivo contiene varios certificados juntos, no es esta categoría sino un compilado.",
     "curso_cultura_titulo",
     "corresponde al titulo del curso: verificar que diga 'inducción cultura' o 'cultura salesland'",
     "STRING"),

    # ── 5. Curso transparencia ──
    ("curso_transparencia",
     "Certificado individual del curso 'programa de transparencia y ética empresarial' otorgado por Salesland al empleado. Si el archivo contiene varios certificados juntos, no es esta categoría sino un compilado.",
     "curso_transparencia_titulo",
     "corresponde al titulo del curso: verificar que diga 'programa de transparencia' o 'ética empresarial'",
     "STRING"),

    # ── 6. Curso otro ──
    ("curso_otro",
     "Certificado individual de un curso distinto a ética, cultura o transparencia, otorgado por Salesland al empleado. Si el archivo contiene varios certificados juntos, es un compilado.",
     "curso_otro_titulo",
     "corresponde al titulo del curso: extraer el nombre del curso realizado",
     "STRING"),

    # ── 7. Pruebas psicotécnicas ──
    ("pruebas_psicotecnicas",
     "Informe de resultados de pruebas psicotécnicas aplicadas al candidato: evalúa aptitudes, personalidad y competencias mediante gráficos, escalas o interpretaciones emitidas por un psicólogo o evaluador.",
     None, None, None),

    # ── 8. Verificación de referencias ──
    ("verificacion_referencias",
     "Formato interno de verificación de referencias personales y laborales del candidato: datos de contacto, relación con el aspirante y recomendación del referente, diligenciado por personal de selección.",
     None, None, None),

    # ── 9. ARL ──
    ("arl",
     "Certificado de afiliación a una ARL (Administradora de Riesgos Laborales), donde consta el nombre de la aseguradora, el tipo de riesgo asignado y el estado activo de la afiliación.",
     None, None, None),

    # ── 10. CCF ──
    ("ccf",
     "Certificado de afiliación o radicación de trámites emitido por una Caja de Compensación Familiar (CCF), con el nombre de la caja, el número de radicado y la fecha del trámite.",
     None, None, None),

    # ── 11. Examen médico de ingreso ──
    ("examen_medico_ingreso",
     "Certificado de examen médico ocupacional de preingreso, con resultados de la valoración física, recomendaciones médicas, y el concepto de aptitud laboral emitido por la entidad de salud ocupacional.",
     None, None, None),

    # ── 12. Antecedente policía ──
    ("antecedente_policia",
     "Certificación de Antecedentes Penales y Requerimientos Judiciales, expedida por la Policía Nacional de Colombia, que confirma si la persona tiene o no asuntos pendientes con la justicia colombiana.",
     "antecedente_policia_resultado",
     "tener o no antecedentes: verificar si registra antecedentes penales o requerimientos judiciales pendientes en la Policía Nacional",
     '"SI" o "NO"'),

    # ── 13. Antecedente procuraduría ──
    ("antecedente_procuraduria",
     "Certificado de Antecedentes (SIRI: sanciones e inhabilidades), expedido por la Procuraduría General de la Nación, que confirma si la persona registra sanciones o inhabilidades disciplinarias vigentes.",
     "antecedente_procuraduria_resultado",
     "tener o no antecedentes: verificar si registra sanciones o inhabilidades disciplinarias vigentes en la Procuraduría",
     '"SI" o "NO"'),

    # ── 14. Antecedente contraloría ──
    ("antecedente_contraloria",
     "Certificado de Responsabilidad Fiscal (SIBOR: boletín de responsables fiscales), expedido por la Contraloría General de la República, que confirma si la persona está reportada como responsable fiscal.",
     "antecedente_contraloria_resultado",
     "tener o no antecedentes: verificar si está reportada como responsable fiscal en la Contraloría",
     '"SI" o "NO"'),

    # ── 15. Cuenta bancaria ──
    ("cuenta_bancaria",
     "Certificación bancaria de vinculación emitida a solicitud del titular: entidad financiera, tipo y número de producto, y estado de vigencia. No es un extracto ni un estado de cuenta.",
     "cuenta_bancaria_numero",
     "extraer el numero de cuenta bancaria completo",
     "entero sin espacios ni puntos"),

    # ── 16. Pensión o cesantías ──
    ("pension_o_cesantias",
     "Certificado emitido por una entidad afiliadora a pensiones o cesantías, que confirma que la persona está afiliada al Fondo de Pensiones, al de Cesantías, o a ambos.",
     "pension_o_cesantias_tipo",
     "identificar a qué fondo(s) corresponde la afiliación: PENSIONES, CESANTIAS o PENSIONES Y CESANTIAS",
     '"PENSIONES" o "CESANTIAS" o "PENSIONES Y CESANTIAS"'),

    # ── 17. EPS o ADRES ──
    ("eps_o_adres",
     "Formulario o certificado de afiliación a EPS o consulta ADRES: régimen, tipo de cotizante, EPS y estado. Incluye tanto solicitudes/formularios de afiliación como certificados ya confirmados. Nunca formato de carné.",
     None, None, None),

    # ── 18. Estudios ──
    ("estudios",
     "Diploma o acta de grado, emitido por una institución educativa, que confiere un título académico a la persona (bachiller, técnico, tecnólogo, o profesional) en cualquier nivel.",
     "estudios_bachillerato",
     "verificar si el título obtenido es de bachillerato o secundaria (BACHILLERATO) o de otro nivel superior (OTRO)",
     '"BACHILLERATO" o "OTRO"'),

    # ── 19. Referencia personal ──
    ("referencia_personal",
     "Carta redactada por una persona natural (no una empresa) que certifica conocer al recomendado desde hace tiempo y da fe de su comportamiento personal, con firma del referente.",
     None, None, None),

    # ── 20. Referencia laboral ──
    ("referencia_laboral",
     "Certificación laboral emitida por una empresa ya finalizada la relación: cargo, modalidad de contratación, fechas de inicio y fin del vínculo, y contacto de la entidad. Sin firma del trabajador.",
     None, None, None),

    # ── 21. Hoja de vida ──
    ("hoja_de_vida",
     "Documento redactado por el propio candidato para postularse a un empleo: perfil profesional, experiencia laboral, educación y contacto. No es un formulario de empresa ni un carné de identidad.",
     None, None, None),

    # ── 22. Formatos para la contratación (2 requerimientos) ──
    ("formatos_para_la_contratacion",
     "Paquete de varios formatos internos de Salesland diligenciados por el postulante: antecedentes de salud, autorización de descuentos, tratamiento de datos, declaración de reportes negativos, ficha del candidato, concepto de entrevista.",
     "formatos_para_la_contratacion_hojas",
     "verificar que el paquete contenga como mínimo 9 hojas en total",
     '"SI" o "NO"'),

    ("formatos_para_la_contratacion",
     "Paquete de varios formatos internos de Salesland diligenciados por el postulante: antecedentes de salud, autorización de descuentos, tratamiento de datos, declaración de reportes negativos, ficha del candidato, concepto de entrevista.",
     "formatos_para_la_contratacion_firmas",
     "verificar que las 9 hojas estén debidamente diligenciadas y firmadas por el candidato en los espacios correspondientes cuando aplique",
     '"SI" o "NO"'),

    # ── 23. Informe DataCrédito (2 requerimientos) ──
    ("informe_datacredito",
     "Reporte de historia crediticia emitido por DataCrédito u otra central de riesgo: créditos vigentes y cerrados, tendencias de endeudamiento, moras y saldos pendientes del titular.",
     "informe_datacredito_moras",
     "verificar si la persona registra moras o saldos en mora vigentes",
     '"SI" o "NO"'),

    ("informe_datacredito",
     "Reporte de historia crediticia emitido por DataCrédito u otra central de riesgo: créditos vigentes y cerrados, tendencias de endeudamiento, moras y saldos pendientes del titular.",
     "informe_datacredito_demandas",
     "verificar si la persona registra demandas o procesos ejecutivos vigentes",
     '"SI" o "NO"'),

    # ── 24. Informe bases ──
    ("informe_bases",
     "Reporte de consulta en múltiples bases de datos (listas LAFT, antecedentes judiciales/fiscales, historial académico y tributario) en un documento consolidado. Si certifica una sola entidad (Policía, Procuraduría, Contraloría), usar esa categoría.",
     "informe_bases_inconveniente",
     "verificar si la persona tiene algún inconveniente o reporte negativo que le impida ser contratado",
     '"SI" o "NO"'),

    # ── 25. Visita domiciliaria ──
    ("visita_domiciliaria",
     "Informe de visita domiciliaria realizada al hogar del candidato: entorno sociofamiliar, condición socioeconómica, estado habitacional, registro fotográfico de la vivienda, y concepto final de idoneidad.",
     None, None, None),

    # ── 26. Acuerdo de pago ──
    ("acuerdo_de_pago",
     "Acuerdo de pago de deudas firmado por la persona, donde se compromete a cancelar un monto específico en cuotas o plazos definidos ante la entidad acreedora.",
     "acuerdo_de_pago_firma",
     "verificar si el acuerdo está firmado explícitamente por quien tiene la deuda",
     '"SI" o "NO"'),

    # ── 27. Checklist documentos ──
    ("checklist_documentos",
     "Tabla interna de RRHH con nombres de documentos en una columna y casillas SI/N.A. para marcar entregados. Es el control de la carpeta, nunca uno de los documentos que lista.",
     None, None, None),

    # ── 28. Manual de funciones ──
    ("manual_de_funciones",
     "Documento interno de la empresa que describe un cargo: nombre, nivel, área, jefe inmediato, funciones y competencias. No es un contrato laboral, es información unilateral del cargo, no un acuerdo firmado por ambas partes.",
     None, None, None),

    # ── 29. Compilado ──
    ("compilado",
     "Documento que reúne varios archivos de categorías DISTINTAS entre sí (ej. cédula y certificado bancario juntos). Si todos los documentos son del mismo tipo (ej. varias certificaciones laborales), usa esa categoría, no esta.",
     None, None, None),

    # ── 30. Otros ──
    ("otros",
     "Documento que no encaja claramente en ninguna categoría anterior. Es una respuesta válida y frecuente, no un último recurso — úsala con confianza ante cualquier duda razonable.",
     "otros_comentario",
     "hacer un comentario explicativo sobre qué tipo de documento puede ser",
     'string entre comillas "comentario"'),
]

# ─── Construir DataFrame y guardar ───

columnas = [
    "tipo de documento",
    "descripcion tipo de documento",
    "id_requisito",
    "Descripcion requisito",
    "output"
]

df = pd.DataFrame(filas, columns=columnas)

ruta = Path(__file__).parent / "reglas_v2.ods"
df.to_excel(ruta, engine="odf", sheet_name="Hoja 1", index=False)

# ─── Resumen ───

tipos_unicos = df["tipo de documento"].nunique()
total_filas = len(df)
con_req = df["Descripcion requisito"].notna().sum()
sin_req = df["Descripcion requisito"].isna().sum()

print(f"✓ Generado: {ruta}")
print(f"  {tipos_unicos} tipos de documento")
print(f"  {total_filas} filas totales ({con_req} con requerimiento, {sin_req} sin requerimiento)")
