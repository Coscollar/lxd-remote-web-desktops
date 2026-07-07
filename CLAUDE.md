# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Repo language is Spanish (`AGENTS.md`, docs, code comments, commit messages). Respond and commit in Spanish unless told otherwise.

## What this is

Browser-based remote desktops/apps for students, built on LXD. A single Ubuntu Server host runs LXD VMs (persistent, per-student MATE desktops via xrdp) and LXD containers (stateless apps like Jupyter), fronted by a FastAPI orchestrator (`provision/`), Apache Guacamole (RDP-in-browser), and Nginx (TLS + reverse proxy + auth gate).

No lint/typecheck/test suite exists — this is infra (bash + YAML + Python) validated by running `lxc` commands against a real LXD host, not by a CI pipeline.

## Golden rules (non-negotiable, from `AGENTS.md`)

1. **Profiles**: every instance uses a restricted profile (`stateless`, `persistent`, or `admin`) — never LXD's `default`.
2. **Images**: prefer `simplestreams` from the `ubuntu-releases` remote. Local images are copied with `lxc image copy ... local:` under stable aliases.
3. **Automation**: every reproducible change must be executable via `lxc` CLI / bash scripts. No manual console steps.
4. **guacd tunneling**: browser RDP/VNC connections ALWAYS go through `guacd`. Never expose xrdp/VNC ports directly. Stateless (HTTP) apps do **not** use guacd — this rule is RDP/VNC only.
5. **Stateless apps**: LXD containers on profile `stateless`, network `lab-stateless`, pool `stateless-pool`, prebuilt image `local:app-<id>`. Launched via `instances.launch_container()` (no `--vm`), always through the job queue (never synchronous). Proxied by Nginx under `/apps/{app_id}/`.
6. **Naming**: student/lab names must match `^(?!app-)[a-z0-9][a-z0-9-]{1,30}$` (the `app-` prefix is reserved). Apps use `^app-[a-z0-9][a-z0-9-]{1,30}$`. If `app-<id>-<alumno>` exceeds 30 chars, substitute `<alumno>` with `sha8(alumno)`.
7. **Triple fingerprint rule**: changing the Ubuntu release requires updating fingerprints in **all three**: `server-setup-lxd.sh`, `IMAGE_SOURCE` in `build-lab-vm-base-mate.sh`, and `IMAGE_SOURCE` in `build-apps/_common.sh`.
8. **Auth**: JWT with `scope` claim (`dashboard`|`lab`|`admin`). `ADMIN_JWT_SECRET` is separate from the student browser secret. Cookie `admin_token` is `Path=/admin`, TTL 30min, no sliding renewal. `X-Internal` header shared only between Nginx→provision-api (defense in depth, `len>=32`, never logged). Middleware in `provision/main.py` strips client-forged headers (`X-Lab-Role`, `X-Admin-Email`, `X-Lab-Alumno`, `X-Lab-Name`, `X-App-Target`).
9. **iframe apps**: `sandbox="allow-scripts allow-forms"` **without** `allow-same-origin` — apps are effectively cross-origin and cannot read the parent's cookies.

## Architecture

```
Browser ──HTTPS──▶ Nginx (:443)
                     ├─ / , /dashboard , /lab/* , /api/* , /admin/* , /static/*
                     │   auth_request /verify (or /admin/verify) → provision-api (:8000)
                     ├─ /desktop/{lab}/...
                     │   auth_request /verify (requires X-Lab-Scope=lab)
                     │   → Guacamole Server (:8080) → guacd (:4822) → student VM (xrdp :3389, never exposed)
                     └─ /apps/{app_id}/...
                         auth_request /verify/app (READ-ONLY) → stateless app container (10.50.10.x:port, direct HTTP, no guacd)
```

- **`provision/`** — the FastAPI orchestrator, the core of the system:
  - `main.py` — app + lifespan (dry-run BD↔LXD reconciliation on boot, never blind-deletes), hardening middleware (strips forged headers, blocks VM/app-network peers from browser-only routes), `/lab/*`, `/heartbeat`, `/save`, `/reset`, `/restore`, `/admin/*`, `/metrics`.
  - `auth.py` — magic-link + JWT (HS256) for students, separate JWT/cookie for admin, VM/app service tokens (`scope=save|reset|heartbeat`, IP-bound).
  - `instances.py` — `lxc` wrapper via `asyncio.create_subprocess_exec` (never blocking `subprocess.run`, never raw LXD REST/`trust_password`). `launch()` (VMs, `--vm` hardcoded) is intentionally separate from `launch_container()` (stateless apps, no `--vm`).
  - `policy.py` — snapshot lifecycle (`base` + `k1..k5` FIFO, source of truth = LXD not a DB counter) and pool-usage guard (`>60%` reduce retention, `>75%` purge oldest, `>90%` reject).
  - `jobs.py` — persistent job queue (table `jobs` + worker in `lifespan`), because `BackgroundTasks` don't survive a restart. All launches (VM and app) go through this, never synchronously in the request handler.
  - `reap.py` — standalone script invoked by a systemd timer (not an HTTP endpoint on the single worker) that destroys idle/expired instances and apps. Anti-TOCTOU: re-checks state inside `BEGIN IMMEDIATE` before deleting.
  - `apps.py` — stateless app catalog + launch/reset/status endpoints (FASE 6).
  - `web.py` — Jinja2 HTML routes for students (login, dashboard); `web/templates/`, `web/static/`.
  - `db.py` — SQLite schema (WAL, `busy_timeout=5000`); `config.py` — `Settings.from_env()`, fails fast if required secrets are missing or `<32` bytes.
- **`cloud-init-template.yml`** — Jinja2 template (not native `${}` cloud-init syntax) rendered per-student by `provision-api` and piped via **stdin** to `lxc launch -c user.user-data=-` (never as a shell argument — avoids flag injection). Full contract in `docs/cloud-init-render.md`. Never commit a rendered YAML (it contains the live VM service token) — it's render-in-memory only.
- **`build-lab-vm-base-mate.sh`** — builds the `lab-vm-base` VM image (MATE desktop + xrdp, autologin, no known RDP password — "Modelo A"). Aborts if the image already exists unless `--force`.
- **`build-apps/`** — mirrors the VM builder for stateless app container images. `_common.sh` centralizes `IMAGE_SOURCE` + helpers; one `build-app-<name>.sh` per app.
- **`nginx/`** — `lab.conf` (multi-path reverse proxy + `auth_request` gate), `iptables-lab.sh` (inter-VM isolation), `iptables-apps.sh` (inter-app + app↔VM isolation), `install.sh`.
- **`guacamole/`** — `docker-compose.yml` (guacd + guacamole + mysql, all `network_mode: host`, bound to 127.0.0.1), `install.sh`.
- **`systemd/`** — `provision.service`, `provision-reap.{service,timer}` (VMs), `provision-reap-apps.{service,timer}` (apps).
- **`install-all.sh` / `uninstall-all.sh`** — single entrypoints for full install/uninstall (including the FASE 6 apps portal).
- **`.claude/agents/`, `.claude/skills/`** — domain subagents (`infra-lxd`, `vm-base-builder`, `cloud-init-author`, `provision-api`, `web-gateway`, `policy-engine`, `auth-designer`) and critics (`critic-security`, `critic-idempotency`, `critic-lxd-conventions`, `critic-reliability`, `critic-scalability`), plus skills documenting the fingerprint rule, cloud-init pattern, guacd tunneling rule, snapshot/destroy policy, and idempotent `lxc` CLI patterns. Critics are read-only reviewers.
- **`comandos.txt`, `DOIN.md`, `Entorno de Laboratorio con LXD.md`, `PLAN.md`** — design notes, not executable. If they conflict with the actual scripts, trust the scripts.

## Development commands (Linux host)

```bash
# Scripts are edited from Windows (CRLF); convert before running:
sudo apt update && sudo apt install dos2unix -y
for f in *.sh provision/*.sh guacamole/*.sh nginx/*.sh build-apps/*.sh; do
  dos2unix "$f" 2>/dev/null || true
done

# One-shot full install (all FASES 0-6, generates secrets automatically):
sudo bash install-all.sh --domain=lab.example.com --email=admin@example.com

# Uninstall:
sudo bash uninstall-all.sh --domain=lab.example.com           # asks to confirm
sudo bash uninstall-all.sh --purge-lxd --domain=lab.example.com  # + pools/networks/profiles

# Step-by-step (see docs/DEPLOY.md for detail per phase):
sudo bash server-setup-lxd.sh          # FASE 0: LXD infra + base VM image
sudo bash provision/install.sh          # FASE 1-3: provision-api service
cd guacamole && sudo bash install.sh && cd ..
sudo bash nginx/install.sh lab.<domain> admin@<domain>
sudo bash nginx/iptables-lab.sh
for f in build-apps/build-app-*.sh; do sudo bash "$f"; done
sudo bash nginx/iptables-apps.sh

# Validation after any infra change:
lxc storage list && lxc network list && lxc profile list && lxc project list && lxc image list local
lxc image list local --project labs | grep app-
sudo ss -tlnp | grep -E ':(3389|5900|3000|8888)'   # must be empty — nothing exposed directly
```

There is no `lxd init --preseed` re-run without an explicit `--force-preseed`-equivalent guard — reloading the preseed is destructive and wipes prior daemon config (`lxd-preseed.yaml`, see `preseed-destructive` skill).

## Known gotchas

- `core.trust_password` in the preseed is dev/lab only — rotate before any production use.
- `build-lab-vm-base-mate.sh` uses `timeout`-guarded waits, not fragile `sleep`; verify with `lxc exec vm-base -- cloud-init status` before publishing if the host is slow.
- Images do NOT auto-update (`images.auto_update_interval: "0"`) — rotation is manual.
- `stateless-pool` starts at 20GB in the preseed; `install-all.sh` expands it to 80GB via `lxc storage set size=80GB` (non-destructive — never `--force-preseed`, which would wipe `persistent-pool`).
- `lab-stateless` starts at /24 in the preseed; `install-all.sh` expands it to /23 (non-destructive).
- `uvicorn` must bind `--host 0.0.0.0` (not `127.0.0.1`) so VMs/apps can reach `provision-api`; this is paired with an iptables allowlist restricting who can reach port 8000.
- `instances.launch()` hardcodes `--vm` — apps must use `launch_container()`, never repurpose `launch()`.
- `/verify/app` is READ-ONLY (never writes `last_seen`) to avoid saturating the single SQLite writer; the app's own heartbeat updates `last_seen` instead.
- Auto-heal of shared `always_on=1` apps is asynchronous (queued after `yield` in lifespan), never synchronous at startup — it would block boot.
- `persistent-pool` at 40GB realistically supports only ~2-3 students with `k1..k5` snapshot retention; the pool guard lowers retention to `k1..k3` above 60% usage.
- Reconciliation on boot is always dry-run — it marks orphans, it never blind-deletes an instance found in LXD-vs-DB mismatch.
