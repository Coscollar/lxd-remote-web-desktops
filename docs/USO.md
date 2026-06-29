# Uso del Entorno de Laboratorio con LXD

Guía de uso para alumnos y administradores. Para la instalación previa,
ver `docs/DEPLOY.md`.

## Para el alumno

1. **Entrar:** abre `https://lab.<tu-dominio>` en el navegador.
2. **Identificarse:** introduce tu correo electrónico (el mismo con el que
   estás matriculado).
3. **Magic link:** recibirás un email con un enlace
   `https://lab.<tu-dominio>/auth/verify?token=...`. Ábrelo (válido
   **15 minutos**). Si no lo ves, revisa spam.
4. **Dashboard:** si tienes varios labs, verás el dashboard con tus labs
   disponibles y las apps stateless de cada lab. Si solo tienes uno, irás
   directo al escritorio.
5. **Abrir escritorio:** clic en "Abrir escritorio" del lab deseado. Se lanza
   tu VM (si no existía) y se carga el escritorio MATE en el navegador vía
   Guacamole. El primer arranque tarda ~1-3 min (cloud-init).
6. **Abrir app stateless:** clic en "Abrir" de una app. Se lanza el contenedor
   (si no existía) y se abre en el navegador vía Nginx proxy.
7. **Trabajar:** usa el escritorio o las apps como uno local. Tu sesión RDP
   va por el túnel `guacd`; nunca se expone el puerto 3389. Las apps van por
   HTTP proxyado por Nginx (no usan guacd).

### Apps stateless

- **Apps compartidas (shared):** una instancia para todos los alumnos del lab.
  Útil para demos, documentación, apps de solo lectura.
- **Apps por alumno (per-alumno):** tu instancia propia, destruida tras
  `APP_IDLE_MINUTES` (30 min) de inactividad.
- **Reset de app per-alumno:** botón "Resetear" (destroy + launch).
- **Reset de app shared:** solo el admin (afecta a todos los alumnos).

### Scripts de laboratorio (dentro de la VM)

| Comando | Qué hace |
|---|---|
| `lab-save` | Crea un snapshot `k1..k5` de tu estado actual (rotación FIFO, máx. 5). |
| `lab-reset` | Restaura tu VM al estado `base` (pierdes cambios no guardados). Pide confirmación; usa `lab-reset --yes` para saltarla. |
| `lab-heartbeat` | Lo lanza systemd cada 5 min automáticamente (señal de vida). No lo ejecutes a mano. |

> El token de servicio en `/etc/lab/identity` es personal y rotatorio; no
> lo compartas ni lo borres.

### Sesión y caducidad

- La cookie de sesión alumno dura **1 hora**. La cookie admin dura **30 min**.
  Al caducar, vuelve a pedir un magic link.
- **Inactividad VM:** si tu VM lleva `IDLE_MINUTES` (por defecto 60) sin
  actividad, se destruye automáticamente. Vuelve a entrar para relanzarla.
- **Inactividad app per-alumno:** si tu app lleva `APP_IDLE_MINUTES` (por
  defecto 30) sin actividad, se destruye. Vuelve a abrirla para relanzarla.
- **Fin de curso/deadline:** si el admin fijó `COURSE_DEADLINE` o
  `labs.deadline`, las VMs y apps se destruyen al pasar esa fecha.

## Para el administrador

### Consola admin (navegador)

1. Abre `https://lab.<tu-dominio>/admin/login`.
2. Introduce tu email (debes estar en la tabla `admins`).
3. Recibirás un magic link admin (válido **5 min**). Ábrelo.
4. Si tienes TOTP activado (`ADMIN_TOTP_REQUIRED=1`), introduce el código
   de tu app TOTP.
5. Entrarás en la consola admin (cookie `admin_token`, TTL 30 min sin
   sliding). Recibirás un email de notificación de canje.

Desde la consola puedes:
- **Labs:** crear, editar, desactivar labs.
- **Matrículas:** matricular alumnos (email → lab).
- **Apps stateless:** añadir apps al catálogo (nombre, imagen
  `local:app-<id>`, puerto HTTP, shared/per-alumno, always_on, labs
  asignados).
- **Instancias:** listar todas (VMs + apps), filtrar, destruir, resetear,
  forzar creación de VM para un alumno.
- **Lanzar/detener apps shared** globales.

### Operaciones habituales

```bash
# Listar instancias activas (VMs)
sudo sqlite3 /var/lib/provision/provision.db \
  "SELECT nombre,alumno,lab,estado,ip_rdp,last_seen FROM instancias;"

# Listar instancias de apps stateless
sudo sqlite3 /var/lib/provision/provision.db \
  "SELECT nombre_lxd,app_id,alumno,estado,ip,last_seen FROM app_instances;"

# Listar catálogo de apps
sudo sqlite3 /var/lib/provision/provision.db \
  "SELECT id,nombre,shared,always_on,puerto_http FROM apps;"

# Ver instancias en LXD (VMs + apps)
lxc list --project labs
lxc list ^app- --project labs   # solo apps

# Destruir manualmente una instancia (VM o app)
curl -s -X POST "http://127.0.0.1:8000/admin/instances/lab1-alumno1/destroy?tipo=vm" \
  -H "X-Admin-Token: $ADMIN_TOKEN"
curl -s -X POST "http://127.0.0.1:8000/admin/instances/app-jupyter-alumno1/destroy?tipo=app" \
  -H "X-Admin-Token: $ADMIN_TOKEN"

# Disparar el reaper a mano (VMs)
curl -s -X POST http://127.0.0.1:8000/admin/reap -H "X-Admin-Token: $ADMIN_TOKEN"
# o vía systemd:
sudo systemctl start provision-reap.service

# Disparar el reaper de apps
sudo systemctl start provision-reap-apps.service

# Listar snapshots de una VM
lxc info <instancia> --project labs

# Reconstruir la imagen base VM (sube nueva versión lab-vm-base-v<fecha>)
sudo bash build-lab-vm-base-mate.sh --force

# Reconstruir imagen de app
sudo bash build-apps/build-app-jupyter.sh --force

# Rotar secretos JWT sin invalidar sesiones:
# poner el actual en JWT_SECRET_PREV y el nuevo en JWT_SECRET, reiniciar provision.
# Para admin: ADMIN_JWT_SECRET_PREV + ADMIN_JWT_SECRET.
```

### Matricular / dar de baja alumnos y admins

```bash
# Alta alumno
sudo sqlite3 /var/lib/provision/provision.db \
  "INSERT OR IGNORE INTO enrollments(alumno_id,email,lab,active,created_at)
   VALUES('alumno2','a2@ejemplo.com','lab1',1,datetime('now'));"

# Baja alumno (no borra histórico; desactiva)
sudo sqlite3 /var/lib/provision/provision.db \
  "UPDATE enrollments SET active=0 WHERE email='a2@ejemplo.com';"

# Alta admin
sudo sqlite3 /var/lib/provision/provision.db \
  "INSERT OR IGNORE INTO admins(email,role,active,created_at)
   VALUES('admin@ejemplo.com','admin',1,datetime('now'));"

# Baja admin
sudo sqlite3 /var/lib/provision/provision.db \
  "UPDATE admins SET active=0 WHERE email='admin@ejemplo.com';"
```

### Logs y diagnóstico

```bash
journalctl -u provision -f                      # API
journalctl -u provision-reap.service -e         # reaper VMs
journalctl -u provision-reap-apps.service -e    # reaper apps
docker compose -f guacamole/docker-compose.yml logs -f guacd
sudo tail -f /var/log/nginx/lab.access.log
lxc exec <instancia> --project labs -- cloud-init status --long
lxc exec <instancia> --project labs -- systemctl status xrdp
```

### Recreación intencionada de la infra LXD (destructiva)

```bash
sudo bash server-setup-lxd.sh --force-preseed
```

⚠️ Machaca toda la config del daemon LXD. Solo para recreación planificada;
haz snapshot/backup antes.

### Desinstalación completa del proyecto

```bash
# Con confirmación interactiva:
sudo bash uninstall-all.sh --domain=lab.<tu-dominio>

# Sin confirmación (automatización):
sudo bash uninstall-all.sh --yes --domain=lab.<tu-dominio>

# Incluye pools ZFS, redes, perfiles y proyectos LXD (NO desinstala el snap):
sudo bash uninstall-all.sh --purge-lxd --domain=lab.<tu-dominio>
```

Elimina: servicios systemd (incluido `provision-reap-apps`), instancias e
imágenes LXD (incluidas `app-*`), stack Docker Guacamole, site Nginx, reglas
iptables (incluidas iptables-apps y allowlist 8000), certs certbot, usuario
`provision` y directorios. **No** desinstala paquetes del sistema ni el
repo en disco. **No** revierte la ampliación de pool/subred (usar
`--purge-lxd` para eliminar pools completamente).

### Desinstalar paquetes del sistema (opcional, manual)

`uninstall-all.sh` no toca los paquetes del sistema. Si quieres eliminarlos
por completo (ej. para reutilizar el host para otra cosa):

```bash
sudo apt remove --purge nginx certbot docker.io iptables-persistent sqlite3 dos2unix
sudo apt autoremove --purge
sudo snap remove lxd          # ⚠️ elimina LXD completamente (incl. daemon)
```

⚠️ `snap remove lxd` borra el daemon LXD y todo su estado. Solo si no vas
a volver a usar LXD en el host.