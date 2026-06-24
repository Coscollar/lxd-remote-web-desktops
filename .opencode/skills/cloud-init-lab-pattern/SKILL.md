---
name: cloud-init-lab-pattern
description: Patron cloud-init por alumno para VMs persistentes del laboratorio (usuario, packages, write_files con scripts save/reset, runcmd, servicios systemd). Las apps stateless NO reciben esto.
---

# Patron cloud-init por alumno

Estructura recomendada para `cloud-init-template.yml` (y sus copias por alumno).

```yaml
#cloud-config

# Usuario del alumno
users:
  - name: alumno
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: false
    # NO poner pass en claro: preferir hashed passwd=$6$... o ssh_authorized_keys
    ssh_authorized_keys:
      - ssh-ed25519 AAAA...

hostname: alumno-labX
manage_etc_hosts: true

package_update: true
packages:
  - python3
  - git
  # Solo paquetes especificos del lab; MATE/xrdp/ssh YA estan en lab-vm-base

write_files:
  - path: /usr/local/bin/lab-save
    permissions: '0755'
    content: |
      #!/bin/bash
      # Pide al provision-api que haga snapshot
      curl -sX POST http://<provision-host>:<port>/save?lab=$(hostname)
  - path: /usr/local/bin/lab-reset
    permissions: '0755'
    content: |
      #!/bin/bash
      curl -sX POST http://<provision-host>:<port>/reset?lab=$(hostname)

runcmd:
  - systemctl enable xrdp
  - systemctl enable ssh

# Persistencia del servicios de guardado/reset se gestiona desde provision-api, no desde aqui
```

## Reglas del repo
- No reinstalar paquetes ya presentes en `lab-vm-base` (MATE, xrdp, ssh). Listar solo delta.
- No meter passwords en claro; usar `passwd:` con hash o `ssh_authorized_keys`.
- `users:` es idempotente (no duplica) pero `runcmd` no; mantenerlo idempotente.
- Coordinar con @provision-api y @policy-engine: los scripts `lab-save`/`lab-reset` llaman al servicio host, NO ejecutan `lxc` localmente (no viable dentro de la VM).
- Apps stateless (contenedores) no llevan cloud-init de guardado/reset.

Idempotencia: en re-lanzamientos desde base, cloud-init corre otra vez; que sea determinista.