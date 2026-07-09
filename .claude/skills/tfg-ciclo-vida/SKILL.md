---
name: tfg-ciclo-vida
description: Mapeo del ciclo de vida completo de la aplicacion (analisis, diseño, desarrollo, pruebas, implantacion, operacion) a las evidencias reales de este repositorio, y a los capitulos de la memoria TFG. Usar para saber DE DONDE sacar el contenido de cada capitulo sin inventar nada.
---

# Ciclo de vida de la aplicacion → evidencias del repo → capitulos TFG

La memoria debe documentar el ciclo de vida COMPLETO. Este proyecto ya
contiene evidencia real de cada fase; los redactores deben extraerla de
estas fuentes (y NUNCA inventar datos que el repo no respalde):

| Fase del ciclo de vida | Evidencia en el repo | Capitulo TFG |
|---|---|---|
| Concepcion y requisitos | `README.md` (que es y para quien), `docs/USO.md` (funcionalidad visible), `AGENTS.md` (reglas de oro = requisitos no funcionales), `Entorno de Laboratorio con LXD.md` y `DOIN.md` (notas de diseño originales) | 1 Introduccion, 3 Analisis |
| Analisis de seguridad | `AGENTS.md`/`CLAUDE.md` (JWT scopes, X-Internal, sandbox iframe, guacd intermedio), `nginx/iptables-*.sh` (aislamiento), middleware anti-headers-forjados en `provision/main.py` | 3 Analisis (seguridad) |
| Marco legal | Emails de alumnos en SQLite → RGPD/LOPDGDD; licencias de dependencias (LXD, Guacamole Apache-2.0, FastAPI MIT, Nginx BSD); licencia propia del proyecto | 3 Analisis (marco legal) |
| Riesgos | `docs/DEPLOY.md` §"Deudas y limites conocidos"; preflight de `install-all.sh` (riesgos de entorno); pool guard (riesgo de saturacion) | 3 Analisis (riesgos) |
| Alternativas evaluadas | Decisiones documentadas: LXD vs Docker/KVM, Guacamole vs exposicion RDP, SQLite vs Postgres, magic link vs passwords, snapshots LXD vs backups; Anexos B/C de `docs/DEPLOY.md` (Opcion A vs C, HTTP-01 vs DNS-01) | 3 Analisis (soluciones) |
| Plan de trabajo real | `git log` (fases reales, fechas, iteraciones), FASES 0-6 del proyecto | 3 Analisis (plan de trabajo) |
| Diseño arquitectonico | `README.md` §Arquitectura (topologia + tabla de puertos), `CLAUDE.md` (componentes), `lxd-preseed.yaml` (infra) | 4 Diseño (arquitectura) |
| Diseño detallado | `provision/*.py` (modulos: main, auth, instances, policy, jobs, reap, apps, admin, web, db, config), `provision/db.py` (esquema BD), `cloud-init-template.yml` + Anexo A de DEPLOY (contrato de render), `nginx/lab.conf` (rutas) | 4 Diseño (detallado) |
| Tecnologia | Stack completo: Ubuntu Server, LXD/ZFS, KVM, FastAPI/uvicorn, SQLite WAL, Jinja2, Apache Guacamole + guacd, Docker, Nginx, certbot, systemd, iptables, xrdp, MATE | 4 Diseño (tecnologia) |
| Desarrollo | `git log` (decisiones e hitos), gotchas de `CLAUDE.md` (problemas reales encontrados: CRLF, preseed destructivo, grupo lxd exit 100, CSP...), patron de agentes/criticos usado para desarrollar | 5 Desarrollo |
| Implantacion | `install-all.sh` (instalador dirigido + preflight), `docs/DEPLOY.md`, `uninstall-all.sh`, `systemd/` | 6 Implantacion |
| Pruebas | Secciones "Validacion" de `docs/DEPLOY.md` (por fase + Anexos B.6/C.8), criterios de aceptacion (curl/lxc/ss), validacion estatica (bash -n, py_compile) | 7 Pruebas |
| Operacion y mantenimiento | Policy engine (snapshots, pool guard), reapers (auto-destruccion), reconciliacion dry-run al arranque, rotacion de secretos (USO.md), monitorizacion (`journalctl`, logs seguros) | 6-7 y Trabajos futuros |
| Evolucion | Deudas tecnicas documentadas en DEPLOY.md; cotas de escalabilidad del README | 9 Trabajos futuros |

## Datos duros disponibles (usar estos, no inventar)

- Extension de pools: persistent-pool 40GB (2-3 alumnos con k1..k5),
  stateless-pool 80GB (~60-80 contenedores).
- Cotas: SQLite ≤50 alumnos, /24 ≤250 VMs, /23 ~510 IPs, 4GB RAM/VM,
  2GB RAM/app (tabla completa en `README.md` §Cotas).
- Politicas: IDLE_MINUTES=60, APP_IDLE_MINUTES=30, SHARED_IDLE_HOURS=6,
  KEEP_SNAPSHOTS=5→3 (pool guard 60/75/90%), TTL JWT 1h/30min, magic link
  15min/5min.
- Snapshot base + k1..k5 FIFO con LXD como fuente de verdad.

## Lo que el repo NO da y hay que elaborar (declarandolo como estimacion)

- **Presupuesto**: horas-persona (derivar del git log + estimacion), coste
  hw (servidor con KVM), sw (todo FOSS → coste 0 en licencias), coste
  operativo (dominio, host).
- **Casos de uso / diagramas UML**: derivarlos de la funcionalidad real
  (actores: alumno, administrador, sistema/reaper).
- **ODS**: relacion razonada (p.ej. ODS 4 educacion de calidad, ODS 10
  reduccion de desigualdades — acceso a escritorios potentes desde
  cualquier dispositivo; ODS 12/13 — consolidacion de recursos frente a un
  PC por alumno). Justificar, no listar.
- **Validacion con usuarios**: si no la hay, decirlo honestamente y
  proponerla en Trabajos futuros.

## Regla de oro

Cada afirmacion tecnica de la memoria debe poder señalarse en un fichero
del repo o en una referencia bibliografica. El critico de veracidad
(`critic-tfg-veracidad`) rechazara lo que no.
