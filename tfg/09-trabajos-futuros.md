# Capítulo 9. Trabajos futuros

Este capítulo recoge las líneas de evolución del sistema, derivadas todas de deudas técnicas y límites documentados (Capítulos 3 y 7), y un camino que se ha decidido no seguir.

## 9.1 Líneas de evolución priorizadas

**Validación con usuarios reales.** La carencia más relevante del trabajo es la ausencia de un piloto docente (Capítulo 7). El primer trabajo futuro es desplegar la plataforma en una asignatura real con un grupo reducido, midiendo satisfacción, tiempos percibidos y las medidas de carga que el Capítulo 7 tampoco pudo aportar (peticiones/s sobre `/verify/app`, tiempos de lanzamiento, consumo real por instancia). <!-- fuente: propuesta derivada de 7.3 y 7.4 -->

**Ampliación del almacenamiento de escritorios.** El cuello de botella dominante de la capacidad actual es el *pool* de VMs de 40 GB (7.3); ampliarlo hoy exige una recreación destructiva de la infraestructura LXD o reducir la retención de instantáneas. Convertirlo en una operación segura es la mejora operativa más inmediata. <!-- fuente: docs/DEPLOY.md:Deudas y límites conocidos (persistent-pool 40GB, --force-preseed) -->

**Endurecimiento para producción.** Cinco deudas marcan el paso a producción: SMTP transaccional con DKIM/SPF y reintentos para el *magic link*; retirar el orquestador del grupo `lxd` con un envoltorio `sudo` de lista blanca; migrar guacd a *socket* Unix compartido (ya analizado en 3.6); instalar la lista blanca de cortafuegos del puerto de la API (véase 5.2); y completar el segundo factor TOTP de administración, cuyo andamiaje existe sin verificarse. <!-- fuente: docs/DEPLOY.md:Deudas y límites conocidos; provision/auth.py; provision/db.py (andamiaje TOTP) -->

**Cierre de brechas entre lo documentado y lo implementado.** El contraste de esta memoria con el código (Capítulos 4 y 7) identificó funcionalidad documentada pero no implementada: destrucción por fecha límite del curso, latido propio de las aplicaciones, extensión del guardián del *pool* al lanzamiento de VMs, alta automática de conexiones en Guacamole, copia de seguridad de la base de datos, y la batería de pruebas unitarias, cuya ausencia se justificó en 7.1. <!-- fuente: provision/reap.py; provision/apps.py; provision/jobs.py; docs/DEPLOY.md:Anexo B.4 -->

**Otras líneas.** La identidad institucional (SSO/LDAP, pospuesta en 3.6) eliminaría la dependencia del correo a costa de acoplar la plataforma a cada centro; el filtrado de egreso y el límite de peticiones por alumno cierran deudas de aislamiento; la purga del histórico y la migración a PostgreSQL completan la operación; y el crecimiento a varios servidores —fuera de alcance hoy— exigiría un planificador de instancias, para el que LXD ofrece agrupación nativa en clúster. <!-- fuente: sección 3.6; docs/DEPLOY.md:Deudas y límites conocidos; README.md:Cotas -->

Estas líneas no son equivalentes en urgencia: el piloto y el almacenamiento condicionan el uso real; el endurecimiento y el cierre de brechas son higiene técnica; el resto son mejoras incrementales sobre un sistema que ya opera a la escala actual.

## 9.2 Un camino desaconsejado

Se ha valorado y descartado ofrecer un **subdominio por alumno** (`alumno.lab.dominio`) mediante certificados comodín con validación DNS-01. No aporta valor de seguridad ni de identidad en esta arquitectura: la identidad procede exclusivamente del JWT verificado en cada petición, no del nombre de host, y el aislamiento de origen entre aplicaciones ya lo da el atributo `sandbox` del iframe sin `allow-same-origin`. El coste (DNS dinámico, renovación DNS-01, complejidad del proxy) no queda compensado; solo cobraría sentido si se quisiera aislamiento *cross-origin* sin depender del sandbox, escenario que hoy no se da. <!-- fuente: docs/DEPLOY.md:Deudas y límites conocidos (certbot HTTP-01, subdominio por app) -->
