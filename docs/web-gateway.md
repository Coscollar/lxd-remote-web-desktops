# FASE 4 — Acceso web (Guacamole + guacd + Nginx)

## Topología

```
Navegador ──HTTPS──▶ Nginx (:443)
                        │
                        ├── / , /dashboard , /lab/* , /api/* , /admin/* , /static/*
                        │   auth_request /verify (o /admin/verify para /admin/*)
                        │   → provision-api (:8000)
                        │
                        ├── /desktop/{lab}/...
                        │   auth_request /verify (exige X-Lab-Scope=lab)
                        │   → Guacamole Server (:8080)
                        │       → guacd (:4822)
                        │           → VM alumno (xrdp :3389, NO expuesto)
                        │
                        └── /apps/{app_id}/...
                            auth_request /verify/app (READ-ONLY, valida pertenencia)
                            → app stateless (10.50.10.x:puerto, HTTP directo, NO guacd)
```

**Regla de oro:** guacd SIEMPRE intermedio para RDP/VNC. El navegador nunca
alcanza `3389` ni `5900`. Nginx enruta a Guacamole (8080) solo para
`/desktop/{lab}/`, nunca a guacd ni a las VMs. Las apps stateless son HTTP
directo (no usan guacd).

## Puertos y enrutamiento

| Servicio        | Bind            | Origen permitido          | Destino real        |
|-----------------|-----------------|---------------------------|---------------------|
| Nginx           | 0.0.0.0:80/443  | Internet (TLS)            | provision-api 8000 / Guacamole 8080 / app stateless |
| provision-api   | 0.0.0.0:8000    | Nginx (127.0.0.1), VMs (10.50.20.0/24), apps (10.50.10.0/23) | — |
| Guacamole Server| 127.0.0.1:8080  | Nginx (loopback)           | guacd 4822          |
| guacd           | 127.0.0.1:4822  | Guacamole (loopback)       | VM 10.50.20.x:3389  |
| mysql           | 127.0.0.1:3306  | Guacamole (loopback)       | —                   |
| app stateless   | 10.50.10.x:puerto | Nginx (10.50.10.1)       | —                   |

`docker ps` debe mostrar guacd **sin** columna `PORTS` publicada
(`network_mode: host` + bind 127.0.0.1). Las apps stateless no exponen
puertos en el host (`ss -tlnp | grep -E ':(3000|8888)'` vacío).

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
- **JWT con scope (FASE 6):** `dashboard` (lab null, multi-lab), `lab`
  (lab fijado), `admin` (sin lab). `/verify` devuelve `X-Lab-Scope` además
  de `X-Lab-Alumno`/`X-Lab-Name`. Nginx enruta a Guacamole solo si
  `scope=lab`.
- **Multi-lab (FASE 6):** `/lab/select` reemite JWT con lab seleccionado.
  Si el alumno tiene >1 matrícula, entra al dashboard (`scope=dashboard`) y
  escoge lab.
- **Admin (FASE 6):** cookie `admin_token` separada (Path=/admin, TTL 30min
  sin sliding). `/admin/verify` valida role admin. `ADMIN_JWT_SECRET`
  separado del navegador.
- El subdominio **no** identifica al alumno. Nginx SIEMPRE sobreescribe
  `Remote-User` con `"$lab_alumno-$lab_name"`; el cliente no puede
  inyectarlo.
- **`X-Internal` (FASE 6):** header secreto compartido Nginx→provision-api
  (defensa en profundidad, env len≥32, no loguear). provision-api lo exige
  en todas las llamadas internas. Middleware provision-api borra headers
  forjados del cliente (`X-Lab-Role`, `X-Admin-Email`, `X-Lab-Alumno`,
  `X-Lab-Name`, `X-App-Target`).
- Modelo A (sin password RDP): la conexión Guacamole se crea sin password
  (autologin configurado en la imagen base). El alumno no se loguea dos
  veces.

## Proxy de apps stateless (FASE 6)

Las apps stateless (contenedores LXD, perfil `stateless`) exponen HTTP en un
puerto interno. Nginx proxya vía path prefix `/apps/{app_id}/`:

1. `auth_request /verify/app` (READ-ONLY): valida JWT + pertenencia
   app↔alumno (app_lab↔enrollments) + IP ∈ 10.50.10.0/23. Devuelve
   `X-App-Target: <ip>:<puerto>`.
2. `auth_request_set $app_target $upstream_http_x_app_target`.
3. `proxy_pass http://$app_target` (con `resolver 10.50.10.1 valid=1s
   ipv6=off`).
4. `X-Forwarded-Prefix: /apps/{app_id}` para que la app genere URLs
   correctas.
5. WebSocket reusa `map $http_upgrade $connection_upgrade`.
6. `limit_req_zone $lab_alumno zone=appuser:10m rate=30r/s` (rate-limit por
   alumno para apps shared, anti noisy-neighbor).

**Regla de oro:** las apps NO pasan por guacd (son HTTP, no RDP/VNC). guacd
sigue intermedio SOLO para `/desktop/` (VMs).

**Cross-tenant:** `/verify/app` valida que `app_id ∈ apps_del_alumno`. Un
alumno no puede abrir `/apps/{app_de_otro}/`. `X-App-Target` lo genera
provision-api (upstream), no el cliente (anti-SSRF).

**iframe:** las apps se embeben en el dashboard con
`<iframe sandbox="allow-scripts allow-forms">` (sin `allow-same-origin` →
cross-origin efectiva, no lee cookies del padre).

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

## Aislamiento de apps stateless (iptables-apps.sh, FASE 6)

```bash
# DROP inter-app (lateral movement prevention)
iptables -A FORWARD -i lab-stateless -o lab-stateless -j DROP
# DROP app↔VM bidireccional (cross-tenant)
iptables -A FORWARD -i lab-stateless -o lab-persistent -j DROP
iptables -A FORWARD -i lab-persistent -o lab-stateless -j DROP
# ACCEPT host→app:3000-9999 (-I antes de DROP)
iptables -I FORWARD -s 10.50.10.1 -d 10.50.10.0/23 -p tcp --dport 3000:9999 -j ACCEPT
# ACCEPT app→host:8000 (heartbeat)
iptables -I FORWARD -s 10.50.10.0/23 -d 10.50.10.1 -p tcp --dport 8000 -j ACCEPT
# Defensa en profundidad: solo UID provision alcanza apps
iptables -I OUTPUT -m owner --uid-owner $(id -u provision) -d 10.50.10.0/23 -p tcp --dport 3000:9999 -j ACCEPT
```

Validación: `ss -tlnp | grep -E ':(3389|5900|3000|8888)'` vacío en host.

## Contrato con provision-api

- Tras `healthcheck_rdp` OK, provision-api escribe en la DB JDBC de
  Guacamole una conexión `<alumno>-<lab>` con `hostname=<vm-ip>`,
  `port=3389`, `username=alumno`, `ignore-cert=true`, `security=any`,
  **sin password** (Modelo A).
- IP dinámica: provision-api reescribe `hostname` tras cada healthcheck
  dentro de la transición a estado `lista`.
- En `destroy`: `DELETE` de la conexión y del usuario Guacamole asociado.
- `/verify` devuelve `200` + `X-Lab-Alumno`/`X-Lab-Name`/`X-Lab-Scope` si el
  JWT es válido y la matrícula sigue activa (SELECT enrollments); `401` en
  caso contrario (Nginx corta antes de llegar a Guacamole).
- `/verify/app` (FASE 6, READ-ONLY): valida JWT + pertenencia app↔alumno +
  IP ∈ 10.50.10.0/23. Devuelve `X-App-Target: <ip>:<puerto>`. **No escribe
  `last_seen`** (lo hace el heartbeat de la app, como las VMs).
- `/admin/verify` (FASE 6): valida cookie `admin_token` + role admin.
  Devuelve `X-Lab-Role: admin` + `X-Admin-Email`.

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
- **Redacción de query (FASE 6):** `lab_safe` usa `$loggable_request` (no
  `$request`) vía `map $request_uri $loggable_request { ~^/auth/verify
  "REDACTED"; ~^/admin/auth/verify "REDACTED"; default $request; }` para no
  loguear el token del magic link.
- **No loguear** `X-App-Target` (filtra IPs internas 10.50.10.x) ni
  `X-Internal` (secreto compartido).
- uvicorn (provision-api) con `--log-config` que redacte `Authorization`,
  `Cookie`, `X-Internal`, `X-Admin-Token` (filtro de logging).