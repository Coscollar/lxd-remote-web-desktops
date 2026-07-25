# Anexo A1. Glosario de términos y acrónimos

<!-- FICHERO VIVO: cada redactor añade aquí todo término técnico nuevo
     que introduzca en su capítulo. Orden alfabético al cierre.
     Público objetivo: profesional informático NO especialista. -->

**auth_request** — Mecanismo de Nginx por el que, antes de servir una petición, se consulta a un servicio interno de autenticación; si este responde con error, la petición se rechaza sin llegar al destino. <!-- fuente: nginx/lab.conf -->

**BEGIN IMMEDIATE (SQLite)** — Forma de iniciar una transacción de SQLite que toma el bloqueo de escritura desde el primer momento, en lugar de al ejecutar la primera escritura; garantiza que las comprobaciones hechas dentro de la transacción sigan siendo válidas cuando se escriba. <!-- fuente: provision/reap.py; cap. 5 -->

**Broker de conexión** — En las plataformas VDI, componente que asigna a cada usuario su escritorio virtual y encamina la sesión hasta él. <!-- fuente: cap. 2 -->

**certbot** — Cliente oficial de la autoridad Let's Encrypt que solicita, instala y renueva automáticamente certificados TLS mediante los retos del protocolo ACME. <!-- fuente: nginx/install.sh; cap. 4 -->

**cloud-init** — Estándar *de facto* de inicialización de instancias en la nube: un fichero YAML declara usuarios, paquetes, ficheros y comandos que se aplican en el primer arranque de una máquina. <!-- fuente: cloud-init-template.yml -->

**Cola de trabajos (job queue)** — Estructura persistente en la que se registran las tareas pendientes de ejecución (aquí, en una tabla de la base de datos) para que un proceso trabajador las ejecute de forma asíncrona; al sobrevivir a reinicios del servicio, ninguna tarea aceptada se pierde. <!-- fuente: provision/jobs.py -->

**Contenedor de aplicación** — Contenedor que empaqueta un único proceso con sus dependencias en una imagen inmutable y efímera; es el modelo popularizado por Docker. <!-- fuente: cap. 2 (Merkel, 2014) -->

**Contenedor de sistema** — Entorno aislado que comparte el núcleo del sistema operativo anfitrión pero ejecuta una distribución completa con su propio init, a diferencia de los contenedores de aplicación (Docker), que ejecutan un único proceso. <!-- fuente: Entorno de Laboratorio con LXD.md -->

**CRLF / LF** — Convenciones de final de línea de los ficheros de texto: Windows termina cada línea con retorno de carro y salto de línea (CRLF), mientras que Unix usa solo el salto de línea (LF); un script de shell con CRLF falla en Linux porque el retorno de carro se interpreta como parte del comando. <!-- fuente: install-all.sh; cap. 5 -->

**CSP (Content Security Policy)** — Cabecera HTTP que restringe los orígenes desde los que un navegador puede cargar y ejecutar recursos (scripts, estilos, marcos), mitigando ataques de inyección de código. <!-- fuente: CLAUDE.md:Golden rules -->

**DaaS (Desktop as a Service)** — Evolución del VDI en la que el plano de control, y a menudo los propios escritorios virtuales, residen en la nube de un proveedor que los factura por suscripción o por uso. <!-- fuente: cap. 2 -->

**Docker** — Plataforma de contenedores de aplicación que empaqueta procesos con sus dependencias en imágenes portables entre distribuciones Linux. <!-- fuente: cap. 2 (Merkel, 2014) -->

**Dry-run (ejecución simulada)** — Modo de ejecución en el que un proceso calcula y notifica lo que haría sin efectuar cambios; aquí, la reconciliación de arranque marca discrepancias pero nunca borra instancias. <!-- fuente: provision/main.py (lifespan); docs/DEPLOY.md:Anexo C.5 -->

**Event loop (bucle de eventos)** — Núcleo de un servidor asíncrono que atiende muchas peticiones concurrentes turnándolas en un único hilo; cualquier operación bloqueante ejecutada en él congela todas las peticiones a la vez. <!-- fuente: provision/instances.py; cap. 5 -->

**Fail-closed (cierre seguro)** — Principio por el que un componente, ante la imposibilidad de verificar una condición, asume el caso desfavorable y rechaza la operación en lugar de permitirla. <!-- fuente: provision/policy.py; cap. 4 -->

**Fail-fast (fallo temprano)** — Principio por el que un proceso comprueba sus precondiciones al inicio y aborta inmediatamente si no se cumplen, en lugar de fallar más tarde con el trabajo a medias; lo aplican el preflight del instalador y la carga de configuración del orquestador. <!-- fuente: install-all.sh:0b; provision/config.py -->

**FIFO (First In, First Out)** — Política de rotación en la que, al alcanzarse el límite de elementos, se elimina el más antiguo para dar sitio al nuevo; es la rotación de las instantáneas `k1..k5`. <!-- fuente: provision/policy.py; docs/DEPLOY.md:Anexo C.1 -->

**FastAPI** — *Framework* web para Python orientado a APIs, con validación de datos y ejecución asíncrona; es la base del orquestador de este proyecto. <!-- fuente: provision/main.py -->

**FOSS (Free and Open Source Software)** — Software libre y de código abierto, cuya licencia permite usarlo, estudiarlo, modificarlo y redistribuirlo sin coste de licencia. <!-- fuente: cap. 2 -->

**guacd** — Demonio proxy de Apache Guacamole que traduce protocolos de escritorio remoto (RDP, VNC) al protocolo interno de Guacamole, que el cliente HTML5 consume vía WebSocket. <!-- fuente: guacamole/docker-compose.yml -->

**Heartbeat** — Señal periódica que un componente envía para acreditar que sigue activo; aquí, cada VM la emite cada cinco minutos hacia el orquestador, que la usa para decidir la destrucción por inactividad (las aplicaciones efímeras carecen hoy de latido propio; véase 4.2.3). <!-- fuente: docs/USO.md:Scripts de laboratorio; provision/apps.py -->

**HS256 (HMAC-SHA256)** — Algoritmo de firma simétrica usado en los JWT del sistema: quien conoce el secreto puede emitir y verificar testigos. <!-- fuente: provision/auth.py -->

**Hipervisor** — Software que reparte los recursos de una máquina física entre varias máquinas virtuales, gestionando su creación, aislamiento y ejecución. <!-- fuente: cap. 2 -->

**IaaS (Infrastructure as a Service)** — Modelo de nube que ofrece infraestructura de cómputo, red y almacenamiento virtualizada bajo demanda, sobre la que el cliente despliega sus propios sistemas. <!-- fuente: cap. 2 -->

**Idempotencia** — Propiedad de una operación que produce el mismo resultado aunque se ejecute varias veces; los scripts de infraestructura del proyecto comprueban el estado antes de actuar para poder reejecutarse sin efectos duplicados. <!-- fuente: nginx/iptables-lab.sh -->

**Incus** — Derivado comunitario de LXD surgido en 2023, compatible en conceptos y comandos, mantenido dentro del proyecto Linux Containers. <!-- fuente: cap. 2 (nota al pie) -->

**Integración continua (CI)** — Práctica de ejecutar automáticamente compilación y pruebas sobre cada cambio del código en un entorno controlado; este proyecto no dispone de ella y valida contra el host real (véase el Capítulo 7). <!-- fuente: CLAUDE.md:"no lint/typecheck/test suite"; cap. 7 -->

**Jinja2** — Motor de plantillas para Python que permite generar texto (aquí, ficheros YAML y páginas HTML) interpolando variables y aplicando condicionales y bucles. <!-- fuente: cloud-init-template.yml; docs/DEPLOY.md:Anexo A.1 -->

**JupyterHub** — Servidor multiusuario que lanza un entorno de *notebooks* Jupyter por usuario desde una máquina central, de uso extendido en docencia de ciencia de datos. <!-- fuente: cap. 2 -->

**JWT (JSON Web Token)** — Testigo firmado que codifica afirmaciones (*claims*) sobre una identidad; permite a servicios independientes verificar la sesión sin estado compartido. <!-- fuente: provision/auth.py -->

**Kubernetes** — Orquestador de contenedores de aplicación que gestiona su despliegue, escalado y ciclo de vida sobre clústeres de servidores. <!-- fuente: cap. 2 (Burns et al., 2016) -->

**KVM (Kernel-based Virtual Machine)** — Hipervisor integrado en el núcleo Linux que permite ejecutar máquinas virtuales con aceleración por hardware. <!-- fuente: install-all.sh (preflight /dev/kvm) -->

**Let's Encrypt** — Autoridad de certificación gratuita y automatizada que emite certificados TLS reconocidos por los navegadores; los valida mediante retos como HTTP-01 (servir un fichero en el puerto 80). <!-- fuente: nginx/install.sh; cap. 4 -->

**LXC (Linux Containers)** — Tecnología de contenedores de sistema del núcleo Linux sobre la que se construye LXD; también la usa Proxmox VE para sus contenedores. <!-- fuente: cap. 2 -->

**LXD** — Gestor de virtualización ligera de Canonical que administra tanto contenedores de sistema como máquinas virtuales KVM bajo una única API y CLI (`lxc`). <!-- fuente: server-setup-lxd.sh -->

**Magic link** — Mecanismo de autenticación sin contraseña: el usuario recibe por correo un enlace de un solo uso y validez limitada cuyo canje inicia la sesión. <!-- fuente: provision/auth.py -->

**MATE** — Entorno de escritorio Linux ligero, continuación de GNOME 2, elegido para las VMs de alumno por su bajo consumo de memoria. <!-- fuente: build-lab-vm-base-mate.sh -->

**Middleware** — Componente que intercepta todas las peticiones de una aplicación web antes (o después) de su tratamiento, para aplicar lógica transversal como saneado de cabeceras o control de acceso. <!-- fuente: provision/main.py -->

**noVNC** — Cliente VNC libre escrito en JavaScript que se ejecuta íntegramente en el navegador mediante HTML5 y WebSocket, sin instalación local. <!-- fuente: cap. 2 -->

**OpenStack** — Plataforma libre de nube privada (IaaS) orientada a centros de datos con múltiples servidores. <!-- fuente: cap. 2 -->

**Orquestador** — Servicio que coordina la creación, supervisión y destrucción de los recursos de una plataforma según reglas de negocio; aquí, la API de aprovisionamiento del proyecto. <!-- fuente: provision/ -->

**Perfil (LXD)** — Conjunto reutilizable de configuración de LXD (límites de CPU y memoria, disco, red) que se aplica a una instancia al crearla; en este proyecto toda instancia usa un perfil restringido, nunca el perfil por defecto. <!-- fuente: lxd-preseed.yaml; CLAUDE.md:Golden rules -->

**Pool (de almacenamiento)** — Agrupación de espacio de disco gestionada por LXD (aquí sobre ZFS) de la que se aprovisionan los volúmenes de instancias e instantáneas. <!-- fuente: server-setup-lxd.sh -->

**Preflight** — Verificación previa del entorno que un instalador ejecuta antes de modificar nada, abortando si el host no cumple los requisitos (aquí: sistema operativo, KVM, ZFS, puertos libres, RAM y disco). <!-- fuente: install-all.sh; docs/DEPLOY.md:0b -->

**Preseed (LXD)** — Fichero declarativo que configura de una sola vez el demonio LXD (pools, redes, perfiles, proyectos); su aplicación no es incremental: reemplaza la configuración existente completa, por lo que reaplicarlo es destructivo. <!-- fuente: lxd-preseed.yaml; docs/DEPLOY.md:2 -->

**Proxmox VE (Virtual Environment)** — Plataforma libre de virtualización que combina máquinas virtuales KVM y contenedores LXC bajo una consola web de administración con soporte de clúster. <!-- fuente: cap. 2 -->

**Proyecto (LXD)** — Espacio de nombres de LXD que agrupa instancias, imágenes, perfiles y redes bajo un ámbito aislado; el proyecto `labs` separa los recursos de los alumnos del resto del host. <!-- fuente: lxd-preseed.yaml; server-setup-lxd.sh -->

**RDP (Remote Desktop Protocol)** — Protocolo de escritorio remoto que transmite la interfaz gráfica de una máquina a un cliente y devuelve las interacciones de teclado y ratón. <!-- fuente: README.md:Arquitectura -->

**Reaper** — Proceso periódico que destruye recursos caducados u ociosos (aquí: VMs y contenedores inactivos o fuera de plazo). <!-- fuente: provision/reap.py -->

**Reverse proxy** — Servidor intermedio que recibe las peticiones de los clientes y las reenvía a los servicios internos apropiados, centralizando TLS, enrutado y autenticación. <!-- fuente: nginx/lab.conf -->

**Sandbox (atributo de iframe)** — Restricción declarativa de HTML que limita lo que un documento embebido puede hacer (ejecutar scripts, enviar formularios, acceder al origen del padre); sin `allow-same-origin`, el contenido embebido no puede leer las cookies de la página que lo aloja. <!-- fuente: README.md:Identidad y seguridad -->

**simplestreams** — Protocolo de publicación y descarga de imágenes de sistema operativo empleado por LXD para obtener imágenes oficiales de repositorios remotos. <!-- fuente: server-setup-lxd.sh; cap. 2 -->

**Snapshot** — Copia instantánea del estado de una instancia (disco y configuración) que permite restaurarla posteriormente a ese punto. <!-- fuente: provision/policy.py -->

**SPOF (Single Point of Failure)** — Componente único cuyo fallo interrumpe todo el sistema; aquí, el servidor único que aloja toda la plataforma. <!-- fuente: docs/DEPLOY.md:Deudas y límites conocidos -->

**SSRF (Server-Side Request Forgery)** — Ataque en el que se induce a un servidor a realizar peticiones hacia destinos internos elegidos por el atacante; se mitiga impidiendo que el cliente controle el destino de las peticiones internas. <!-- fuente: docs/DEPLOY.md:Anexo B.3 -->

**systemd timer** — Unidad de systemd que programa la ejecución periódica de un servicio, equivalente moderno de cron. <!-- fuente: systemd/ -->

**Thin client (cliente ligero)** — Dispositivo de bajo coste cuya única función es presentar sesiones de escritorio ejecutadas en un servidor central y devolver las interacciones del usuario. <!-- fuente: cap. 2 -->

**TLS (Transport Layer Security)** — Protocolo criptográfico que cifra y autentica las comunicaciones de red; es la base de HTTPS y lo termina el proxy inverso con certificados de Let's Encrypt. <!-- fuente: nginx/lab.conf -->

**TOCTOU (Time-Of-Check to Time-Of-Use)** — Condición de carrera en la que el estado comprobado cambia antes de ejecutar la acción que dependía de esa comprobación. <!-- fuente: provision/reap.py -->

**TOTP (Time-based One-Time Password)** — Código de un solo uso derivado de un secreto compartido y la hora actual; segundo factor de autenticación habitual. <!-- fuente: provision/auth.py -->

**uvicorn** — Servidor de aplicaciones ASGI para Python que ejecuta aplicaciones web asíncronas como FastAPI; en este proyecto corre con un único *worker*. <!-- fuente: systemd/provision.service; README.md:Cotas -->

**VDI (Virtual Desktop Infrastructure)** — Modelo en el que los escritorios de los usuarios se ejecutan como máquinas virtuales en servidores del centro de datos y se entregan a dispositivos remotos. <!-- fuente: cap. 2 -->

**VM (máquina virtual)** — Emulación completa de una máquina física, con su propio núcleo y hardware virtualizado, gestionada por un hipervisor. <!-- fuente: Entorno de Laboratorio con LXD.md -->

**VNC (Virtual Network Computing)** — Sistema de escritorio remoto independiente de plataforma basado en el protocolo RFB, que transmite el contenido gráfico de la pantalla (*framebuffer*) a un cliente sin estado. <!-- fuente: cap. 2 (Richardson et al., 1998) -->

**WAL (Write-Ahead Logging)** — Modo de journaling de SQLite que registra los cambios en un diario previo, permitiendo lecturas concurrentes con un único escritor. <!-- fuente: provision/db.py -->

**WebSocket** — Canal de comunicación bidireccional y persistente entre navegador y servidor sobre HTTP, empleado por los clientes de escritorio remoto HTML5. <!-- fuente: cap. 2 -->

**xrdp** — Servidor RDP libre para Linux que expone la sesión gráfica local a clientes de escritorio remoto. <!-- fuente: build-lab-vm-base-mate.sh -->

**XSS (Cross-Site Scripting)** — Ataque de inyección en el que un atacante consigue ejecutar código JavaScript propio en el navegador de otro usuario dentro de una web legítima; se mitiga con políticas CSP y evitando interpolar contenido en el HTML. <!-- fuente: README.md:Identidad y seguridad -->

**ZFS** — Sistema de ficheros y gestor de volúmenes con instantáneas y clones nativos de bajo coste, usado por LXD como *backend* de almacenamiento. <!-- fuente: server-setup-lxd.sh -->
