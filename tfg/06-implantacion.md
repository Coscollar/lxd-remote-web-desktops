# Capítulo 6. Implantación

Este capítulo describe la puesta en producción: requisitos del servidor y verificación previa, instalador dirigido con un solo comando, operación del sistema resultante y su desinstalación. El objetivo de diseño fue que la implantación no exigiera conocer el interior de la plataforma (OE4, sección 1.2).

## 6.1 Requisitos del host y verificación previa

El único requisito de partida es un **Ubuntu Server 22.04 o 24.04 limpio** con acceso root: el instalador aporta el resto de dependencias (LXD, Nginx, certbot, Docker, Python, utilidades). Alrededor del host se necesitan un registro DNS tipo A hacia su IP pública —imprescindible para que Let's Encrypt emita el certificado—, los puertos 80 y 443 abiertos en el cortafuegos perimetral (y **solo** esos), virtualización por hardware (`/dev/kvm`), salida a Internet y una cuenta SMTP para los *magic links*. En recursos, el mínimo del que avisa el instalador son 8 GB de RAM —una VM concurrente aproximadamente— y 100 GB de disco libres; el host de referencia del análisis de capacidad tiene 32 GB (sección 7.3). <!-- fuente: docs/DEPLOY.md:0; install-all.sh (preflight); README.md:Instalación -->

Implantar sobre un host inadecuado producía fallos tardíos y crípticos (sin `/dev/kvm`, la construcción de la imagen base fracasa a mitad). Por ello el instalador comienza con una verificación previa (*preflight*) **fail-fast**: comprueba el host antes de modificar nada y aborta si falta un requisito esencial, distinguiendo errores que impiden continuar (ABORT) de avisos (WARN); la Tabla 6.1 la resume. Algunas comprobaciones necesitan paquetes para poder verificarse (el módulo ZFS, `snap`), así que el *preflight* ejecuta antes los chequeos de solo lectura e instala lo imprescindible solo si no hay errores previos. El indicador `--skip-preflight` degrada los ABORT a avisos, bajo responsabilidad del operador. <!-- fuente: install-all.sh:0b; docs/DEPLOY.md:0b -->

| Comprobación | Si falla |
|---|---|
| Sistema operativo Ubuntu 22.04/24.04 | **ABORT** |
| Virtualización KVM (`/dev/kvm` presente) | **ABORT** |
| Módulo ZFS cargable (instala `zfsutils-linux` y los módulos extra del kernel si faltan) | **ABORT** si sigue sin cargar, con diagnóstico (kernels *cloud* sin módulos extra) |
| `snapd` instalado y sembrado (espera hasta 180 s) | Lo instala si falta; **WARN** si no termina de sembrarse |
| Puertos 80/443 libres (u ocupados solo por Nginx) | **ABORT** |
| El dominio indicado resuelve por DNS | **WARN** (el veredicto final lo da certbot) |
| Cortafuegos `ufw` activo (convive mal con las reglas del proyecto) | **WARN** |
| RAM ≥ 8 GB y disco libre ≥ 100 GB | **WARN** |

*Tabla 6.1. Comprobaciones del preflight del instalador y consecuencia de cada fallo. Elaboración propia a partir del código del instalador.* <!-- fuente: install-all.sh:0b; docs/DEPLOY.md:0b -->

## 6.2 El instalador dirigido

La implantación completa se realiza con un único comando (`sudo bash install-all.sh`). Sin argumentos, arranca un **asistente dirigido** que solicita los cuatro datos que no pueden generarse: el dominio público, el correo de avisos de Let's Encrypt, el correo del primer administrador (dado de alta automáticamente en la tabla `admins`) y las credenciales SMTP, con la contraseña oculta para que no quede en el historial ni en la lista de procesos. Cada dato se valida contra una expresión regular de **conjunto de caracteres cerrado**: rechaza erratas de inmediato y, al excluir todo carácter especial en un guion de shell sin consultas parametrizadas, hace seguras las interpolaciones posteriores (SQL del alta de administrador, configuración de Nginx, invocación de certbot). Antes de tocar nada, el asistente muestra un resumen y pide confirmación; cancelar no deja rastro. Para automatización sin terminal existen indicadores equivalentes (`--domain`, `--email`, `--admin-email`, `--smtp-user/-pass`), cuyos valores sí quedan visibles en la lista de procesos. <!-- fuente: install-all.sh (asistente y validación); docs/DEPLOY.md:Despliegue con un único script --> La Figura 6.1 muestra el asistente en ejecución.

*Figura 6.1. Asistente dirigido de instalación: solicitud de datos con validación, resumen y confirmación previa.* [RELLENAR: captura de pantalla del asistente de `install-all.sh` en un terminal]

Confirmados los datos, el instalador encadena sin más intervención cuatro bloques: preparación (conversión CRLF→LF, *preflight*, desinstalación previa —todo arranque es limpio y reejecutable por construcción— y dependencias no interactivas); infraestructura (imagen base, ampliaciones no destructivas de *pool* y subred, imágenes de aplicaciones, y el grupo `lxd`: si no está activo en la sesión, el script termina con el código reservado 100 y reintenta tras activarlo o reiniciar sesión); servicios (orquestador con secretos generados, Guacamole, Nginx con TLS y aislamiento); y verificación final (detalle fase a fase en el Anexo A3). Si una fase falla (p. ej. certbot ante un DNS aún no propagado), el instalador se detiene con el error visible y basta corregir la causa y reejecutar, sin deshacer nada a mano. <!-- fuente: install-all.sh (pasos 0-6, exit 100); README.md:Instalación; docs/DEPLOY.md:0b -->

Los **secretos** merecen mención propia: el instalador genera con `openssl rand` los ocho que el sistema necesita (firmas de sesión de alumno y administrador con sus secretos previos de rotación, testigos de servicio, testigo interno proxy→API, clave TOTP) y no imprime ninguno por pantalla; quedan en `/etc/provision/provision.env` (root, grupo del servicio, permisos 0640), de donde los leen el orquestador y el generador de la configuración interna de Nginx, que aborta si el testigo interno falta o es corto. <!-- fuente: install-all.sh:4.2; docs/DEPLOY.md:4.2 --> Si el operador pospuso el SMTP, el resumen final le recuerda que sin él nadie puede iniciar sesión y dónde rellenarlo (en desarrollo se empleó el servicio de pruebas Mailtrap[^1]). El resultado visible de la implantación son el portal del alumno y la consola de administración, que muestran las Figuras 6.2 y 6.3.

*Figura 6.2. Portal del alumno tras la implantación: acceso por correo y panel de laboratorios y aplicaciones.* [RELLENAR: captura del portal / dashboard del alumno]

*Figura 6.3. Consola de administración: gestión de laboratorios, matrículas, aplicaciones e instancias.* [RELLENAR: captura de la consola /admin]

## 6.3 Operación del sistema

El sistema implantado queda gobernado por systemd. El servicio `provision.service` ejecuta el orquestador bajo un usuario dedicado (`provision`, miembro del grupo `lxd`); dos temporizadores invocan la destrucción automática: `provision-reap.timer` cada cinco minutos para las VMs y `provision-reap-apps.timer` cada dos para las aplicaciones (cadencia menor por su plazo de inactividad más corto —30 min frente a 60— y el menor coste de cada pasada). El certificado TLS se renueva de forma desatendida, con un gancho que valida la configuración de Nginx antes de recargarla. <!-- fuente: systemd/; docs/DEPLOY.md:3.2, 4.2 y 5 --> En cada arranque se ejecuta la **reconciliación en modo simulado** de la sección 4.2.1: las instancias en base de datos ausentes de LXD se marcan huérfanas y las aplicaciones compartidas siempre activas ausentes se reencolan, sin borrar nunca nada a ciegas. <!-- fuente: provision/main.py (lifespan); docs/DEPLOY.md:Anexo C.5 -->

Dos procedimientos operativos completan el cuadro. Primero, la **rotación de secretos sin cortar sesiones**: cada secreto de firma tiene una variable "previa" (`JWT_SECRET_PREV`, `ADMIN_JWT_SECRET_PREV`); para rotar, el secreto vigente pasa a la variable previa y el nuevo ocupa la principal, de modo que las sesiones firmadas con el secreto saliente sigan verificándose hasta su caducidad natural. <!-- fuente: docs/USO.md:Operación avanzada --> Segundo, el **alta de administradores solo por SQL**: deliberadamente no existe ni interfaz ni endpoint para crear administradores, porque conceder el privilegio máximo desde la propia consola convertiría el compromiso de una cuenta de administrador en la capacidad de crear otras; la operación exige acceso de shell al servidor (el primer administrador lo siembra el instalador por esta misma vía). <!-- fuente: docs/USO.md:Para el administrador; README.md:Identidad y seguridad --> El diagnóstico cotidiano se realiza con `journalctl` sobre los servicios y con los registros de acceso de Nginx, que excluyen secretos por diseño (sección 3.3).

## 6.4 Desinstalación y límites de reversión

La desinstalación es igualmente un único comando (`uninstall-all.sh`), con confirmación interactiva u omisión explícita (`--yes`). Elimina servicios y temporizadores, todas las instancias e imágenes LXD (incluidas las aplicaciones), el stack de Guacamole, el sitio de Nginx, las reglas de cortafuegos, los certificados, el usuario de servicio y los directorios de datos. Deliberadamente **no** desinstala los paquetes del sistema ni borra el repositorio, y **no revierte** dos cambios: la ampliación del *pool* de aplicaciones a 80 GB —encoger ZFS es arriesgado y no compensa automatizar— y la subred /23, inocua. Para una limpieza total (*pools*, redes, perfiles, proyectos) existe `--purge-lxd`. <!-- fuente: uninstall-all.sh; README.md:Desinstalación; docs/DEPLOY.md:Desinstalación completa --> El procedimiento paso a paso, la resolución de problemas y las validaciones detalladas se recogen en el Anexo A3.

Implantado el sistema, queda demostrar que funciona y cuantificar hasta dónde llega. El capítulo siguiente presenta la estrategia de pruebas, los criterios de aceptación verificados de extremo a extremo y el análisis de capacidad de la plataforma.

[^1]: Mailtrap, servicio SMTP de pruebas para desarrollo — https://mailtrap.io/ [consulta: 16 de julio de 2026].
