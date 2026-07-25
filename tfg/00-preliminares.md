# Preliminares

<!-- Este fichero contiene las partes previas al cuerpo de la memoria.
     No computa en la extensión (50-100 págs sin anexos). El alumno debe
     trasvasarlo a la plantilla oficial ETSINF. -->

## Portada

| Campo | Valor |
|---|---|
| Título | Plataforma de escritorios remotos por navegador para laboratorios docentes |
| Subtítulo | Diseño, desarrollo e implantación con virtualización ligera LXD, Apache Guacamole y FastAPI |
| Autor/a | [RELLENAR: nombre completo del alumno] |
| Tutor/a | [RELLENAR: nombre y apellidos; cotutor/a si lo hay] |
| Titulación | [RELLENAR: Grado en Ingeniería Informática, ETSINF-UPV] |
| Curso académico / convocatoria | [RELLENAR: 2025-2026, convocatoria de defensa] |

<!-- Verificación: título de 9 palabras, sin acrónimos (LXD/FastAPI van al
     subtítulo, permitido). [RELLENAR: confirmar que coincide con el título
     aprobado por la Comisión Académica antes del depósito]. -->

## Agradecimientos

[RELLENAR: opcional. Obligatorio únicamente mencionar la financiación si el trabajo la tuvo (proyecto/beca).]

## Resumen

Las prácticas de las titulaciones técnicas dependen de laboratorios físicos con un equipo por puesto, lo que ata el aprendizaje al horario del aula y obliga a mantener decenas de ordenadores homogéneos. Este trabajo aborda ese problema construyendo una plataforma que ofrece a cada alumno un escritorio Linux persistente y aplicaciones web efímeras, accesibles únicamente con un navegador y una dirección de correo electrónico, ejecutados en un único servidor de la institución.

El desarrollo siguió un modelo iterativo e incremental en siete fases, validado en cada paso contra un servidor real, y se apoyó —de forma declarada y supervisada— en una metodología de desarrollo asistida por agentes de inteligencia artificial con revisores críticos. La plataforma integra virtualización ligera con LXD (máquinas virtuales KVM para los escritorios persistentes y contenedores de sistema para las aplicaciones efímeras), Apache Guacamole como pasarela de escritorio remoto en HTML5, Nginx como proxy inverso con puerta de autenticación centralizada, y un orquestador propio desarrollado en FastAPI que implementa la autenticación sin contraseñas mediante enlaces de un solo uso, el aprovisionamiento bajo demanda con una cola de trabajos persistente, las instantáneas de autoservicio con rotación, la destrucción automática por inactividad y una consola web de administración.

El resultado es un sistema desplegable de extremo a extremo con un solo comando sobre un servidor Ubuntu limpio, mediante un instalador dirigido con verificación previa del host. Ningún puerto de escritorio remoto queda expuesto a Internet, el tráfico entre alumnos está aislado por cortafuegos y todo el software empleado es libre, con coste de licencias nulo. La evaluación se presenta como un análisis de cotas que identifica el almacenamiento de los escritorios persistentes —consumido por la retención de instantáneas— como límite dominante de la capacidad actual, y las deudas técnicas quedan documentadas y priorizadas.

Se concluye que la integración propuesta cubre un hueco real entre las plataformas comerciales de escritorio virtual, generalmente sobredimensionadas para el aula y con costes de licencia difíciles de asumir en docencia, y los componentes libres existentes, que solo resuelven partes del problema; su validación con estudiantes reales se propone como primera línea de trabajo futuro.

<!-- Recuento del resumen: ~300 palabras (dentro de 200-500). Sin citas ni remisiones a capítulos. -->

**Palabras clave:** escritorios remotos; virtualización ligera; contenedores; LXD; Apache Guacamole; laboratorios docentes; aprovisionamiento bajo demanda; seguridad web.

## Abstract

Hands-on courses in technical degrees depend on physical laboratories with one computer per seat, which ties learning to classroom hours and requires maintaining dozens of homogeneous machines. This work addresses that problem by building a platform that provides each student with a persistent Linux desktop and ephemeral web applications, accessible with nothing but a web browser and an email address, running on a single institutional server.

Development followed an iterative, incremental model in seven phases, validated at every step against a real server, and relied—openly and under the author's supervision—on an AI-assisted development methodology based on specialised agents and critical reviewers. The platform integrates lightweight virtualisation with LXD (KVM virtual machines for the persistent desktops and system containers for the ephemeral applications), Apache Guacamole as an HTML5 remote-desktop gateway, Nginx as a reverse proxy with a centralised authentication gate, and a purpose-built orchestrator developed with FastAPI that implements passwordless authentication through single-use links, on-demand provisioning backed by a persistent job queue, self-service snapshots with rotation, automatic destruction of idle instances, and a web administration console.

The result is a system deployable end-to-end with a single command on a clean Ubuntu server, through a guided installer with host preflight checks. No remote-desktop port is exposed to the Internet, traffic between students is isolated by firewall rules, and the whole stack is free and open-source software with zero licensing cost. The evaluation is presented as an analysis of capacity bounds that identifies the storage of the persistent desktops—consumed by snapshot retention—as the dominant limit of the current deployment, and the remaining technical debts are documented and prioritised.

The work concludes that the proposed integration fills a real gap between commercial virtual-desktop platforms—generally oversized for the classroom and costly to license in an educational setting—and existing open-source components, which only solve parts of the problem; validating the platform with real students is proposed as the first line of future work.

**Keywords:** remote desktops; lightweight virtualisation; containers; LXD; Apache Guacamole; teaching laboratories; on-demand provisioning; web security.

## Índice de contenido (previsto)

<!-- La plantilla oficial genera el índice automáticamente; esta versión
     sirve de guía de trasvase. Máximo nivel 3. -->

1. Introducción — 1.1 Motivación · 1.2 Objetivos · 1.3 Impacto esperado y Objetivos de Desarrollo Sostenible · 1.4 Metodología · 1.5 Estructura de la memoria · 1.6 Convenciones
2. Estado del arte — 2.1 Escritorios remotos e infraestructura de escritorio virtual · 2.2 Virtualización ligera: máquinas virtuales y contenedores · 2.3 Laboratorios virtuales docentes · 2.4 Crítica al estado del arte · 2.5 Propuesta
3. Análisis del problema — 3.1 Especificación de requisitos · 3.2 Casos de uso · 3.3 Análisis de seguridad · 3.4 Marco legal y ético · 3.5 Análisis de riesgos · 3.6 Identificación y análisis de soluciones posibles · 3.7 Solución propuesta y plan de trabajo · 3.8 Presupuesto
4. Diseño de la solución — 4.1 Arquitectura del sistema · 4.2 Diseño detallado (4.2.1 Módulos del orquestador · 4.2.2 Diseño de la base de datos · 4.2.3 Ciclo de vida de una instancia · 4.2.4 Contrato de personalización con cloud-init) · 4.3 Diseño de seguridad aplicado · 4.4 Tecnología utilizada
5. Desarrollo de la solución propuesta — 5.1 Organización del desarrollo · 5.2 Problemas encontrados y soluciones · 5.3 Decisiones de implementación destacadas
6. Implantación — 6.1 Requisitos del host y verificación previa · 6.2 El instalador dirigido · 6.3 Operación del sistema · 6.4 Desinstalación y límites de reversión
7. Pruebas — 7.1 Estrategia de verificación · 7.2 Verificación funcional de extremo a extremo · 7.3 Análisis de capacidad y eficiencia · 7.4 Validación con usuarios
8. Conclusiones — 8.1 Conclusiones sobre los objetivos · 8.2 Relación del trabajo desarrollado con los estudios cursados
9. Trabajos futuros — 9.1 Líneas de evolución priorizadas · 9.2 Un camino desaconsejado
10. Referencias

Anexos: A1 Glosario de términos y acrónimos · A2 Manual de usuario · A3 Guía de despliegue

## Índice de figuras

- Figura 3.1. Diagrama de casos de uso de la plataforma.
- Figura 3.2. Plan de trabajo real derivado del historial del repositorio.
- Figura 4.1. Arquitectura general de la plataforma: bloques y rutas de enrutado.
- Figura 4.2. Diagrama de despliegue: servicios, redes internas y almacenamiento sobre el host único.
- Figura 4.3. Diagrama de componentes del orquestador.
- Figura 4.4. Máquina de estados de una VM de alumno.
- Figura 5.1. Metodología de desarrollo con agentes especializados y críticos de revisión.
- Figura 6.1. Asistente dirigido de instalación. [RELLENAR: captura]
- Figura 6.2. Portal del alumno tras la implantación. [RELLENAR: captura]
- Figura 6.3. Consola de administración. [RELLENAR: captura]

## Índice de tablas

- Tabla 2.1. Comparativa de soluciones de escritorio remoto y entrega de entornos.
- Tabla 3.1. Requisitos funcionales y no funcionales del sistema.
- Tabla 3.2. Modelo de amenazas: amenaza, mitigación y evidencia.
- Tabla 3.3. Análisis de riesgos: tipo, probabilidad, impacto y mitigación.
- Tabla 3.4. Alternativas evaluadas por decisión estructural.
- Tabla 3.5. Presupuesto estimado del proyecto.
- Tabla 4.1. Servicios, puntos de escucha y orígenes permitidos.
- Tabla 4.2. Entidades de la base de datos del orquestador.
- Tabla 4.3. Pila tecnológica y alternativas evaluadas.
- Tabla 6.1. Comprobaciones del preflight del instalador.
- Tabla 7.1. Criterios de aceptación de extremo a extremo.
- Tabla 7.2. Cotas de capacidad con su límite dominante.

## Índice de fragmentos de código

- Fragmento 5.1. Re-comprobación anti-TOCTOU del reaper.
- Fragmento 5.2. Envoltorio asíncrono y sin shell de la CLI de LXD.
- Fragmento 5.3. Lanzamiento de la VM con cloud-init por entrada estándar.
