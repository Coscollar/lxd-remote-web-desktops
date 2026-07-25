# Anexo A3. Guía de despliegue

Este anexo resume la puesta en marcha de la plataforma en un host propio. Es un resumen operativo de la guía de despliegue completa del repositorio (`docs/DEPLOY.md`), que incluye además el paso a paso por fases, la resolución de problemas y los anexos técnicos (contrato de la plantilla cloud-init, pasarela web, motor de políticas); para el detalle debe consultarse esa guía. <!-- fuente: docs/DEPLOY.md -->

## A3.1 Requisitos previos del host

Basta un **Ubuntu Server 22.04 o 24.04 limpio** con acceso root; el instalador incorpora el resto de dependencias. Deben cumplirse, no obstante, estas condiciones de entorno: <!-- fuente: docs/DEPLOY.md:0 Pre-requisitos -->

- **Virtualización KVM** disponible (`/dev/kvm`): VT-x/AMD-V habilitado en BIOS o virtualización anidada en el hipervisor. Sin ella, las máquinas virtuales no arrancan y el instalador aborta.
- **Conectividad saliente** (descarga de imágenes, Docker, certificados).
- **DNS**: un registro `A` que apunte `lab.<dominio>` a la IP pública del host (requisito de Let's Encrypt).
- **Firewall perimetral**: abrir únicamente 80/tcp y 443/tcp; en ningún caso 3389, 4822, 3306 ni 8000.
- **Cuenta SMTP** para el envío de los enlaces de acceso.
- **Recursos**: unos 4 GB de RAM por máquina virtual concurrente; el instalador avisa por debajo de 8 GB de RAM u 100 GB de disco libres.

## A3.2 Nota sobre finales de línea (CRLF)

El repositorio se edita desde Windows y los guiones de shell abortan si detectan finales de línea CRLF. El instalador único convierte CRLF→LF internamente; solo si se ejecutan fases a mano hay que convertir antes los guiones con `dos2unix`. <!-- fuente: README.md:Instalación paso a paso, docs/DEPLOY.md:1 -->

## A3.3 Instalación con un único comando

```bash
git clone https://github.com/Coscollar/lxd-remote-web-desktops.git
cd lxd-remote-web-desktops
sudo bash install-all.sh
```

Ejecutado sin parámetros desde un terminal, `install-all.sh` arranca un **asistente dirigido** que solicita el dominio público, el correo para los certificados, el primer administrador de la consola (que queda dado de alta automáticamente) y las credenciales SMTP (la contraseña se pide oculta); valida cada dato, muestra un resumen y pide confirmación antes de modificar nada. Para automatización sin terminal, los mismos datos se pasan por parámetros (`--domain`, `--email`, `--admin-email`, `--smtp-user`, `--smtp-pass`). <!-- fuente: docs/DEPLOY.md:Despliegue con un único script -->

Antes de actuar, el instalador ejecuta una **verificación previa** (*preflight*) que aborta ante condiciones irrecuperables (sistema operativo no soportado, ausencia de `/dev/kvm`, módulo ZFS no cargable, puertos 80/443 ocupados) y avisa ante condiciones degradadas (DNS sin resolver, `ufw` activo, RAM o disco escasos). El parámetro `--skip-preflight` degrada los abortos a avisos, bajo responsabilidad del operador. <!-- fuente: docs/DEPLOY.md:0b Preflight -->

Comportamientos relevantes del instalador:

- Es **reejecutable**: realiza siempre una desinstalación limpia previa.
- Los **secretos generados no se muestran por pantalla**; quedan en `/etc/provision/provision.env` (propietario `root:provision`, permisos 0640).
- Si el grupo `lxd` no está activo en la sesión, termina con código 100; basta cerrar sesión, volver a entrar y reejecutar.
- Incluye la fase de aplicaciones efímeras: amplía el pool de contenedores a 80 GB y su subred a /23, construye las imágenes de aplicación y activa el aislamiento y el temporizador de limpieza correspondientes. <!-- fuente: docs/DEPLOY.md:Despliegue con un único script -->

## A3.4 Validación tras la instalación

```bash
lxc storage list && lxc network list && lxc profile list && lxc image list local
sudo ss -tlnp | grep -E ':(3389|5900|3000|8888)'   # debe estar vacío
```

La segunda comprobación es el criterio de seguridad central: ningún puerto de escritorio remoto ni de aplicación debe escuchar públicamente (véase el Capítulo 7). <!-- fuente: README.md:Arquitectura (validación rápida) -->

## A3.5 Desinstalación y límites de reversión

```bash
sudo bash uninstall-all.sh --domain=lab.<dominio>            # pide confirmación
sudo bash uninstall-all.sh --purge-lxd --domain=lab.<dominio> # además, pools/redes/perfiles
```

La desinstalación elimina servicios, instancias, imágenes, la pila de Guacamole, la configuración de Nginx, las reglas de cortafuegos y los certificados; **no** desinstala los paquetes del sistema ni revierte la ampliación de pool y subred (reducir un pool ZFS es peligroso y la subred /23 no perjudica). <!-- fuente: README.md:Desinstalación -->

## A3.6 Advertencia sobre recreación de la infraestructura

Recargar la preconfiguración de LXD (`server-setup-lxd.sh --force-preseed`) es **destructivo**: sobrescribe toda la configuración del demonio. Solo debe usarse para una recreación planificada, con copia de seguridad previa. <!-- fuente: docs/DEPLOY.md:Recreación intencionada -->
