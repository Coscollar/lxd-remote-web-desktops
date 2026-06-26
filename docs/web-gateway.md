# FASE 4 — Acceso web (Guacamole + guacd + Nginx)

## Topología

```
Navegador ──HTTPS──▶ Nginx (:443)
                       │ auth_request /verify ──HTTP──▶ provision-api (:8000)
                       │   (JWT httpOnly en cookie; valida y devuelve
                       │    X-Lab-Alumno / X-Lab-Name)
                       ▼
                 Guacamole Server (:8080, 127.0.0.1)
                       │ Remote-User = "<alumno>-<lab>"
                       ▼
                      guacd (:4822, 127.0.0.1)
                       ▼  (TCP, host → 10.50.20.0/24)
                 VM alumno (xrdp :3389, NO expuesto)
```

**Regla de oro:** guacd SIEMPRE intermedio. El navegador nunca alcanza
`3389` ni `5900`. Nginx enruta a Guacamole (8080), nunca a guacd ni a las VMs.

## Puertos y enrutamiento

| Servicio        | Bind            | Origen permitido          | Destino real        |
|-----------------|-----------------|---------------------------|---------------------|
| Nginx           | 0.0.0.0:80/443  | Internet (TLS)            | Guacamole 8080      |
| provision-api   | 127.0.0.1:8000  | Nginx (`auth_request`)    | —                   |
| Guacamole Server| 127.0.0.1:8080  | Nginx (loopback)           | guacd 4822          |
| guacd           | 127.0.0.1:4822  | Guacamole (loopback)       | VM 10.50.20.x:3389  |
| mysql           | 127.0.0.1:3306  | Guacamole (loopback)       | —                   |

`docker ps` debe mostrar guacd **sin** columna `PORTS` publicada
(`network_mode: host` + bind 127.0.0.1).

## Opción A (dev/lab) vs Opción C (deuda prod)

- **Opción A (actual):** guacd, guacamole y mysql en `network_mode: host`,
  bind estricto `127.0.0.1`. guacd con `cap_drop: [ALL]` y
  `security_opt: [no-new-privileges]`. Suficiente para un host único.
- **Opción C (deuda prod):** guacd nativo con socket Unix en lugar de TCP
  4822, y Guacamole en su propia red Docker (no host). Reduce superficie
  de loopback y elimina el puerto TCP. Migrar cuando se multiplique el
  número de hosts o se aísle Guacamole por tenant.

## certbot: HTTP-01 vs wildcard DNS-01

- **HTTP-01 (actual):** host único `lab.<dominio>`. certbot con `--nginx`
  sirve `/.well-known/acme-challenge/` en :80. Suficiente y simple.
- **DNS-01 (wildcard, futuro):** si se pasa a un subdominio por alumno
  (`<alumno>.lab.<dominio>`), HTTP-01 por host deja de escalar. DNS-01
  con wildcard `*.lab.<dominio>` + un único cert. Requiere plugin de DNS
  provider y credenciales fuera del repo. **No adoptar hasta que la
  identidad deje de venir del JWT** — hoy el subdominio no identifica al
  alumno, así que un wildcard no aporta valor y sí complejidad.

## Identidad

- **SOLO desde el JWT** vía `auth_request_set $lab_alumno /
  $lab_name` (headers `X-Lab-Alumno` / `X-Lab-Name` devueltos por
  provision-api `/verify`).
- El subdominio **no** identifica al alumno. Nginx SIEMPRE sobreescribe
  `Remote-User` con `"$lab_alumno-$lab_name"`; el cliente no puede
  inyectarlo.
- Modelo A (sin password RDP): la conexión Guacamole se crea sin password
  (autologin configurado en la imagen base). El alumno no se loguea dos
  veces.

## Aislamiento inter-VM (iptables)

```bash
# DROP todo el tráfico entre VMs del lab-persistent (no solo 3389).
sudo iptables -A FORWARD -i lab-persistent -o lab-persistent -j DROP

# ACCEPT solo desde el host (10.50.20.1 en bridge) hacia VMs:3389.
sudo iptables -I FORWARD -s 10.50.20.1 -d 10.50.20.0/24 -p tcp --dport 3389 -j ACCEPT

# Defensa en profundidad: restringir al UID de guacd en OUTPUT.
GUACD_UID="$(docker compose exec -T guacd id -u guacd 2>/dev/null || echo 1000)"
sudo iptables -I OUTPUT -m owner --uid-owner "${GUACD_UID}" -d 10.50.20.0/24 -p tcp --dport 3389 -j ACCEPT
```

Persistir con `iptables-persistent` (`netfilter-persistent save`).

## Contrato con provision-api

- Tras `healthcheck_rdp` OK, provision-api escribe en la DB JDBC de
  Guacamole una conexión `<alumno>-<lab>` con `hostname=<vm-ip>`,
  `port=3389`, `username=alumno`, `ignore-cert=true`, `security=any`,
  **sin password** (Modelo A).
- IP dinámica: provision-api reescribe `hostname` tras cada healthcheck
  dentro de la transición a estado `lista`.
- En `destroy`: `DELETE` de la conexión y del usuario Guacamole asociado.
- `/verify` devuelve `200` + `X-Lab-Alumno`/`X-Lab-Name` si el JWT es
  válido y la VM está en estado `lista`; `401` en caso contrario (Nginx
  corta antes de llegar a Guacamole).

## Validaciones

```bash
# 1. Sin cookie → 401.
curl -kI https://lab.<dominio>/guacamole/ | head -1   # 401

# 2. Con cookie JWT válida → 200 y escritorio MATE vía navegador.

# 3. guacd sin puertos publicados.
docker ps --format '{{.Names}} {{.Ports}}' | grep guacd
#   guacd  (sin nada en la columna Ports)

# 4. iptables inter-VM.
sudo iptables -L FORWARD -n | grep -E 'DROP|3389'

# 5. 3389 NO escucha en el host.
sudo ss -tlnp | grep 3389                          # debe estar vacío

# 6. Conexiones runtime en Guacamole.
docker compose exec -T mysql \
  mysql -h127.0.0.1 -uroot -p"$GUAC_MYSQL_ROOT" guacamole \
  -e "SELECT connection_name, hostname FROM guacamole_connection;"

# 7. Hook de renovación.
ls -l /etc/letsencrypt/renewal-hooks/deploy/nginx-reload.sh
sudo certbot renew --dry-run
```

## Logging seguro

- `log_format lab_safe` SIN `$http_cookie` (regla 4.7).
- uvicorn (provision-api) con `--log-config` que redacte `Authorization`
  y `Cookie` (filtro de logging).