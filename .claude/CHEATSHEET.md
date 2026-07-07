# Chuleta del ecosistema OpenCode (lab LXD)

Basado en `Entorno de Laboratorio con LXD.md`. Config en `opencode.json` + `.opencode/`.

## 2 agentes primarios (Tab para cambiar)
- **`lab-plan`** — planificación, read-only. Agente por defecto (`default_agent`).
- **`lab-build`** — implementación, edita/ejecuta.
- Ambos con `task` restringido a los subagentes del repo.

## 7 subagentes de dominio (invocables con `@`)
- `@infra-lxd` — pools, redes, perfiles, proyectos, imágenes.
- `@vm-base-builder` — imagen base VM `lab-vm-base` (MATE + xrdp).
- `@cloud-init-author` — `cloud-init-template.yml` y cloud-init por alumno (sin passwords en claro).
- `@provision-api` — Python + FastAPI + SQLite + systemd lanza/cura VMs, verifica JWT.
- `@web-gateway` — Apache Guacamole + guacd + Nginx + certbot (TLS Let's Encrypt).
- `@policy-engine` — snapshots nativos LXD (`base` + `k1..k5`) + auto-destrucción por inactividad/fecha.
- `@auth-designer` — magic link por email + JWT httpOnly (HS256).

## 5 críticones (read-only, no editan)
- `@critic-security` — secrets, puertos expuestos, fuga xrdp/VNC, `trust_password`.
- `@critic-idempotency` — scripts/cloud-init re-ejecutables sin duplicar.
- `@critic-lxd-conventions` — reglas de oro y convenciones de `AGENTS.md`.
- `@critic-reliability` — `sleep` frágil, `cloud-init status --wait`, errores silenciosos.
- `@critic-scalability` — una instancia por alumno/lab, retención de snapshots, cuellos a N alumnos.
- Sólo `bash` de lectura (`git diff`/`show`/`log`) + `webfetch`.

## 6 skills (cargadas on-demand vía `skill`)
- `lxd-cli-patterns` — patrones `lxc` idempotentes.
- `preseed-destructive` — `lxd init --preseed` es destructivo.
- `image-fingerprints` — fingerprints 22.04 fijados + regla de actualización dual.
- `cloud-init-lab-pattern` — patrón cloud-init por alumno.
- `guacd-tunneling-rule` — topología obligada alumno→Nginx→Guacamole→guacd→VM.
- `snapshot-destroy-policy` — esquema snapshots/restore/auto-destroy.

## Config y rules
- `opencode.json` — `default_agent: lab-plan`, permisos globales `ask`.
- `AGENTS.md` — sección "Ecosistema OpenCode" documenta todo esto.

## Uso típico
1. Con **`lab-plan`** (por defecto): *"plantea el paso 3 (cloud-init por alumno)"*.
   - Delega en `@cloud-init-author` / `@infra-lxd` y revisa con los críticos.
2. Cambia a **`lab-build`** (Tab): *"implementa el paso 3 según el plan"*.
3. En cualquier momento: `@critic-...` para revisar artefactos concretos.

## Roadmap (ver `DOIN.md`)
1. Infra LXD ✅ · 2. Imagen base VM ✅️ · 3. cloud-init por alumno · 4. Provisión on-demand · 5. Acceso web · 6. Políticas.
Antes de tocar un paso, consolida el anterior.