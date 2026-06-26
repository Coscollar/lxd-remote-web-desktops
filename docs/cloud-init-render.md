# Contrato de renderización de `cloud-init-template.yml`

Este documento define cómo `provision-api` (FASE 3) renderiza la plantilla
`cloud-init-template.yml` al lanzar una VM de alumno. La plantilla **no** se
procesa por cloud-init tal cual: está escrita en **Jinja2** y provision-api la
compila a un `#cloud-config` YAML válido antes de inyectarla como
`user.user-data`.

## Por qué Jinja2 (y no `${}` nativo)

cloud-init soporta `${VAR}` solo en contadas claves y no permite condicionales.
Necesitamos omitir `packages:` cuando el lab no aporta delta, omitir `sudo:`
cuando `SUDO_MODE` es vacío, y omitir `ssh_authorized_keys` cuando no hay
claves. Eso exige `{% if %}`/`{% for %}`, que solo Jinja2 (o equivalente)
provee. Por tanto la plantilla es Jinja2 y provision-api es el único renderer.

## Variables interpolables

| Variable | Tipo | Origen | Validación |
|---|---|---|---|
| `ALUMNO` | str | JWT del alumno (claim `sub`) | `^[a-z0-9][a-z0-9-]{1,30}$` |
| `LAB` | str | ruta/claim del lab | `^[a-z0-9][a-z0-9-]{1,30}$` |
| `PROVISION_URL_VM` | str (URL) | config del host | `http://10.50.20.1:8000` (IP del host en bridge `lab-persistent`). **Nunca** `127.0.0.1` ni `localhost`: la VM no ve el loopback del host. |
| `LAB_SERVICE_TOKEN` | str (secret) | tabla `vm_tokens` (FASE 1.7) | no vacío; se inyecta en `/etc/lab/identity` (0640 root:root) |
| `SUDO_MODE` | str | config del lab | uno de: `ALL=(ALL) NOPASSWD:ALL`, `ALL=(ALL) ALL`, o vacío (sin sudo). Si vacío, la clave `sudo:` se omite. |
| `SSH_AUTHORIZED_KEYS` | list[str] | config del lab | lista de claves públicas OpenSSH. Si vacía, la clave `ssh_authorized_keys:` se omite. |
| `LAB_PACKAGES` | list[str] | config del lab | delta de paquetes del lab. **No** incluir MATE/xrdp/ssh (ya en `lab-vm-base`). Si vacía, la clave `packages:` se omite. |
| `TIMEZONE` | str | config del lab | tzdata válida (ej. `Europe/Madrid`). |

## Mecanismo de render

1. provision-api carga `cloud-init-template.yml` desde el repo (path fijado en config).
2. Construye el contexto con las variables de la tabla, validadas previamente.
3. Renderiza con Jinja2 (`autoescape=False` porque producimos YAML, no HTML;
   pero las variables se escapan como literales YAML entre comillas dobles donde
   corresponda — `sudo`, `content` de `/etc/lab/identity`).
4. **Whitelist estricta**: rechazar el render si cualquier variable falla su
   regex/enum. En particular `SUDO_MODE` debe estar en el conjunto cerrado de
   tres valores o vacío; cualquier otra cosa aborta el lanzamiento.
5. Parsea el resultado con `yaml.safe_load` y verifica que empieza por
   `#cloud-config` y que las claves top-level son un subconjunto conocido
   (`users`, `hostname`, `manage_etc_hosts`, `fqdn`, `package_update`,
   `packages`, `write_files`, `runcmd`, `timezone`). Si no parsea, abortar.
6. Pasa el YAML renderizado **por stdin** a:
   ```
   lxc launch local:lab-vm-base <alumno>-<lab> --vm \
     -p persistent --project labs \
     -c user.user-data=-
   ```
   El render se envía por stdin al proceso `lxc`, **no** como argumento shell.
   Esto evita inyección de flags y límites de longitud de línea de comandos.

## Qué NO hacer

- **No commitear el render.** El YAML con el token real nunca se escribe a disco
  en el repo ni en el host. Se pasa in-memory al `lxc launch`.
- **No usar `127.0.0.1` ni `localhost`** como `PROVISION_URL_VM`. La VM vive en
  su propio namespace de red (`lab-persistent`, 10.50.20.0/24); el loopback del
  host no es alcanzable. Usar la IP del host en ese bridge (por defecto
  `10.50.20.1`).
- **No usar `package_upgrade: true`.** Rompe idempotencia: en una re-aplicación
  de cloud-init cambiaría versiones de paquetes base y podría desincronizar con
  el snapshot base. Solo `package_update: true` (refresca índices APT).
- **No incluir `chpasswd`**, `ssh_pwauth: true` ni `final_modules: []`. Modelo A:
  sin password RDP conocida; el autologin lo gestiona `lab-vm-base`.
- **No reinstalar** MATE, xrdp, ssh, ni ningún paquete ya presente en
  `lab-vm-base`. `LAB_PACKAGES` es **delta** del lab.
- **No pasar `user.user-data` como argumento** al `lxc launch` (riesgo de
  inyección de flags y truncamiento). Siempre stdin (`-c user.user-data=-`).
- **No renderizar sin validar**. Cualquier fallo de regex/enum aborta el
  lanzamiento antes de tocar LXD.

## Idempotencia y guardián

El `runcmd` está envuelto en un guardián: si existe `/etc/lab/.provisioned`,
el bloque entero se omite. Al final, se escribe
`sha256sum /etc/lab/identity > /etc/lab/.provisioned`. Esto permite detectar
cambios de plantilla/token: si provision-api re-aplica cloud-init con un token
distinto, el sha cambia y el operador puede forzar re-provisionado borrando el
guardián. En operación normal, una re-aplicación de cloud-init es no-op.

## Validación manual (FASE 2)

```bash
# Render manual de prueba (provision-api debería exponer un endpoint /render
# o un CLI `python -m provision.render --alumno test --lab lab1 ...`):
lxc launch local:lab-vm-base test-alumno-lab1 --vm \
  -p persistent --project labs -c user.user-data=- < rendered.yml

lxc exec test-alumno-lab1 -- cloud-init status --wait      # status: done
lxc exec test-alumno-lab1 -- systemctl is-active xrdp       # active
lxc exec test-alumno-lab1 -- cat /etc/lab/.provisioned      # existe (sha256)
lxc exec test-alumno-lab1 -- lab-save                       # reach provision-api (mock)

# Limpieza:
lxc delete test-alumno-lab1 --force --project labs
```