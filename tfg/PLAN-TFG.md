# PLAN-TFG.md — Guion de la memoria del TFG

> Guion de planificación producido por @tfg-plan para ejecución por @tfg-build.
> Restricción del alumno: **~50 páginas SIN contar anexos** (mínimo de la horquilla ETSINF 50-100).
> Regla de conversión: ~350 palabras/página → cuerpo objetivo ≈ **17.500 palabras**.
> Fecha de planificación: 2026-07-09. Directorio `tfg/` inexistente: planificación desde cero.

---

## 0. Datos de portada [RELLENAR por el alumno]

| Campo | Valor |
|---|---|
| Título | Plataforma de escritorios remotos por navegador para laboratorios docentes |
| Subtítulo | Diseño, desarrollo e implantación con virtualización ligera LXD, Apache Guacamole y FastAPI |
| Autor | [RELLENAR: nombre completo] |
| Tutor/a | [RELLENAR: nombre y apellidos; cotutor si lo hay] |
| Titulación | [RELLENAR: Grado en Ingeniería Informática, ETSINF-UPV] |
| Curso académico / convocatoria | [RELLENAR: 2025-2026, convocatoria de defensa] |

Verificación del título: 9 palabras, sin acrónimos ni abreviaturas (los tecnicismos LXD/FastAPI van al subtítulo, permitido). **Debe coincidir con el aprobado por la Comisión Académica — confirmar con el tutor antes de redactar la portada.**

## 1. Decisiones cerradas del plan

1. **Extensión total del cuerpo: 50-52 páginas** (capítulos 1-10, sin preliminares ni anexos). Los preliminares (portada, resumen, índices, ~5 págs) y los anexos quedan fuera del cómputo. Presupuesto por capítulo en la tabla de §2; @tfg-build debe tratar los máximos como **duros**: si un capítulo se pasa, recorta según la columna "Qué se recorta" de §3.
2. **Formato de citas: ISO 690-2010** (recomendación oficial de la guía ETSINF). **[RELLENAR: confirmar con el tutor**; si fija IEEE, solo cambia el formato de `10-referencias.md`, no el guion]. Webs de producto/fabricante y vídeos → notas al pie la primera vez, nunca bibliografía.
3. **Palabras clave (8):** escritorios remotos; virtualización ligera; contenedores; LXD; Apache Guacamole; laboratorios docentes; aprovisionamiento bajo demanda; seguridad web.
4. **Resumen**: 200-500 palabras, autocontenido, en **español e inglés** (redactar AL FINAL). Estructura obligatoria: problema → metodología → herramientas → resultados → conclusiones.
5. **Objetivos del TFG** (contrato con las Conclusiones; en infinitivo, medibles):
   - **OG.** Construir una plataforma que ofrezca a cada alumno un escritorio Linux persistente y aplicaciones web efímeras, accesibles solo con un navegador, sobre un único servidor.
   - **OE1.** Diseñar una arquitectura de acceso web sin exponer ningún puerto de escritorio remoto al exterior (criterio medible: `ss -tlnp` sin 3389/5900/3000/8888 públicos).
   - **OE2.** Desarrollar un orquestador de aprovisionamiento bajo demanda con autenticación sin contraseñas (magic link + JWT) y ciclo de vida automatizado: snapshots con rotación, auto-destrucción por inactividad y reconciliación segura.
   - **OE3.** Extender la plataforma a aplicaciones stateless por contenedor con aislamiento de red entre alumnos (criterio: reglas iptables inter-VM, inter-app y app↔VM en DROP).
   - **OE4.** Automatizar la implantación completa mediante un instalador único dirigido con verificación previa del host (criterio: despliegue end-to-end con un solo comando sobre Ubuntu Server limpio).
   - **OE5.** Evaluar la seguridad y la escalabilidad de la solución, documentando cotas cuantitativas y deudas técnicas.
6. **Cuerpo vs. anexos** (decisión de recorte para cumplir las 50 págs):
   - **Anexos**: manual de usuario (desde `docs/USO.md`) → A2; guía de despliegue paso a paso y troubleshooting (desde `docs/DEPLOY.md`) → A3; glosario → A1 (anunciado en Introducción→Estructura).
   - **Cuerpo**: solo arquitectura, decisiones y fragmentos mínimos. El esquema completo de BD **no** va a anexo: tabla-resumen de entidades en el cap. 4 y remisión al repositorio (`provision/db.py`). Los listados de comandos largos se remiten a A3 o al repositorio.
   - Estructura de ficheros: la canónica de `.claude/agents/tfg-build.md` (00-10 + A1-A3), sin ficheros nuevos.
7. **Uso de asistentes de IA en la metodología**: el desarrollo usó una arquitectura de agentes/críticos (evidencia: `.claude/agents/`, `.claude/skills/`, commits de junio 2026). Se documenta **honestamente** en Introducción→Metodología y cap. 5, como herramienta bajo supervisión y validación del alumno. [RELLENAR: confirmar con el tutor la política UPV de declaración de uso de IA vigente en la convocatoria.]
8. **Corrección de evidencias**: `AGENTS.md` y `PLAN.md` ya no existen en el repo (consolidación de docs, commit 2026-07-08). Toda evidencia que las skills atribuyen a `AGENTS.md` se toma de **`CLAUDE.md`** (reglas de oro) y de las notas de diseño `DOIN.md` y `Entorno de Laboratorio con LXD.md`. @critic-tfg-veracidad debe aplicar esta sustitución.

## 2. Reparto de extensión (total cuerpo: 51 págs ≈ 17.850 palabras)

| Fichero | Capítulo | Págs | ~Palabras | Responsable |
|---|---|---|---|---|
| 00-preliminares.md | Preliminares | (5, no computan) | — | @tfg-build |
| 01-introduccion.md | 1. Introducción | 5 | 1.750 | @tfg-build |
| 02-estado-del-arte.md | 2. Estado del arte | 6 | 2.100 | @tfg-estado-arte |
| 03-analisis.md | 3. Análisis del problema | 10 | 3.500 | @tfg-analista |
| 04-diseno.md | 4. Diseño de la solución | 10 | 3.500 | @tfg-disenador |
| 05-desarrollo.md | 5. Desarrollo | 6 | 2.100 | @tfg-desarrollo-doc |
| 06-implantacion.md | 6. Implantación | 4 | 1.400 | @tfg-desarrollo-doc |
| 07-pruebas.md | 7. Pruebas | 4 | 1.400 | @tfg-desarrollo-doc |
| 08-conclusiones.md | 8. Conclusiones | 3 | 1.050 | @tfg-build |
| 09-trabajos-futuros.md | 9. Trabajos futuros | 1,5 | 500 | @tfg-build |
| 10-referencias.md | 10. Referencias | 1,5 | — | @tfg-build |
| **Total cuerpo** | | **51** | **~17.300** | |
| A1-glosario.md / A2-manual-usuario.md / A3-guia-despliegue.md | Anexos | 8-12 (no computan) | — | @tfg-build |

Índice: máximo nivel 3 de encabezados en todo el cuerpo.

## 3. Guion capítulo a capítulo

Convenciones del guion: **Evidencia** = `fichero:sección` del repo; **[ELABORAR]** = sin evidencia directa, elaborar declarándolo como estimación/derivación; **[INVESTIGAR]** = requiere búsqueda web con referencias reales (solo @tfg-estado-arte).

### 00-preliminares.md — Preliminares (@tfg-build, redactar AL FINAL, ~5 págs fuera de cómputo)

- Portada con datos de §0 [RELLENAR].
- Resumen ES + Abstract EN (200-500 palabras cada uno, sin citas ni remisiones a capítulos).
- Palabras clave (las 8 de §1.3).
- Índice de contenido (nivel ≤3), índice de figuras y de tablas (desde la lista de §5).
- Agradecimientos [RELLENAR: opcional; obligatorio solo si hubo financiación].

### 01-introduccion.md — Capítulo 1. Introducción (@tfg-build, 5 págs)

| Sección | Contenido | Evidencia / marca |
|---|---|---|
| 1.1 Motivación | Problema: laboratorios docentes atados a aulas físicas y equipos homogéneos; alumnos sin acceso a entornos Linux configurados fuera del aula; coste de mantener un PC por puesto. Motivación personal admite 1ª persona (1 párrafo). | `README.md:Qué es`; [ELABORAR: contexto docente general, 2-3 frases sin cifras inventadas] |
| 1.2 Objetivos | OG + OE1..OE5 de §1.5, literalmente. Aviso de que se retoman uno a uno en el cap. 8. | Este plan |
| 1.3 Impacto esperado y ODS | Beneficio por perfil: alumno (acceso desde cualquier dispositivo, guardado/restauración autónomos), profesor/admin (consola web, sin gestión de contraseñas), institución (un servidor en lugar de N puestos). ODS **justificados, no listados**: ODS 4 (acceso a entornos de prácticas fuera del aula), ODS 10 (alumnos sin hardware potente acceden vía navegador), ODS 12 (consolidación de recursos frente a un PC por alumno). | `docs/USO.md:Para el alumno`; [ELABORAR: redacción ODS] |
| 1.4 Metodología | Desarrollo iterativo incremental por fases (FASES 0-6), validación sobre host LXD real (no CI), y metodología asistida por agentes especializados y críticos de revisión con supervisión del autor (declaración honesta, ver §1.7 del plan). Debe casar con la estructura real de capítulos. | git log (§6); `.claude/agents/`, `.claude/skills/`; `CLAUDE.md:Golden rules` |
| 1.5 Estructura de la memoria | Índice comentado (máx. nivel 2), incluyendo anexos y aviso de la existencia del glosario (A1). | Este plan |
| 1.6 Convenciones | Código y comandos en monoespaciada; extranjerismos en cursiva; citas textuales entrecomilladas; nombres de ficheros del repositorio en monoespaciada. | `tfg-estilo-academico` |

Recorte si excede: comprimir 1.3 (impacto) a media página; nunca recortar 1.2.

### 02-estado-del-arte.md — Capítulo 2. Estado del arte (@tfg-estado-arte, 6 págs)

Único capítulo con **[INVESTIGAR]**: concentra el grueso de las referencias (8-15 entradas reales; nunca inventadas). Escribir para no especialista: definir aquí VM vs. contenedor, escritorio remoto, protocolo RDP/VNC.

| Sección | Contenido | Evidencia / marca |
|---|---|---|
| 2.1 Escritorios remotos y VDI | Panorama: VDI comercial (Citrix, VMware Horizon/Omnissa, Azure Virtual Desktop), soluciones libres (Apache Guacamole, noVNC, xrdp), y servicios cloud educativos. Evolución breve: del thin client al HTML5. | [INVESTIGAR: referencias académicas sobre VDI/educación + notas al pie de productos] |
| 2.2 Virtualización ligera | Contenedores vs. VMs; LXD como caso híbrido (contenedores de sistema + VMs KVM); comparación conceptual con Docker/Kubernetes y con Proxmox/OpenStack. | [INVESTIGAR: bibliografía técnica LXD/contenedores]; `Entorno de Laboratorio con LXD.md` (visión original) |
| 2.3 Laboratorios virtuales docentes | Trabajos previos de laboratorios remotos universitarios (p. ej. plataformas de laboratorios virtuales publicadas en revistas de educación en ingeniería). | [INVESTIGAR: 3-5 artículos reales; si no se localizan fuentes sólidas, reducir la sección — nunca citar sin fuente] |
| 2.4 Crítica al estado del arte | Lagunas: VDI comercial = coste de licencias y sobredimensionado para un laboratorio docente; Guacamole solo resuelve el túnel, no el aprovisionamiento ni el ciclo de vida; soluciones cloud = coste recurrente y dependencia. | Derivada de 2.1-2.3 + `README.md:Qué es` |
| 2.5 Propuesta | Qué hueco llena este TFG: integración de LXD + Guacamole + orquestador propio en un único host, con ciclo de vida automatizado y coste de licencias cero. Diferenciadores concretos (magic link, snapshots de autoservicio, instalador único). | `README.md:Qué es`, `README.md:Instalación` |

Recorte si excede: 2.3 es la sección sacrificable (fusionar con 2.1). Regla: webs de producto a nota al pie.

### 03-analisis.md — Capítulo 3. Análisis del problema (@tfg-analista, 10 págs)

| Sección | Contenido | Evidencia / marca | Págs |
|---|---|---|---|
| 3.1 Requisitos | Plantilla estándar. RF derivados de la funcionalidad real: login por magic link, dashboard multi-lab, escritorio en navegador, guardar/restaurar/reset, apps stateless, consola admin (labs, matrículas, apps, instancias, destroy). RNF desde las reglas de oro: nunca exponer 3389/5900, perfiles restringidos, automatización total por CLI, aislamiento entre alumnos, TTLs de sesión. | `docs/USO.md` (funcionalidad visible), `CLAUDE.md:Golden rules`, `README.md:Identidad y seguridad` | 2 |
| 3.2 Casos de uso | Diagrama UML de casos de uso [ELABORAR desde funcionalidad real]. Actores: Alumno, Administrador, Sistema (reaper/timers). 6-8 casos: autenticarse, seleccionar lab, usar escritorio, guardar snapshot, resetear, usar app, administrar catálogo, destruir instancia. 2-3 casos detallados en plantilla; el resto en tabla. | `docs/USO.md:Para el alumno`, `docs/USO.md:Consola admin` | 1,5 |
| 3.3 Análisis de seguridad | Modelo de amenazas por superficie: identidad (JWT scopes, secretos separados alumno/admin), red (guacd intermedio, iptables DROP inter-VM/inter-app/app↔VM), aplicación (middleware anti-headers forjados, CSP estricta, sandbox iframe sin allow-same-origin, X-Internal), logs seguros. Formato tabla amenaza→mitigación→evidencia. | `README.md:Identidad y seguridad`, `provision/main.py` (middleware), `nginx/iptables-lab.sh`, `nginx/iptables-apps.sh`, `provision/auth.py` | 2 |
| 3.4 Marco legal y ético | RGPD/LOPDGDD: emails de alumnos en SQLite, minimización (sin contraseñas almacenadas: magic link), logs sin datos sensibles. Licencias de dependencias: LXD (AGPL-3.0 desde Canonical / Apache-2.0 Incus — verificar y citar), Guacamole (Apache-2.0), FastAPI (MIT), Nginx (BSD-2). Licencia propia del proyecto [RELLENAR: decidir licencia del repo si no la hay]. | `provision/db.py` (datos personales), `README.md:Logs seguros`; [ELABORAR: análisis RGPD; [INVESTIGAR-ligero: textos legales citables — puede asumirlo @tfg-analista con las referencias BOE/DOUE estándar]] | 1,5 |
| 3.5 Análisis de riesgos | Tabla riesgo→tipo→impacto→mitigación, desde evidencias reales: saturación de pool (pool guard 60/75/90%), pérdida de trabajo del alumno (snapshots), host único como SPOF, dependencia de SMTP para login, preseed destructivo, grupo lxd ≈ root. | `docs/DEPLOY.md:Deudas y límites conocidos`, `README.md:Ciclo de vida`, `provision/policy.py` | 1 |
| 3.6 Soluciones posibles | Tabla comparativa con criterios declarados (coste, aislamiento, persistencia, complejidad): LXD vs Docker vs KVM puro vs Proxmox; Guacamole vs exponer xrdp vs noVNC; SQLite vs Postgres; magic link vs passwords; snapshots LXD vs backups. Mensaje: ingeniero que evalúa alternativas. | `docs/DEPLOY.md:Anexo B.1` (Opción A vs C), `Entorno de Laboratorio con LXD.md`, `DOIN.md`; [ELABORAR: formato comparativo] | 1,5 |
| 3.7 Solución propuesta y plan de trabajo | Solución en fases FASES 0-6. Plan real desde git (§6 de este plan): 4 etapas (dic-ene infra base; mar-may documentación/refactor; jun metodología de agentes + grueso de implementación; jul instalador autocontenido + consola admin). **Reflexión crítica sobre la desviación**: el grueso se concentró en junio, tras adoptar la metodología de agentes. Horas-persona [ELABORAR: estimación declarada, derivada del git log — no inventar precisión falsa]. | git log (§6), `docs/DEPLOY.md` (FASES) | 1 (incluye diagrama Gantt simple) |
| 3.8 Presupuesto | [ELABORAR declarado como estimación]: RRHH (horas × tarifa junior de referencia citada), hardware (servidor con KVM, ~32GB RAM como el descrito en cotas), software 0€ (FOSS), operación (dominio, electricidad/hosting). Tabla única. | `docs/DEPLOY.md:Deudas` (host 32GB), `README.md:Cotas` | 0,5 |

Recorte si excede: 3.2 a 1 pág (solo 1 caso detallado); 3.4 a 1 pág. No recortar 3.3 ni 3.6 (secciones que más valora el tribunal en este proyecto).

### 04-diseno.md — Capítulo 4. Diseño de la solución (@tfg-disenador, 10 págs)

| Sección | Contenido | Evidencia | Págs |
|---|---|---|---|
| 4.1 Arquitectura del sistema | Diagrama de bloques (versión académica del ASCII del README) + diagrama UML de despliegue [ELABORAR en Mermaid]. Flujos: petición autenticada vía `auth_request`, túnel RDP navegador→Nginx→Guacamole→guacd→VM, proxy directo de apps. Tabla de servicios/puertos/orígenes permitidos. Patrón: reverse proxy con gate de autenticación centralizado + orquestador. | `README.md:Arquitectura` (topología y tabla de puertos), `nginx/lab.conf`, `CLAUDE.md:Architecture` | 3 |
| 4.2 Diseño detallado | Módulos de `provision/` con responsabilidad de cada uno (main, auth, instances, jobs, policy, reap, apps, admin, web, db, config) + diagrama de componentes [ELABORAR]. Esquema BD: tabla-resumen de entidades (alumnos, labs, matrículas, instancias, app_instances, jobs, admins) y decisiones (SQLite WAL, single-writer); DDL completo → remisión al repositorio. Diseño del ciclo de vida: cola de jobs persistente (por qué no BackgroundTasks), reaper como proceso separado anti-TOCTOU, snapshots base+k1..k5 con LXD como fuente de verdad, pool guard fail-closed. Contrato cloud-init (Jinja2, render en memoria, stdin — por qué). | `provision/*.py`, `provision/db.py`, `provision/jobs.py`, `provision/policy.py`, `provision/reap.py`, `cloud-init-template.yml`, `docs/DEPLOY.md:Anexo A`, `docs/DEPLOY.md:Anexo C` | 4 |
| 4.3 Diseño de seguridad aplicado | Solo lo no cubierto en 3.3 (remisión cruzada, no repetir): cadena de identidad JWT→auth_request→headers sobrescritos; service tokens de VM/app ligados a IP; decisión `/verify/app` read-only. | `README.md:Identidad y seguridad`, `provision/auth.py`, `docs/DEPLOY.md:Anexo B.4-B.5` | 1 |
| 4.4 Tecnología utilizada | Tabla stack completo (Ubuntu Server, LXD/ZFS, KVM, FastAPI/uvicorn, SQLite, Jinja2, Guacamole+guacd, Docker, Nginx, certbot, systemd, iptables, xrdp, MATE) con papel y alternativa valorada (remisión a 3.6, sin repetir); nota de coste de aprendizaje. | `CLAUDE.md`, `README.md:Estructura del repo`; skill `tfg-ciclo-vida:Tecnología` | 2 |

Recorte si excede: 4.4 a 1,5 págs (la comparación ya vive en 3.6); nunca recortar 4.1-4.2.

### 05-desarrollo.md — Capítulo 5. Desarrollo (@tfg-desarrollo-doc, 6 págs)

**No es un changelog**: narrativa de problemas→decisiones. Poco código: máximo 3-4 fragmentos cortos comentados.

- 5.1 Organización del desarrollo: iteraciones reales (§6), metodología de agentes especializados y críticos (infra-lxd, provision-api, critic-security...) con skills que codifican reglas del dominio; validación contra host LXD real. Evidencia: git log, `.claude/agents/`, `.claude/skills/`, `CLAUDE.md:no lint/test suite`.
- 5.2 Problemas reales y soluciones (selección de gotchas documentados, cada uno: síntoma→causa→solución): CRLF de edición en Windows (conversión automática en el instalador); preseed LXD destructivo (guard `--force-preseed` y ampliaciones no destructivas de pool/subred); grupo `lxd` no activo (exit 100 y re-login); CSP estricta sin inline JS (render DOM con createElement); TOCTOU del reaper (`BEGIN IMMEDIATE`); uvicorn bind 0.0.0.0 + allowlist iptables; separación `launch()`/`launch_container()`. Evidencia: `CLAUDE.md:Known gotchas`, `README.md:Instalación`, `provision/reap.py`, `docs/DEPLOY.md`.
- 5.3 Decisiones de implementación destacadas: subprocess asíncrono en vez de REST LXD; render cloud-init por stdin (anti-inyección de flags); cola de jobs persistente. Evidencia: `provision/instances.py`, `docs/DEPLOY.md:Anexo A.3-A.4`, `provision/jobs.py`.
- Recorte si excede: reducir 5.2 a los 4 problemas más ilustrativos.

### 06-implantacion.md — Capítulo 6. Implantación (@tfg-desarrollo-doc, 4 págs)

- 6.1 Requisitos del host y preflight: qué comprueba y cómo falla (fail-fast). Evidencia: `docs/DEPLOY.md:0-0b`, `README.md:Instalación`.
- 6.2 Instalador dirigido: asistente interactivo (dominio, certbot, primer admin, SMTP), generación automática de secretos (no impresos), fases 0→6, idempotencia/desinstalación previa. Capturas del asistente [ELABORAR: el alumno aporta capturas; commits "Pantallas" 2026-06-29]. Evidencia: `install-all.sh`, `README.md:Instalación`.
- 6.3 Operación: servicios systemd y timers de reapers, rotación de secretos, alta de admins solo-SQL (decisión de seguridad), reconciliación dry-run al arranque. Evidencia: `systemd/`, `docs/USO.md:Para el administrador`.
- 6.4 Desinstalación y límites de reversión (qué no se revierte y por qué: ZFS shrink, /23). Evidencia: `README.md:Desinstalación`.
- Detalle paso a paso completo → Anexo A3 (remisión).

### 07-pruebas.md — Capítulo 7. Pruebas (@tfg-desarrollo-doc, 4 págs)

- 7.1 Estrategia: sin suite CI (declararlo honestamente y justificarlo: proyecto de infraestructura validado contra LXD real); validación estática (`bash -n`, `py_compile`) + criterios de aceptación por fase. Evidencia: `CLAUDE.md:no lint/typecheck/test`, `docs/DEPLOY.md:Validación FASE 0-6`.
- 7.2 Verificación funcional end-to-end: tabla criterio→comando→resultado esperado (401 sin sesión; flujo magic link→escritorio; `ss -tlnp` vacío en 3389/5900; guacd sin puertos publicados; FIFO k1..k5 con purga del 6º; reaper destruye VM idle; pool guard 503 >90%; auto-heal de apps shared; 403 en reset de app shared sin admin). Evidencia: `docs/DEPLOY.md:7 Chequeo final`, `docs/DEPLOY.md:Anexo C.8`, `docs/DEPLOY.md:Anexo B.6`.
- 7.3 Pruebas de capacidad/escalabilidad: tabla de cotas con su límite dominante (2-3 alumnos con k1..k5 en 40GB; ≤50 alumnos SQLite; ~510 IPs /23; 200-500 req/s en /verify/app...). Presentar como análisis de cotas, distinguiendo lo medido de lo estimado. Evidencia: `README.md:Cotas de escalabilidad`.
- 7.4 Validación con usuarios: **no realizada** — declararlo explícitamente y remitir a Trabajos futuros (honestidad técnica).
- Recorte si excede: 7.2 en tabla compacta, sin transcribir salidas completas.

### 08-conclusiones.md — Capítulo 8. Conclusiones (@tfg-build, AL FINAL, 3 págs)

- 8.1 Conclusiones: retomar OG y OE1..OE5 **uno a uno**, indicando grado de consecución y en qué capítulo se demuestra (OE1→cap.4/7; OE2→cap.4/5; OE3→cap.4/7; OE4→cap.6; OE5→cap.3/7). No repetir resultados; no concluir nada fuera de los objetivos. Incluir lo aprendido y limitaciones asumidas (host único, escala de laboratorio).
- 8.2 **Relación del trabajo desarrollado con los estudios cursados (OBLIGATORIO)**: asignaturas aplicadas [RELLENAR: nombres exactos del plan de estudios del alumno; propuesta: redes de computadores, sistemas operativos, seguridad, administración de sistemas, bases de datos, ingeniería del software, desarrollo web] + **competencias transversales UPV** puestas en práctica (análisis y resolución de problemas; aplicación pensamiento práctico; diseño y proyecto; planificación y gestión del tiempo; aprendizaje permanente).

### 09-trabajos-futuros.md — Capítulo 9. Trabajos futuros (@tfg-build, 1,5 págs)

Derivar SOLO de deudas documentadas: migración a Postgres (>50 alumnos), guacd con socket Unix (Opción C), SMTP de producción con DKIM/SPF, wrapper sudo para el grupo lxd, egress filtering de apps, rate-limit por alumno en apps, purga de histórico, validación con usuarios reales (piloto docente), multi-host. Incluir también un camino **desaconsejado** con razones (p. ej. subdominio por alumno con wildcard DNS-01: no aporta porque la identidad viene del JWT). Evidencia: `docs/DEPLOY.md:Deudas y límites conocidos`, `README.md:Cotas`.

### 10-referencias.md — Capítulo 10. Referencias (@tfg-build, mantenido vivo, 1,5 págs)

- ISO 690-2010 (o el formato que confirme el tutor). Objetivo: 12-20 entradas de calidad (libros, artículos, documentación técnica de referencia), no una lista de URLs.
- Registro incremental: cada cita que introduzca un redactor se anota aquí al momento; verificación final bidireccional citada↔existente.
- Recopilación separada de notas al pie (webs de producto, vídeos).

### Anexos (fuera de cómputo, 8-12 págs)

- **A1-glosario.md** (@tfg-build, vivo durante toda la redacción): LXD, contenedor de sistema, VM, KVM, ZFS, simplestreams, cloud-init, RDP, xrdp, guacd, reverse proxy, auth_request, JWT, magic link, TOTP, snapshot, reaper, TOCTOU, CSP, WAL, systemd timer, preflight, idempotencia...
- **A2-manual-usuario.md**: redacción académica derivada de `docs/USO.md` (alumno + administrador). No copiar literal (Turnitin): redactar sobre la fuente.
- **A3-guia-despliegue.md**: resumen operativo derivado de `docs/DEPLOY.md` (preflight, instalación un comando, validaciones) **remitiendo al repositorio** para el detalle; incluye la nota CRLF y la recreación destructiva.

## 4. Reparto de ficheros y orden de redacción

Orden de ejecución para @tfg-build: (1) 02 → (2) 03 → (3) 04 → (4) 05, 06, 07 → (5) 09, 10, A1-A3 → (6) 01 y 08 (exigen visión de conjunto) → (7) 00 (el resumen refleja la memoria terminada). Tras cada capítulo: @critic-tfg-formato + @critic-tfg-academico; en 03-07 además @critic-tfg-veracidad (con la sustitución AGENTS.md→CLAUDE.md de §1.8).

## 5. Figuras y tablas previstas (todas numeradas, con pie y citadas en el texto)

| Id | Tipo | Contenido | Capítulo | Fuente |
|---|---|---|---|---|
| Tabla 2.1 | Tabla | Comparativa de soluciones de escritorio remoto existentes | 2 | [INVESTIGAR] |
| Fig. 3.1 | UML casos de uso | Actores alumno/admin/sistema | 3 | [ELABORAR desde USO.md] |
| Tabla 3.1 | Tabla | Requisitos funcionales y no funcionales | 3 | USO.md + CLAUDE.md |
| Tabla 3.2 | Tabla | Amenaza → mitigación → evidencia | 3 | README + provision/ |
| Tabla 3.3 | Tabla | Riesgos (tipo, impacto, mitigación) | 3 | DEPLOY.md |
| Tabla 3.4 | Tabla | Alternativas con criterios (LXD/Docker/KVM...) | 3 | [ELABORAR] |
| Fig. 3.2 | Gantt | Plan de trabajo real (dic 2025-jul 2026) | 3 | git log |
| Tabla 3.5 | Tabla | Presupuesto | 3 | [ELABORAR] |
| Fig. 4.1 | Bloques | Arquitectura general (Nginx/Guacamole/provision/LXD) | 4 | README:Arquitectura |
| Fig. 4.2 | UML despliegue | Host, redes 10.50.x, servicios y puertos | 4 | README tabla puertos |
| Fig. 4.3 | UML componentes | Módulos de provision/ | 4 | provision/*.py |
| Tabla 4.1 | Tabla | Entidades de la BD (resumen) | 4 | provision/db.py |
| Fig. 4.4 | Diagrama | Ciclo de vida VM: creación→base→k1..k5→destrucción | 4 | policy.py + DEPLOY Anexo C |
| Tabla 4.2 | Tabla | Stack tecnológico y papel de cada pieza | 4 | CLAUDE.md |
| Fig. 5.1 | Diagrama | Metodología de agentes/críticos | 5 | .claude/agents/ |
| Fig. 6.1-6.3 | Capturas | Asistente de instalación, portal alumno, consola admin | 6 | [RELLENAR: capturas del alumno] |
| Tabla 7.1 | Tabla | Criterios de aceptación end-to-end | 7 | DEPLOY.md:7 + C.8 |
| Tabla 7.2 | Tabla | Cotas de escalabilidad y límite dominante | 7 | README:Cotas |

Diagramas: describir en texto + versión Mermaid en bloque de código (el alumno los convertirá a imagen para la plantilla).

## 6. Plan de trabajo real (insumo para 3.7 — datos de git)

| Etapa | Periodo | Hitos (commits reales) |
|---|---|---|
| 1. Infraestructura base | dic 2025 - ene 2026 | Commits iniciales, script de instalación, primeras pruebas; creación de imagen base en la instalación (2026-01-04) |
| 2. Documentación y consolidación | mar - may 2026 | Docs .md (2026-03-31), refactor (2026-04-28), limpieza (mayo) |
| 3. Metodología y grueso de implementación | jun 2026 | Agentes y skills (06-24), plan revisado (06-25), implementación (06-26), refactor + docs de uso/despliegue + install/uninstall (06-27), pantallas e instalación (06-29) |
| 4. Cierre de producto | jul 2026 | Orquestación de agentes (07-07), instalador autocontenido + consola admin completa + consolidación de docs (07-08), instalador dirigido (07-09) |

Reflexión para 3.7: estimación inicial implícita vs. realidad (concentración del esfuerzo en junio tras adoptar la metodología de agentes; meses de baja actividad — declarar honestamente la intermitencia y su gestión).

## 7. Críticas integradas (emulación de @critic-tfg-formato y @critic-tfg-academico sobre este guion)

Sin herramienta Agent disponible: se leyeron ambas definiciones y se aplicó su checklist de forma adversarial al guion. Hallazgos y resolución:

**De @critic-tfg-formato:**
1. **[ALTA] Título con acrónimo** — el borrador inicial incluía "LXD" en el título. *Integrada*: acrónimos movidos al subtítulo; título final de 9 palabras sin acrónimos (§0).
2. **[CRÍTICA] Riesgo de omitir "Relación con los estudios cursados"** — *Integrada*: sección 8.2 explícita, con competencias transversales UPV y [RELLENAR] para las asignaturas exactas del alumno.
3. **[ALTA] Extensión: 50 es el mínimo, no un máximo blando** — con la restricción del alumno, quedarse corto incumple la normativa. *Integrada*: presupuesto de 51 págs (colchón de +1 sobre el mínimo) y regla de que los preliminares no computan; @tfg-build debe verificar el recuento al cierre y, si queda <50, ampliar primero 3.3, 4.2 y 7.3 (secciones con más evidencia disponible).
4. **[MEDIA] Trazabilidad objetivos↔conclusiones** — *Integrada*: mapa OE→capítulo probatorio fijado en 8.1; los objetivos de §1.5 son literales e inmutables para todos los redactores.
5. **[MEDIA] Bibliografía como lista de URLs** — riesgo alto en un TFG de infraestructura. *Integrada*: regla en cap. 2 y 10 (webs de producto = nota al pie; objetivo 12-20 entradas de calidad).
6. **[BAJA] Índice >3 niveles** — *Integrada*: límite nivel 3 declarado en §2.

**De @critic-tfg-academico:**
1. **[ALTA] Lector no especialista** — el guion daba por sabidos LXD, guacd o magic link. *Integrada*: definiciones obligatorias en 2.2 (VM vs. contenedor), primera aparición de cada término con definición + entrada A1; A1 se mantiene vivo.
2. **[MEDIA] Preguntas de tribunal previsibles** — "¿por qué no Docker/Proxmox/VDI comercial?" (respondida en 3.6 con criterios declarados y 2.4), "¿cómo sabe que escala a N alumnos?" (7.3 distingue medido de estimado, con límite dominante por recurso), "¿qué pasa si se llena el disco?" (3.5 + pool guard en 4.2), "¿y si cae el host?" (SPOF asumido en 3.5 y 8.1 como limitación), "¿lo ha probado algún alumno real?" (7.4 lo declara y 9 lo propone). *Integradas* en las secciones citadas.
3. **[ALTA] Uso de IA en el desarrollo sin declarar** — un tribunal en 2026 lo preguntará; ocultarlo es un riesgo de integridad. *Integrada*: declaración honesta en 1.4 y 5.1, con [RELLENAR] para confirmar la política UPV aplicable con el tutor.
4. **[MEDIA] Capítulo 5 como changelog** — riesgo real dado el git log. *Integrada*: 5.2 estructurado como síntoma→causa→solución con máximo 6-7 casos y 3-4 fragmentos de código.
5. **[MEDIA] Duplicación seguridad (3.3 vs 4.3) y tecnología (3.6 vs 4.4)** — *Integrada*: 3.3 = amenazas/requisitos, 4.3 = mecanismos de diseño con remisión cruzada; 4.4 remite a 3.6 para la comparativa.
6. **[BAJA] Cifras sin fuente** — *Integrada*: regla de oro de `tfg-ciclo-vida` recordada en cada capítulo; presupuesto y horas marcados [ELABORAR] como estimación declarada.

**Hallazgo propio de veracidad (para @critic-tfg-veracidad):** las skills citan `AGENTS.md`, `PLAN.md` y `comandos.txt` como evidencia; `AGENTS.md` y `PLAN.md` ya no existen tras la consolidación de docs (2026-07-08). Sustituir por `CLAUDE.md`, `DOIN.md` y `Entorno de Laboratorio con LXD.md`. *Integrada* en §1.8.

**Pendientes que ningún redactor puede resolver (lista [RELLENAR] para el alumno):** nombre/tutor/curso; confirmación del título con la Comisión Académica; formato de citas con el tutor; política UPV de declaración de IA; asignaturas exactas y competencias transversales del plan de estudios (8.2); licencia del repositorio; capturas de pantalla reales del asistente, portal y consola; motivación personal de 1.1 (ajustar o ampliar el párrafo en 1ª persona); confirmación de fecha/commit de la ejecución final de la Tabla 7.1 sobre la versión depositada. Esta lista se verificó exhaustiva en la pasada de revisión de 2026-07-23 (§8).

## 8. Registro de la pasada de revisión y recorte (2026-07-23)

Ejecutada por @tfg-build sobre la memoria ya redactada (00-10 + A1-A3), sin
herramienta Agent disponible: los tres críticos (`critic-tfg-formato`,
`critic-tfg-academico`, `critic-tfg-veracidad`) se emularon leyendo sus
definiciones y aplicando su checklist de forma adversarial capítulo a
capítulo, con edición directa de los hallazgos (los críticos son de solo
lectura; @tfg-build corrige).

**Recorte de extensión** (regla "Recorte si excede" de §3, aplicada
literalmente; protegidas 3.3, 3.6, 4.1 y 4.2 tal como fija el guion):

| Fichero | Antes | Después | Variación |
|---|---|---|---|
| 01-introduccion.md | 1.833 | 1.809 | -1 % |
| 02-estado-del-arte.md | 2.431 | 2.197 | -10 % |
| 03-analisis.md | 4.840 | 4.232 | -13 % |
| 04-diseno.md | 4.082 | 3.942 | -3 % |
| 05-desarrollo.md | 2.297 | 2.132 | -7 % |
| 06-implantacion.md | 1.647 | 1.472 | -11 % |
| 07-pruebas.md | 1.603 | 1.467 | -8 % |
| 08-conclusiones.md | 1.087 | 1.062 | -2 % |
| 09-trabajos-futuros.md | 1.014 | 606 | -40 % |
| 10-referencias.md | 854 | 854 | — |
| **Total cuerpo** | **21.688** | **19.773** | **-9 %** |

03 y 04 quedan por encima de su presupuesto individual (3.500 c/u) porque
3.3+3.6 (1.605 palabras) y 4.1+4.2 (3.156 palabras) son la evidencia más
fuerte del capítulo y esta pasada respetó la instrucción explícita de no
tocarlas; el total del cuerpo queda dentro del margen aceptable
(17.000-19.500) con un desvío de +1,4 % sobre el techo, considerado
razonable dado el anclaje anterior. Si una revisión futura necesita bajar
de 19.500 estrictos, el único margen restante sin tocar 3.3/3.6/4.1/4.2
es reducir aún más 3.7-3.8 y 4.4, o mover parte de la Tabla 4.2 (esquema
de BD) a remisión pura al repositorio.

**Hallazgos de `critic-tfg-veracidad` corregidos**: ninguna discrepancia
memoria↔repositorio nueva (la sustitución AGENTS.md→CLAUDE.md de §1.8 ya
estaba aplicada); se resolvieron los marcadores `[ELABORAR]` visibles en
prosa corrida (no en comentario HTML) de 03 (ENS, tarifa del presupuesto,
desglose de operación anual, estimación de horas) y 04 (coste de
aprendizaje), reescribiéndolos como prosa académica que declara
explícitamente su carácter de supuesto, sin inventar cifras nuevas; y el
`[PENDIENTE]` de medidas de carga en 7.3 se reescribió como remisión a
Trabajos futuros en vez de una nota entre corchetes.

**Hallazgos de `critic-tfg-formato`/`critic-tfg-academico` corregidos**:
ninguna sección obligatoria ausente; trazabilidad objetivos↔conclusiones
intacta; bibliografía verificada bidireccional (12/12 citas↔entradas);
09-trabajos-futuros.md excedía el doble de su presupuesto (riesgo MEDIA de
"capítulo telegrama vs. relleno" señalado por `tfg-estilo-academico`) y se
recortó a la mitad conservando las siete deudas más sólidas, con una
frase de cierre que jerarquiza su urgencia (antes ausente). Se detectó y
corrigió un desliz propio durante el recorte: un primer intento de editar
la tabla de alternativas de 3.6 violaba la protección explícita de esa
sección; revertido antes de continuar.

**No se encontraron** hallazgos ALTA/CRÍTICA nuevos de veracidad ni de
formato que no estuvieran ya previstos en §7 original de este plan.

---

Fin del guion. Siguiente paso: ejecutar @tfg-build sobre este plan.
