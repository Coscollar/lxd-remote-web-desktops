**Entorno de Laboratorio con LXD**

**Objetivo:**  
Diseñar un sistema de laboratorios virtuales basado en Ubuntu con LXD (Linux Containers), donde los alumnos pueden acceder a máquinas virtuales y aplicaciones stateless a través del navegador, con provisión dinámica de instancias, persistencia de sesiones y opciones de guardado y reset. LXD es perfecto, porque maneja contenedores y VMs de forma ligera y escalable. La arquitectura debe ser escalable, fácil de implementar y ha de hacer uso de herramientas open-source para complementar LXD.

**Restricción firme:** LXD es la tecnología de virtualización elegida y **no se sustituye** por ninguna otra (no Docker, no Proxmox, no libvirt puro). Todo lo demás se ajusta alrededor de LXD. Tampoco se modifica el demonio LXD ni su configuración base (`lxd-preseed.yaml`, pools, redes, perfiles) salvo recreación intencionada; los ajustes incrementales se hacen vía `lxc` CLI.

**Arquitectura:**

* **Server:** Servidor Ubuntu LTS con LXD instalado (para contenedores/apps stateless y VMs de escritorio). LXD provee el aislamiento, el almacenamiento ZFS y las redes bridge; no se cambia.
* **Escritorio in-VM:** xrdp (ya en la imagen base `lab-vm-base`) expone RDP en el puerto 3389 **dentro** de la VM. No se sustituye por VNC directo ni se expone al exterior.
* **Apps stateless in-container:** contenedores LXD (perfil `stateless`, red `lab-stateless`, pool `stateless-pool`) que exponen un servicio HTTP en un puerto interno. El alumno los abre en el navegador vía Nginx proxy (path prefix `/apps/{app_id}/`). **No** pasan por guacd (son HTTP, no RDP/VNC). Imagen preconstruida `local:app-<id>` por app; lanzamiento on-demand vía job queue.
* **Acceso web:** Apache Guacamole Server + guacd. guacd tuneliza RDP/VNC; **nunca** se exponen 3389/5900 al navegador del alumno. Nginx como reverse proxy TLS por delante (certificados Let's Encrypt vía `certbot`).
* **Portal web:** FastAPI sirve las páginas HTML (Jinja2 + StaticFiles): login del alumno, dashboard (escoger lab + apps), consola admin. Nginx enruta por *locations*: `/` y `/dashboard` → provision-api; `/desktop/{lab}/` → Guacamole (solo si JWT `scope=lab`); `/apps/{app_id}/` → app stateless (proxy HTTP dinámico); `/admin/*` → provision-api (consola admin).
* **Provisión dinámica:** API escrita en **Python con FastAPI** que expone un webhook / API simple para detectar accesos y lanzar/recuperar instancias on-demand. Estado mínimo persistido en **SQLite**. Arranque del servicio vía **systemd unit**. No se cambia de lenguaje ni de runtime.
* **Apps stateless on-demand:** el provision-api lanza apps stateless (contenedores) por demanda del alumno o del admin. Catálogo en BD (tabla `apps`): cada app define imagen LXD, puerto HTTP, modo `shared` (una instancia para todos) o `per-alumno` (una por alumno), `always_on` (siempre viva). Job queue persistente (reusa `jobs` con `tipo='launch_app'`). Reaper standalone para apps (idle destroy, shared `always_on=1` exentas).
* **Inicialización automática:** Uso de cloud-init en las VMs para configurar el entorno del alumno en el primer arranque (usuario, paquetes del lab, servicios, scripts de guardado/reset).
* **Persistencia:** Snapshots nativos de LXD **solo para VMs** (no para apps/contenedores, que serán stateless). Tagueo `{instancia}:base` + `k1..k5` con retención limitada para no saturar el pool ZFS.
* **URLs por Alumno/Lab:** Nginx en el edge, HTTPS con `certbot`, enruta `https://lab.<dominio>` hacia Guacamole (escritorios) o apps stateless (HTTP proxy).
* **Autenticación:** **Token de un solo uso enviado al correo del alumno (magic link).** Validez corta (p. ej. 15 min). Tras validarlo, el `provision-api` emite un **JWT firmado** (cookie httpOnly) con `{alumno, lab, scope}` que Nginx/Guacamole honran durante la sesión. No se guardan contraseñas de alumnos en ningún sitio. **Auth admin:** magic link por email (sin password), tabla `admins` separada, `ADMIN_JWT_SECRET` separado, cookie `admin_token` Path=/admin, TTL 30min sin sliding. `X-Admin-Token` conservado para automatización. TOTP opcional en prod.
* **Multi-lab:** el JWT del alumno lleva `lab` nullable + claim `scope` (`dashboard`|`lab`|`admin`). Si el alumno tiene >1 matrícula, entra al dashboard (`scope=dashboard`, `lab=null`) y escoge lab (`POST /lab/select` reemite JWT `scope=lab`).
* **Escalabilidad:** Solo una instancia por lab y alumno, con auto-destrucción tras inactividad, fecha o fin de curso escolar. Scheduler de limpieza vía **systemd timer** (o ticker periódico dentro del `provision-api`). Apps stateless: `shared` por defecto (1 instancia para todos los alumnos del lab); `per-alumno` opt-in. Hard cap de inventario por RAM/pool/subred. `stateless-pool` 80GB → ~60-80 contenedores concurrentes. `lab-stateless` /23 → ~510 IPs. Cota realista: ~30-50 alumnos con apps (shared por defecto) + ≤10-12 contenedores app concurrentes pool-wide en host 32GB.

**Flujo de autenticación (magic link por email):**

1. El alumno entra en `https://lab.<dominio>` e introduce su correo.
2. `provision-api` genera un token aleatorio de un solo uso, lo guarda en SQLite con caducidad (15 min) y envía un email con `https://lab.<dominio>/auth/verify?token=<token>`. Si el alumno tiene >1 matrícula activa, el token se guarda con `lab=null` (multi-lab).
3. El alumno abre el enlace; `provision-api` valida el token, lo marca como usado y emite un JWT firmado en una cookie httpOnly (`{alumno, lab, scope, exp}`). Si el token tenía `lab` fijado → JWT `scope=lab` → redirect `/lab/start`. Si `lab=null` (multi-lab) → JWT `scope=dashboard` → redirect `/dashboard`.
4. Si está en el dashboard (`scope=dashboard`), el alumno escoge lab → `POST /lab/select {lab}` valida la matrícula y reemite el JWT con `scope=lab` y el lab seleccionado → redirect `/lab/start`.
5. Nginx autentica (vía JWT, `auth_request /verify`) y redirige a Guacamole para su lab. Si no hay instancia activa, `provision-api` la lanza (cloud-init aplica la configuración inicial).
6. El JWT caduca con la sesión; volver a entrar pide un magic link nuevo.

**Flujo de autenticación admin:**

1. El admin entra en `https://lab.<dominio>/admin/login` e introduce su correo (debe estar en la tabla `admins`).
2. `provision-api` genera un magic link admin (TTL 5 min) y envía email.
3. El admin abre el enlace; `provision-api` canjea el token, emite JWT admin (`ADMIN_JWT_SECRET` separado, `scope=admin`) en cookie `admin_token` (Path=/admin, TTL 30min sin sliding), envía email de notificación de canje (sin enlaces accionables) y redirige a `/admin`.
4. Desde la consola admin puede gestionar labs, matrículas, apps stateless (catálogo) e instancias (VMs + apps: crear, eliminar, resetear).

**Flujo básico (actualizado con auth + apps stateless):**

1. El alumno recibe/abre su magic link y queda autenticado.
2. Si tiene varios labs, ve el dashboard y escoge uno. Si tiene uno, va directo.
3. Nginx autentica (vía JWT) y redirige a Guacamole para su lab.
4. Si no hay instancia activa, en el caso de VMs, cloud-init aplica la configuración inicial automáticamente (instalación de servicios, creación del usuario y entorno de trabajo).
5. Si hay una instancia activa, se carga.
6. Conexión vía guacd al puerto 3389 (RDP) de la instancia. Nunca conexión directa al alumno.
7. Dentro de la VM, los scripts `lab-save` / `lab-reset` llaman al `provision-api` para hacer snapshot o restore.
8. Las apps (contenedores stateless) no permiten guardar estado. Reset = destroy + launch (recreate).

**Flujo de apps stateless:**

1. El alumno, desde el dashboard, ve las apps disponibles en sus labs (catálogo `apps` ↔ `app_lab` ↔ `enrollments`).
2. Al abrir una app, `POST /apps/{app_id}/start` encola un job `launch_app` (si no existe la instancia).
3. El worker lanza el contenedor LXD (`lxc launch local:app-<id> app-<id>[-<alumno>] -p stateless --project labs`), healthcheck HTTP, resuelve IP.
4. El alumno abre `https://lab.<dominio>/apps/{app_id}/` → Nginx `auth_request /verify/app` (READ-ONLY, valida JWT + pertenencia app↔alumno + IP rango) → `proxy_pass http://<app-ip>:<puerto>`.
5. La app hace heartbeat cada 5min (`POST /heartbeat` con service token). Reaper destruye tras `APP_IDLE_MINUTES=30` (per-alumno) o `SHARED_IDLE_HOURS=6` (shared no always_on).