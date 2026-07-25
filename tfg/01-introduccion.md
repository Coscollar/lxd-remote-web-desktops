# Capítulo 1. Introducción

Este capítulo presenta el problema que aborda el trabajo —el acceso de los estudiantes a entornos de prácticas Linux fuera del aula—, formula los objetivos contra los que se evaluará el resultado, expone el impacto esperado y la metodología seguida, y describe la estructura del resto de la memoria.

## 1.1 Motivación

Las asignaturas con componente práctico de las titulaciones de informática dependen de laboratorios equipados: aulas con un ordenador por puesto, mantenidas por los servicios técnicos del centro, con un sistema operativo y un conjunto de herramientas homogéneos. Este modelo presenta limitaciones conocidas: el acceso queda ligado al horario y al espacio físico del aula, de modo que el alumno que quiere continuar una práctica por la tarde o desde casa debe reproducir el entorno por su cuenta, con las diferencias de configuración y los errores que ello introduce; y mantener decenas de equipos idénticos supone un coste recurrente de administración, ya que cualquier cambio de software exige reinstalar la imagen de disco o reconfigurar todos los puestos. <!-- fuente: [ELABORAR: contexto docente general, sin cifras inventadas] -->

Las alternativas habituales trasladan el problema en lugar de resolverlo. Pedir al alumno que instale una máquina virtual en su portátil presupone un equipo con recursos suficientes y le desplaza el trabajo de configuración; contratar escritorios virtuales comerciales o servicios en la nube introduce costes de licencia o de consumo difíciles de asumir para un laboratorio docente, como se analiza en el Capítulo 2.

Este trabajo parte de una observación sencilla: prácticamente cualquier alumno dispone de un navegador web —aunque no necesariamente de un equipo con capacidad para ejecutar máquinas virtuales en local—, y la virtualización ligera permite consolidar múltiples entornos aislados en un único servidor. Sobre esa base se ha construido una plataforma en la que un solo host Ubuntu Server ejecuta, mediante LXD —el gestor de virtualización ligera de Canonical, que administra contenedores y máquinas virtuales bajo una misma interfaz (Anexo A1)—, un escritorio Linux persistente por alumno y aplicaciones web efímeras por laboratorio, accesibles únicamente con un navegador y un correo electrónico. La concentración en un único servidor introduce, como contrapartida, un punto único de fallo y una capacidad acotada; ambos aspectos se cuantifican en los Capítulos 3 y 7. <!-- fuente: README.md:Qué es -->

En el plano personal, este proyecto me permitió unir dos intereses cultivados durante la carrera: la administración de sistemas Linux y la seguridad de las aplicaciones web. Quería comprobar si era capaz de llevar una infraestructura completa —desde el hipervisor hasta la capa de autenticación— a un estado desplegable con un solo comando, y ese reto es el origen de este trabajo. [RELLENAR: ajustar o ampliar la motivación personal del alumno]

## 1.2 Objetivos

El objetivo general del trabajo es el siguiente:

- **OG.** Construir una plataforma que ofrezca a cada alumno un escritorio Linux persistente y aplicaciones web efímeras, accesibles solo con un navegador, sobre un único servidor.

Este objetivo general se desglosa en cinco objetivos específicos, formulados de manera medible:

- **OE1.** Diseñar una arquitectura de acceso web sin exponer ningún puerto de escritorio remoto al exterior (criterio medible: `ss -tlnp` sin 3389/5900/3000/8888 públicos).
- **OE2.** Desarrollar un orquestador de aprovisionamiento bajo demanda con autenticación sin contraseñas (*magic link* + JWT) y ciclo de vida automatizado: snapshots con rotación, auto-destrucción por inactividad y reconciliación segura.
- **OE3.** Extender la plataforma a aplicaciones *stateless* por contenedor con aislamiento de red entre alumnos (criterio: reglas iptables inter-VM, inter-app y app↔VM en DROP).
- **OE4.** Automatizar la implantación completa mediante un instalador único dirigido con verificación previa del host (criterio: despliegue *end-to-end* con un solo comando sobre Ubuntu Server limpio).
- **OE5.** Evaluar la seguridad y la escalabilidad de la solución, documentando cotas cuantitativas y deudas técnicas.

Para el lector no especialista conviene precisar la terminología de estos enunciados, que se desarrolla en los Capítulos 2 y 4 y en el glosario (Anexo A1): un *magic link* es un enlace de un solo uso enviado por correo que sustituye a la contraseña; un JWT es un testigo de sesión firmado; un *snapshot* es una instantánea restaurable del estado de una máquina; una aplicación *stateless* (sin estado) no conserva datos entre sesiones; la "reconciliación" contrasta el inventario de la base de datos con el estado real del hipervisor; y los puertos citados en OE1 corresponden a los escritorios remotos (RDP 3389, VNC 5900) y a las aplicaciones de ejemplo (3000, 8888).

Estos objetivos constituyen el contrato de evaluación de la memoria: el Capítulo 8 los retoma uno a uno, indicando su grado de consecución y el capítulo en el que se demuestra.

## 1.3 Impacto esperado y Objetivos de Desarrollo Sostenible

El beneficio de la plataforma se concreta por perfil de usuario. Para el **alumno**, el entorno de prácticas deja de estar atado al aula: puede abrir su escritorio desde cualquier dispositivo con navegador, guardar su trabajo mediante instantáneas y restaurarlo o reiniciarlo de forma autónoma, sin intervención del profesor. <!-- fuente: docs/USO.md:Para el alumno --> Para el **profesor o administrador**, la gestión se reduce a una consola web desde la que matricula alumnos, crea laboratorios y destruye instancias; la autenticación por enlaces de un solo uso elimina la gestión de contraseñas de alumnos. <!-- fuente: docs/USO.md:Para el administrador --> Para la **institución**, un único servidor concentra los entornos que antes exigían un equipo por puesto —dentro de las cotas que cuantifica el Capítulo 7—, con software libre y sin costes de licencia. <!-- fuente: README.md:Qué es, README.md:Cotas -->

El trabajo se alinea con tres Objetivos de Desarrollo Sostenible de la Agenda 2030 (Naciones Unidas, 2015). Contribuye al **ODS 4 (educación de calidad)** porque extiende el acceso a entornos de prácticas configurados más allá del horario y el espacio del aula, condición necesaria para un aprendizaje práctico continuado. Contribuye al **ODS 10 (reducción de las desigualdades)** porque el requisito de hardware del alumno se reduce al mínimo: un estudiante sin ordenador potente accede al mismo escritorio Linux que el resto, ejecutado en el servidor. Y contribuye al **ODS 12 (producción y consumo responsables)** porque consolida en una sola máquina los recursos que de otro modo exigirían un equipo por puesto, con instancias que se destruyen automáticamente cuando dejan de usarse, evitando el consumo de recursos ociosos. <!-- fuente: [ELABORAR: redacción ODS justificada, no listada] -->

## 1.4 Metodología

El desarrollo siguió un modelo **iterativo e incremental organizado en fases** (FASES 0 a 6 en la documentación del proyecto): primero la infraestructura de virtualización y la imagen base del escritorio, después el orquestador de aprovisionamiento con su autenticación, la pasarela web de acceso, la política de ciclo de vida y, por último, el portal de aplicaciones efímeras, la consola de administración y el instalador unificado. Cada fase definió criterios de aceptación verificables antes de pasar a la siguiente. <!-- fuente: docs/DEPLOY.md (FASES), git log -->

Al tratarse de un proyecto de infraestructura —guiones de shell, plantillas YAML y servicios Python que gobiernan un hipervisor—, la validación no se apoyó en una batería de pruebas de integración continua, sino en la **ejecución contra un host LXD real**, comprobando tras cada cambio el estado efectivo del sistema (instancias, redes, puertos expuestos). Esta decisión y sus implicaciones se justifican en el Capítulo 7. <!-- fuente: CLAUDE.md:no lint/typecheck/test -->

Debe declararse, además, que el desarrollo se apoyó en **asistentes de inteligencia artificial generativa** bajo un esquema estructurado: se definieron agentes especializados por dominio (infraestructura LXD, API de aprovisionamiento, pasarela web, autenticación) y agentes críticos de revisión (seguridad, idempotencia, fiabilidad, escalabilidad) cuyas reglas de trabajo se codificaron en ficheros de configuración versionados junto al código. Todo artefacto generado fue revisado, validado contra el host real y asumido por el autor, que mantiene la responsabilidad plena sobre el resultado. Esta forma de trabajo se documenta con detalle en el Capítulo 5. <!-- fuente: .claude/agents/, .claude/skills/, git log jun-2026 --> [RELLENAR: confirmar con el tutor la política UPV de declaración de uso de IA vigente en la convocatoria]

Esta metodología determina la estructura de la memoria: el análisis (Capítulo 3) y el diseño (Capítulo 4) recogen las decisiones previas a cada fase, el desarrollo y la implantación (Capítulos 5 y 6) narran su ejecución iterativa, y las pruebas (Capítulo 7) documentan los criterios de aceptación con los que se validó cada una.

## 1.5 Estructura de la memoria

El resto de la memoria se organiza como sigue:

- El **Capítulo 2 (Estado del arte)** revisa las soluciones existentes de escritorio remoto y virtualización ligera, las critica desde la óptica de un laboratorio docente y sitúa la propuesta.
- El **Capítulo 3 (Análisis del problema)** especifica requisitos y casos de uso, analiza la seguridad, el marco legal y los riesgos, compara las soluciones posibles y presenta la solución elegida, el plan de trabajo y el presupuesto.
- El **Capítulo 4 (Diseño de la solución)** describe la arquitectura del sistema, el diseño detallado de sus módulos y datos, el diseño de seguridad y la tecnología empleada.
- El **Capítulo 5 (Desarrollo de la solución propuesta)** narra cómo se llevó el diseño a la práctica: organización del trabajo —incluida la metodología asistida por agentes—, problemas reales encontrados y decisiones de implementación.
- El **Capítulo 6 (Implantación)** cubre la puesta en producción: requisitos del host, instalador dirigido, operación y desinstalación.
- El **Capítulo 7 (Pruebas)** recoge la estrategia de verificación, las comprobaciones funcionales de extremo a extremo y el análisis de capacidad.
- Los **Capítulos 8 y 9** presentan las conclusiones —incluida la relación del trabajo con los estudios cursados— y los trabajos futuros.
- El **Capítulo 10** recopila las referencias bibliográficas.
- Los **anexos** contienen un glosario de términos (A1), el manual de usuario (A2) y la guía de despliegue (A3). Se advierte al lector de la existencia del glosario: todo término técnico se define en su primera aparición y cuenta con entrada en el Anexo A1.

## 1.6 Convenciones

En toda la memoria se aplican las convenciones siguientes: los comandos, fragmentos de código, nombres de ficheros del repositorio y valores de configuración se escriben en tipografía `monoespaciada`; los extranjerismos no asentados se escriben en *cursiva*; las citas textuales van "entrecomilladas"; las referencias bibliográficas siguen la norma ISO 690-2010 con citas en el texto del tipo (Autor, año), y las páginas web de productos o fabricantes se citan en nota al pie en su primera aparición. Las figuras y tablas se numeran por capítulo (Figura 4.1, Tabla 3.2) y se citan siempre desde el texto; los listados de código se numeran igualmente por capítulo como Fragmentos (Fragmento 5.1). [RELLENAR: confirmar con el tutor el formato de citas; si fija IEEE, se renumeran las citas sin alterar el contenido]

Establecido el problema, los objetivos y el método, el capítulo siguiente sitúa el trabajo en su contexto tecnológico: qué soluciones existen para ofrecer escritorios remotos, qué aportan y qué carencias justifican esta propuesta.
