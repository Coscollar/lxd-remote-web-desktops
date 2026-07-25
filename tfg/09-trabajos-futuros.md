# Capítulo 9. Trabajos futuros

Este capítulo recoge las líneas de evolución del sistema, derivadas todas de deudas técnicas y límites documentados (Capítulos 3 y 7), y un camino que se ha decidido no seguir.

## 9.1 Líneas de evolución priorizadas

**Validación con usuarios reales.** La carencia más relevante del trabajo, declarada en el Capítulo 7, es la ausencia de un piloto docente. El primer trabajo futuro es desplegar la plataforma en una asignatura real con un grupo reducido, midiendo satisfacción y tiempos percibidos, junto con las medidas empíricas de carga que el Capítulo 7 tampoco pudo aportar (peticiones/s sobre `/verify/app`, tiempos de lanzamiento, consumo real por instancia). <!-- fuente: propuesta derivada de 7.3 y 7.4 -->

**Ampliación del almacenamiento de escritorios.** El cuello de botella dominante de la capacidad actual es el *pool* de VMs de 40 GB (sección 7.3); ampliarlo hoy exige una recreación destructiva de la infraestructura LXD, o reducir la retención de instantáneas. Convertirlo en una operación segura es la mejora operativa más inmediata. <!-- fuente: docs/DEPLOY.md:Deudas y límites conocidos (persistent-pool 40GB, --force-preseed) -->

**Endurecimiento para producción.** Cinco deudas marcan el paso de laboratorio a producción: SMTP transaccional con DKIM/SPF y cola de reintentos para el *magic link*; retirar el servicio orquestador del grupo `lxd` (equivalente a root) con un envoltorio `sudo` de lista blanca; migrar guacd a un *socket* Unix compartido (opción ya analizada); instalar la lista blanca de cortafuegos del puerto de la API, documentada pero no aplicada; y completar el segundo factor TOTP de administración, cuyo andamiaje existe pero no se verifica. <!-- fuente: docs/DEPLOY.md:Deudas y límites conocidos; provision/auth.py; provision/db.py (andamiaje TOTP) -->

**Cierre de brechas entre lo documentado y lo implementado.** La revisión de veracidad de esta memoria (Capítulos 4 y 7) identificó funcionalidad documentada pero no implementada: destrucción por fecha límite del curso, latido propio de las aplicaciones efímeras, extensión del guardián del *pool* al lanzamiento de VMs, alta automática de conexiones en Guacamole, copia de seguridad periódica de la base de datos, y la batería de pruebas unitarias de la lógica pura, cuya ausencia se justificó en 7.1. <!-- fuente: provision/reap.py; provision/apps.py; provision/jobs.py; docs/DEPLOY.md:Anexo B.4 -->

**Otras líneas.** La identidad institucional (SSO/LDAP), pospuesta en 3.6, eliminaría la dependencia del correo a costa de acoplar la plataforma a cada centro; el filtrado de egreso de las aplicaciones y la corrección del límite de peticiones por alumno cierran deudas de aislamiento; la purga periódica del histórico y la migración a PostgreSQL (una vez el *pool* deje de ser el límite) completan la operación; y el crecimiento a varios servidores —fuera de alcance hoy (Capítulo 8)— exigiría además un planificador de instancias, para el que LXD ofrece agrupación nativa en clúster. <!-- fuente: sección 3.6; docs/DEPLOY.md:Deudas y límites conocidos; README.md:Cotas -->

Estas líneas no son equivalentes en urgencia: el piloto y el almacenamiento condicionan el uso real; el endurecimiento y el cierre de brechas son higiene técnica; el resto son mejoras incrementales sobre un sistema que ya opera a la escala actual.

## 9.2 Un camino desaconsejado

Se ha valorado y descartado ofrecer un **subdominio por alumno** (`alumno.lab.dominio`) mediante certificados comodín con validación DNS-01. No aporta valor de seguridad ni de identidad en esta arquitectura: la identidad procede exclusivamente del JWT verificado en cada petición, no del nombre de host, y el aislamiento de origen entre aplicaciones ya lo da el atributo `sandbox` del iframe sin `allow-same-origin`. El coste (DNS dinámico, renovación DNS-01, complejidad del proxy) no queda compensado; solo cobraría sentido si se quisiera aislamiento *cross-origin* sin depender del sandbox, escenario que hoy no se da. <!-- fuente: docs/DEPLOY.md:Deudas y límites conocidos (certbot HTTP-01, subdominio por app) -->
