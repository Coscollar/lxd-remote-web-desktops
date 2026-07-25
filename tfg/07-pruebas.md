# Capítulo 7. Pruebas

Este capítulo documenta cómo se verificó el sistema: estrategia y justificación (7.1), criterios de aceptación comprobados de extremo a extremo (7.2), análisis de capacidad y eficiencia (7.3) y estado de la validación con usuarios (7.4), distinguiendo siempre lo verificado de lo estimado.

## 7.1 Estrategia de verificación

El proyecto **no cuenta con una batería de pruebas unitarias ni con integración continua**. <!-- fuente: CLAUDE.md:"no lint/typecheck/test suite" --> No es una omisión sin examen: la capa de infraestructura —scripts que crean *pools* ZFS, reglas de cortafuegos, lanzamiento de VMs— no admite simulación útil, y montar integración continua con virtualización anidada, ZFS y certificados excedía el alcance del trabajo. La lógica pura del orquestador —rotación FIFO, expresiones regulares de nombres, testigos, umbrales del guardián del *pool*— sí admitiría pruebas unitarias convencionales no implementadas; esa red de seguridad contra regresiones queda como trabajo futuro (Capítulo 9).

En su lugar, la verificación se apoyó en tres prácticas: **validación estática** de todos los artefactos (`bash -n` en los scripts, `python -m py_compile` en los módulos, antes de cada ejecución); <!-- fuente: .claude/skills/tfg-ciclo-vida (práctica de validación del proyecto) --> **criterios de aceptación por fase**, con comandos y resultado esperado ejecutados sobre el host real al cerrar cada una de las FASES 0 a 6 y tras cada cambio que la afectara; <!-- fuente: docs/DEPLOY.md:Validación FASE 0-6 --> y la **idempotencia como prueba**: reejecutar los scripts sobre un host ya configurado debe terminar sin errores ni cambios, lo que convierte cada reejecución en una comprobación del estado declarado. <!-- fuente: docs/DEPLOY.md:Validación FASE 0 --> Las invariantes del proyecto (perfiles restringidos siempre, puertos de escritorio jamás expuestos, guacd como único intermediario) cierran la estrategia como propiedades verificables. <!-- fuente: CLAUDE.md:Golden rules -->

## 7.2 Verificación funcional de extremo a extremo

La Tabla 7.1 recoge los criterios de aceptación del sistema completo, con la comprobación que los verifica y su resultado esperado; se ejecutaron sobre la instalación real durante el desarrollo, al cierre de cada fase. [RELLENAR: confirmar la ejecución completa de la tabla sobre la versión final depositada, indicando fecha y commit] Los comandos se muestran recortados a lo esencial (las formas completas están en la guía de despliegue del repositorio y en el Anexo A3).

| Criterio | Comprobación | Resultado esperado |
|---|---|---|
| Acceso denegado sin sesión | `curl -kI https://lab.<dominio>/dashboard` | `401`; `200` con cookie de sesión válida |
| Consola de administración protegida | `curl -kI https://lab.<dominio>/admin` | `401` sin cookie `admin_token` |
| Flujo completo del alumno | correo → *magic link* → «Abrir escritorio» (manual) | escritorio MATE operativo en el navegador |
| Ningún puerto de escritorio expuesto (OE1) | `ss -tlnp \| grep -E ':(3389\|5900\|3000\|8888)'` | salida vacía |
| guacd sin puertos publicados | `docker ps` (formato nombre/puertos), filtro `guacd` | sin puertos publicados |
| API remota de LXD cerrada | `lxc config show \| grep -E 'trust_password\|https_address'` | salida vacía |
| Rotación FIFO de instantáneas | cinco `POST /save` y un sexto; `lxc info <vm>` | `base`+`k1..k5`; el sexto purga `k1` y reutiliza el hueco |
| Destrucción por inactividad | `IDLE_MINUTES=1`, esperar, disparar `provision-reap.service` | instancia marcada destruida y ausente de `lxc list` |
| Guardián del *pool* | *pool* >90 % de uso, `POST /save` | `503` al crear la instantánea (el rechazo del lanzamiento de VMs está pendiente; sección 4.2.3) |
| Autorreparación de apps compartidas | destruir la instancia `always_on` y reiniciar el servicio | el trabajo de *auto-heal* la relanza (asíncrono) |
| Reset de app compartida sin privilegio | `POST /api/apps/{id}/reset` como alumno | `403` (solo administrador) |
| Aislamiento de red entre alumnos (OE3) | `iptables -L FORWARD` | cadenas con DROP inter-VM, inter-aplicación y aplicación↔VM |
| Idempotencia de la infraestructura | reejecutar `server-setup-lxd.sh` | termina sin errores ni cambios destructivos |
| Renovación del certificado | `certbot renew --dry-run` | simulación satisfactoria |

*Tabla 7.1. Criterios de aceptación de extremo a extremo: comprobación y resultado esperado. Elaboración propia a partir de las secciones de validación de la guía de despliegue.* <!-- fuente: docs/DEPLOY.md:7 (chequeo final), Validación FASE 0-6, Anexo B.6, Anexo C.8 -->

Tres de estas filas verifican directamente objetivos del trabajo: la ausencia de puertos de escritorio expuestos y el confinamiento de guacd acreditan OE1; la rotación de instantáneas, la destrucción por inactividad y el guardián del *pool* acreditan el ciclo de vida de OE2; y el rechazo del *reset* de aplicaciones compartidas, junto con la fila de aislamiento de red, acredita OE3. La relación completa objetivos–evidencias se retoma en el Capítulo 8. <!-- fuente: tfg/01-introduccion.md:1.2; docs/DEPLOY.md:Validación FASE 4 y 6 -->

## 7.3 Análisis de capacidad y eficiencia

La evaluación de escalabilidad (parte de OE5) se presenta como un **análisis de cotas**: para cada recurso se identifica el límite dominante y la capacidad que impone. Es importante precisar el carácter de cada cifra: ninguna procede de una prueba de carga con usuarios simulados; son cotas *aritméticas* (derivan de una división directa de recursos), *de diseño* (las impone una constante del código) o *estimaciones documentadas* del proyecto. La Tabla 7.2 las recoge con esa clasificación. <!-- fuente: README.md:Cotas de escalabilidad; docs/DEPLOY.md:Deudas y límites conocidos -->

| Recurso | Cota | Límite dominante | Carácter |
|---|---|---|---|
| VMs con retención `k1..k5` (*pool* 40 GB) | ≤ 2-3 alumnos | Almacenamiento ZFS de VMs (cuello de botella actual) | Estimación documentada |
| Retención reducida `k1..k3` (uso > 60 %) | Reduce el espacio por alumno (de `base`+5 a `base`+3 instantáneas) | Guardián del *pool* | De diseño |
| Alumnos concurrentes sobre SQLite | ≤ 50 | Escritor único (WAL) | Estimación documentada |
| Lanzamientos de VM concurrentes | ≤ 4 | Semáforo derivado de la RAM + *worker* único | De diseño |
| VMs por subred (10.50.20.0/24) | ≤ 250 | Direccionamiento | Aritmética |
| VMs por memoria | RAM del host / 4 GB (cota bruta) | RAM (4 GB por VM) | Aritmética |
| Contenedores de aplicación (*pool* 80 GB) | ~60-80 | Almacenamiento ZFS de aplicaciones | Estimación documentada |
| Apps por alumno en un host de 32 GB | ~10-12 concurrentes | RAM (2 GB por aplicación) | Estimación documentada |
| Direcciones de aplicaciones (/23) | ~510 | Direccionamiento | Aritmética |
| Verificación `/verify/app` | ~200-500 peticiones/s | Decodificación JWT (solo lectura, sin BD) | Estimación documentada |
| Apps compartidas siempre activas | suma de memoria ≤ 8.192 MB | Presupuesto de RAM configurado | De diseño |

*Tabla 7.2. Cotas de capacidad con su límite dominante y el carácter de cada cifra (aritmética, de diseño o estimación documentada; ninguna medida empíricamente). Elaboración propia.* <!-- fuente: README.md:Cotas de escalabilidad; provision/jobs.py (_sem_limit); install-all.sh (ALWAYS_ON_BUDGET_MB) -->

Conviene precisar qué significa "estimación documentada": son cifras que el propio proyecto declara (`README.md`) sin publicar un cálculo intermedio verificable —a diferencia de las filas "aritméticas", que sí exhiben la división de recursos de la que se derivan—, por lo que deben leerse como órdenes de magnitud, no como valores calculados ni medidos; verificarlas empíricamente es la carencia que registra el párrafo siguiente y que propone resolver el Capítulo 9.

La lectura conjunta de la tabla identifica el cuello de botella real: **el almacenamiento de las VMs persistentes**. Con el *pool* de 40 GB, la retención de cinco instantáneas por alumno agota el espacio con dos o tres alumnos, muy por debajo de los límites de red (250) o de la base de datos (50); la cota de RAM (8 VMs en un host de 32 GB) es también más holgada, aunque esa cifra bruta no descuenta el sistema operativo, Guacamole ni el presupuesto de aplicaciones siempre activas, por lo que la cifra efectiva es menor y no está medida. Por eso existen el guardián del *pool* y la degradación de retención, y por eso ampliar el *pool* es la primera acción de escalado (Capítulo 9). En eficiencia, las dos decisiones de mayor efecto se argumentaron en los Capítulos 4 y 5: el punto de verificación de aplicaciones no escribe en la base de datos y las instantáneas ZFS tienen coste marginal casi nulo. <!-- fuente: docs/DEPLOY.md:Anexo B.4 y C.2; README.md:Cotas de escalabilidad --> Ninguna de estas cifras procede de una medición de carga real; obtenerlas (peticiones/s efectivas sobre `/verify/app`, tiempo medio de lanzamiento, consumo real por instancia) queda como trabajo futuro antes del depósito (Capítulo 9).

## 7.4 Validación con usuarios

La validación con usuarios finales —alumnos y docentes reales en una práctica— **no se ha realizado**: el sistema se ha verificado técnicamente de extremo a extremo (7.2), incluidos los flujos completos de alumno y administrador ejecutados por el autor, pero no existe evidencia de uso por terceros ni medidas de usabilidad. Se declara expresamente para no sobrevalorar el alcance de las pruebas: la verificación demuestra que el sistema funciona según lo especificado; solo un piloto docente puede demostrar que resuelve el problema en condiciones reales, y se propone como primera línea de trabajo futuro (Capítulo 9). <!-- fuente: decisión de honestidad técnica; no existe evidencia de validación con usuarios en el repositorio -->

Verificado el sistema y acotada su capacidad, el capítulo siguiente cierra la memoria retomando los objetivos de la Introducción, su grado de consecución y las limitaciones asumidas.
