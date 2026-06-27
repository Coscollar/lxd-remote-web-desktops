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
4. **Escritorio:** tras validar, se lanza tu VM (si no existía) y se carga
   el escritorio MATE en el navegador vía Guacamole. El primer arranque
   tarda ~1-3 min (cloud-init).
5. **Trabajar:** usa el escritorio como uno local. Tu sesión RDP va por el
   túnel `guacd`; nunca se expone el puerto 3389.

### Scripts de laboratorio (dentro de la VM)

| Comando | Qué hace |
|---|---|
| `lab-save` | Crea un snapshot `k1..k5` de tu estado actual (rotación FIFO, máx. 5). |
| `lab-reset` | Restaura tu VM al estado `base` (pierdes cambios no guardados). Pide confirmación; usa `lab-reset --yes` para saltarla. |
| `lab-heartbeat` | Lo lanza systemd cada 5 min automáticamente (señal de vida). No lo ejecutes a mano. |

> El token de servicio en `/etc/lab/identity` es personal y rotatorio; no
> lo compartas ni lo borres.

### Sesión y caducidad

- La cookie de sesión dura **1 hora**. Al caducar, vuelve a pedir un magic
  link.
- **Inactividad:** si tu VM lleva `IDLE_MINUTES` (por defecto 60) sin
  actividad, se destruye automáticamente. Vuelve a entrar para relanzarla.
- **Fin de curso/deadline:** si el admin fijó `COURSE_DEADLINE` o
  `labs.deadline`, las VMs se destruyen al pasar esa fecha.

## Para el administrador

### Operaciones habituales

```bash
# Listar instancias activas
sudo sqlite3 /var/lib/provision/provision.db \
  "SELECT nombre,alumno,lab,estado,ip_rdp,last_seen FROM instancias;"

# Ver instancias en LXD
lxc list --project labs

# Destruir manualmente una instancia
curl -s -X POST "http://127.0.0.1:8000/admin/destroy?instancia=lab1-alumno1" \
  -H "X-Admin-Token: $ADMIN_TOKEN"

# Disparar el reaper a mano
curl -s -X POST http://127.0.0.1:8000/admin/reap -H "X-Admin-Token: $ADMIN_TOKEN"
# o vía systemd:
sudo systemctl start provision-reap.service

# Listar snapshots de una VM
lxc info <instancia> --project labs

# Reconstruir la imagen base (sube nueva versión lab-vm-base-v<fecha>)
sudo bash build-lab-vm-base-mate.sh --force

# Rotar secretos JWT sin invalidar sesiones:
# poner el actual en JWT_SECRET_PREV y el nuevo en JWT_SECRET, reiniciar provision.
```

### Matricular / dar de baja alumnos

```bash
# Alta
sudo sqlite3 /var/lib/provision/provision.db \
  "INSERT OR IGNORE INTO enrollments(alumno_id,email,lab,active,created_at)
   VALUES('alumno2','a2@ejemplo.com','lab1',1,datetime('now'));"

# Baja (no borra histórico; desactiva)
sudo sqlite3 /var/lib/provision/provision.db \
  "UPDATE enrollments SET active=0 WHERE email='a2@ejemplo.com';"
```

### Logs y diagnóstico

```bash
journalctl -u provision -f                      # API
journalctl -u provision-reap.service -e         # reaper
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