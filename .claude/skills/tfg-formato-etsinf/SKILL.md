---
name: tfg-formato-etsinf
description: Normativa oficial de estructura y formato de la memoria de TFG en la ETSINF (UPV), extraida del documento oficial "Estructura y Contenidos Recomendados". Usar SIEMPRE al redactar o revisar cualquier capitulo de la memoria del TFG.
---

# Formato de memoria TFG — ETSINF (UPV)

Fuente: documento oficial de la ETSINF "Trabajo Fin de Grado — Estructura y
Contenidos Recomendados" (https://www.upv.es/entidades/etsinf/wp-content/uploads/2024/02/EstucturayContenidodeunTFGUltimaversion6_3_19.pdf)
y pagina oficial de TFG de la escuela (https://www.upv.es/entidades/etsinf/).

## Reglas globales

- **Plantilla oficial obligatoria**: todos los TFG de la ETSINF deben seguir
  la plantilla http://www.inf.upv.es/www/etsinf/es/plantilla-tfg/
- **Extension**: entre **50 y 100 paginas sin contar anexos**.
- **Antiplagio**: la memoria debe pasar TURNITIN y el resultado se sube a
  EBRON al depositar (via PoliformaT).
- **Idiomas del resumen**: al menos **ingles Y (español o valenciano)**;
  pueden presentarse los tres.
- El lector objetivo es un **profesional informatico NO especialista** en la
  materia del TFG (el tribunal puede venir de areas diversas). No
  sobrestimar la familiaridad del lector con el tema.

## Partes iniciales (antes de los capitulos)

| Parte | Caracter | Reglas |
|---|---|---|
| Portada | Obligatorio | Sin numeracion o con numeros romanos aparte. |
| Titulo | Obligatorio | <10 palabras, sin abreviaturas ni acronimos; debe coincidir con el aprobado por la Comision Academica. |
| Subtitulo | Opcional | Aclara la parte desarrollada si el TFG es parte de una obra mayor. |
| Autor/a + curso academico | Obligatorio | Nombre completo + convocatoria de defensa. |
| Tutor y cotutores | Obligatorio | Nombre y apellidos; ambos si hay dos; director/a experimental si aplica. |
| Dedicatoria | Opcional | |
| Agradecimientos | Opcional | **Obligatorio** mencionar la financiacion si el trabajo fue financiado (proyecto/beca). |
| Resumen | Obligatorio | **200–500 palabras**, autocontenido (sin referencias a paginas/capitulos, normalmente sin citas). Debe contener: problema, metodologia, herramientas, resultados y conclusiones. Publico: la parte mas leida. |
| Palabras clave | Muy recomendable | **3 a 10**, pueden ser compuestas. |
| Prefacio/prologo | Opcional | Solo si se desea ampliar el resumen. |
| Indice de contenido | Obligatorio | Nivel 3 maximo (excepcionalmente 4). |
| Indice de tablas e ilustraciones | Opcional (habitual) | Una lista de tablas y otra de ilustraciones, con titulo y pagina. |
| Definiciones, abreviaturas y acronimos | Recomendable | Diccionario comun; junto al glosario si existe. |

## Capitulos del cuerpo (estructura recomendada)

Es una recomendacion: segun la naturaleza del TFG (desarrollo software,
arquitectura de sistemas, etc.) se puede prescindir de secciones o anadir
otras. Para este proyecto (desarrollo + arquitectura de sistemas) aplican
practicamente todas.

1. **Introduccion** (muy recomendable) — exponer el problema global de forma
   sencilla y holistica; prosa que motive a seguir leyendo. Subapartados:
   - **Motivacion** (recomendable) — por que este tema; puede dividirse en
     personal (1a persona admisible) y profesional (3a persona).
   - **Objetivos** (muy recomendable) — generales → especificos, ordenados
     por relevancia; **en infinitivo, concretos, factibles y medibles**. La
     valoracion del TFG se hace contra estos objetivos: deben casar con
     Resultados y Conclusiones.
   - **Impacto esperado** (recomendable) — ventajas por tipo de usuario;
     relacionar con los **ODS** (Objetivos de Desarrollo Sostenible).
   - **Metodologia** (recomendable) — pasos para cumplir los objetivos.
   - **Estructura** (muy recomendable) — indice comentado (max nivel 2),
     incluyendo contenido de anexos y aviso de que existe glosario.
   - **Colaboraciones** (obligatorio si aplica) — que hizo cada miembro.
   - **Convenciones** (recomendable) — p.ej. codigo en courier cursiva,
     extranjerismos en cursiva, citas textuales entrecomilladas.
2. **Estado del arte** (muy recomendable) — tambien "Contexto Tecnologico".
   Aplicaciones existentes iguales/parecidas, evolucion historica,
   alternativas. Aqui se concentra el grueso de las referencias. Videos y
   webs de producto → **notas al pie**, no referencias bibliograficas.
   - **Critica al estado del arte** — fallos/lagunas que justifican el TFG.
   - **Propuesta** — que espacio llena este trabajo; que lo diferencia.
3. **Analisis del problema** (muy recomendable):
   - Especificacion de requisitos y/o modelado conceptual con **tecnicas
     estandar** (plantillas de requisitos, casos de uso, UML).
   - Analisis de la seguridad (recomendable).
   - Analisis energetico o de eficiencia algoritmica (recomendable).
   - Analisis del marco legal y etico (recomendable): proteccion de datos,
     propiedad intelectual/licencias, otros aspectos legales (ENI/ENS si
     aplica), etica.
   - Analisis de riesgos (recomendable): por riesgo → tipo, impacto,
     medidas de mitigacion.
   - Identificacion y analisis de soluciones posibles (muy recomendable) —
     pros/contras, criterio de seleccion. Mensaje: trabajo de ingeniero que
     evalua alternativas.
   - Solucion propuesta (muy recomendable) — en que consiste, fases,
     implantacion y validacion prevista.
   - Plan de trabajo (recomendable) — fases, horas-persona, desviaciones
     reales y reflexion critica sobre la estimacion.
   - Presupuesto (recomendable) — recursos humanos y materiales (hw/sw +
     horas-hombre).
4. **Diseño de la solucion** (muy recomendable):
   - **Arquitectura del sistema** — grandes bloques/subsistemas, patron
     arquitectonico, diagrama de bloques y/o UML de componentes/despliegue.
   - **Diseño detallado** — clases/modulos, relaciones, diseño de BD,
     estructura de directorios.
   - **Tecnologia utilizada** — herramientas/frameworks, alternativas
     valoradas, coste de aprendizaje (puede ser capitulo aparte).
5. **Desarrollo de la solucion propuesta** (muy recomendable) — de la
   propuesta a la solucion final: problemas, decisiones, particularidades.
   **Poco codigo fuente** en la memoria: solo fragmentos relevantes,
   novedosos o criticos, comentados; el resto a anexos si procede.
6. **Implantacion** (muy recomendable) — puesta en marcha/produccion del
   sistema desarrollado.
7. **Pruebas** (muy recomendable) — verificacion (funciona correctamente),
   validacion con usuario (hace lo esperado), y pruebas de carga/eficiencia.
8. **Conclusiones** (obligatorio en la practica) — concordancia con los
   objetivos iniciales (todo lo concluido debe aparecer en Objetivos); que
   se ha alcanzado; que se ha aprendido; problemas y como se resolvieron;
   errores y como evitarlos. **NO repetir los resultados** ni ir mas alla
   de los objetivos.
   - **Relacion del trabajo desarrollado con los estudios cursados**
     (OBLIGATORIO) — que asignaturas/conocimientos se aplicaron; que
     **competencias transversales** se pusieron en practica.
9. **Trabajos futuros** (opcional) — flecos, lineas nuevas, ampliaciones; y
   caminos por los que NO conviene seguir, con razones.
10. **Referencias** (obligatorio) — ver reglas abajo.

## Partes finales

- **Anexos** (opcional): detalles tecnicos, manual de usuario, codigo,
  material descartado con interes. Nada imprescindible para entender la
  memoria.
- **Glosario** (recomendable): terminos y acronimos del area para lector no
  especialista. Avisar de su existencia en Introduccion→Estructura.

## Reglas de referencias (obligatorias)

- Formato de citacion **estandar**; la guia oficial recomienda
  **ISO 690-2010** (la plantilla o el tutor pueden fijar IEEE, tambien
  aceptado en la escuela — confirmar con el tutor antes de fijar uno).
- **Toda referencia de la bibliografia debe citarse al menos una vez en el
  texto, y toda cita del texto debe existir en la bibliografia.**
- Webs de fabricante/producto y videos → **notas al pie** (la primera vez
  que aparecen), NO entradas bibliograficas.
- No abusar de referencias a paginas web: la bibliografia es para libros,
  articulos y revistas (electronicos o no).
- Referenciar en el texto todas las figuras, imagenes y tablas incluidas.
- No referenciar conceptos basicos de la carrera (ni Wikipedia a cada
  palabra); si referenciar articulos serios al introducir algoritmos o
  tecnologias especificas.

## Errores tipicos que hay que evitar

- Titulo con acronimos o >10 palabras.
- Resumen con referencias o que remite a capitulos.
- Objetivos vagos, no medibles o que no casan con las Conclusiones.
- Repetir los resultados en las Conclusiones.
- Bibliografia = coleccion de enlaces web.
- Figuras sin numerar, sin pie o sin citar en el texto.
- Olvidar la seccion obligatoria "Relacion del trabajo con los estudios
  cursados" (con competencias transversales).
- Indice con mas de 3-4 niveles.
