**Entorno de Laboratorio con LXD**

**Objetivo:**  
Diseñar un sistema de laboratorios virtuales basado en Ubuntu con LXD (Linux Containers), donde los alumnos pueden acceder a máquinas virtuales y aplicaciones stateless a través del navegador, con provisión dinámica de instancias, persistencia de sesiones y opciones de guardado y reset. LXD es perfecto, porque maneja contenedores y VMs de forma ligera y escalable. La arquitectura debe ser escalable, fácil de implementar y ha de hacer uso de herramientas open-source para complementar LXD.

**Restricción firme:** LXD es la tecnología de virtualización elegida y **no se sustituye** por ninguna otra (no Docker, no Proxmox, no libvirt puro). Todo lo demás se ajusta alrededor de LXD. Tampoco se modifica el demonio LXD ni su configuración base (`lxd-preseed.yaml`, pools, redes, perfiles) salvo recreación intencionada; los ajustes incrementales se hacen vía `lxc` CLI.

**Arquitectura:**

* **Server:** Servidor Ubuntu LTS con LXD instalado (para contenedores/apps stateless y VMs de escritorio). LXD provee el aislamiento, el almacenamiento ZFS y las redes bridge; no se cambia.
* **Escritorio in-VM:** xrdp (ya en la imagen base `lab-vm-base`) expone RDP en el puerto 3389 **dentro** de la VM. No se sustituye por VNC directo ni se expone al exterior.
* **Acceso web:** Apache Guacamole Server + guacd. guacd tuneliza RDP/VNC; **nunca** se exponen 3389/5900 al navegador del alumno. Nginx como reverse proxy TLS por delante (certificados Let's Encrypt vía `certbot`).
* **Provisión dinámica:** API escrita en **Python con FastAPI** que expone un webhook / API simple para detectar accesos y lanzar/recuperar instancias on-demand. Estado mínimo persistido en **SQLite**. Arranque del servicio vía **systemd unit**. No se cambia de lenguaje ni de runtime.
* **Inicialización automática:** Uso de cloud-init en las VMs para configurar el entorno del alumno en el primer arranque (usuario, paquetes del lab, servicios, scripts de guardado/reset).
* **Persistencia:** Snapshots nativos de LXD **solo para VMs** (no para apps/contenedores, que serán stateless). Tagueo `{instancia}:base` + `k1..k5` con retención limitada para no saturar el pool ZFS.
* **URLs por Alumno/Lab:** Nginx en el edge, HTTPS con `certbot`, enruta `https://<alumno>.lab.<dominio>` hacia Guacamole.
* **Autenticación:** **Token de un solo uso enviado al correo del alumno (magic link).** Validez corta (p. ej. 15 min). Tras validarlo, el `provision-api` emite un **JWT firmado** (cookie httpOnly) con `{alumno, lab}` que Nginx/Guacamole honran durante la sesión. No se guardan contraseñas de alumnos en ningún sitio.
* **Escalabilidad:** Solo una instancia por lab y alumno, con auto-destrucción tras inactividad, fecha o fin de curso escolar. Scheduler de limpieza vía **systemd timer** (o ticker periódico dentro del `provision-api`).

**Flujo de autenticación (magic link por email):**

1. El alumno entra en `https://lab.<dominio>` e introduce su correo.
2. `provision-api` genera un token aleatorio de un solo uso, lo guarda en SQLite con caducidad (15 min) y envía un email con `https://lab.<dominio>/auth?token=<token>`.
3. El alumno abre el enlace; `provision-api` valida el token, lo marca como usado y emite un JWT firmado en una cookie httpOnly (`{alumno, lab, exp}`).
4. Nginx pasa el JWT al upstream. Guacamole abre la sesión del lab concreto; si no hay instancia activa, `provision-api` la lanza (cloud-init aplica la configuración inicial).
5. El JWT caduca con la sesión; volver a entrar pide un magic link nuevo.

**Flujo básico (actualizado con auth):**

1. El alumno recibe/abre su magic link y queda autenticado.
2. Nginx autentica (vía JWT) y redirige a Guacamole para su lab.
3. Si no hay instancia activa, en el caso de VMs, cloud-init aplica la configuración inicial automáticamente (instalación de servicios, creación del usuario y entorno de trabajo).
4. Si hay una instancia activa, se carga.
5. Conexión vía guacd al puerto 3389 (RDP) de la instancia. Nunca conexión directa al alumno.
6. Dentro de la VM, los scripts `lab-save` / `lab-reset` llaman al `provision-api` para hacer snapshot o restore.
7. Las apps (contenedores stateless) no permiten guardar estado.