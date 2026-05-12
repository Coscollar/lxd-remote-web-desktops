# cloud-init-template.yml

## Descripción

Archivo de plantilla de configuración en formato YAML que utiliza **cloud-init** para inicializar automáticamente las máquinas virtuales (VMs) de laboratorio en su primer arranque.

## Qué es cloud-init

Cloud-init es una herramienta estándar de la industria que permite la configuración automatizada de sistemas Linux durante el arranque. Soporta múltiples formatos de configuración:
- **cloud-config** (YAML): Formato principal declarativo
- **shell scripts**: Scripts de shell para tareas imperativas
- **part-handler**: Gestión de particiones

## Propósito en el Proyecto

En este proyecto, cloud-init se utiliza para:
- Crear usuarios personalizados para cada alumn@
- Instalar paquetes adicionales necesarios
- Configurar servicios del sistema
- Desplegar scripts de guardado/reset de estado

## Formato del Archivo

### Secciones Principales

```yaml
#cloud-config
users:
  - name: <usuario>
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash

packages:
  - <paquete1>
  - <paquete2>

runcmd:
  - <comando1>
  - <comando2>

write_files:
  - path: /ruta/archivo
    content: |
      contenido del archivo
```

### Descripción de Secciones

| Sección | Descripción |
|---------|-------------|
| `users` | Define usuarios y sus propiedades (shell, sudo, claves SSH) |
| `packages` | Lista de paquetes a instalar via apt |
| `runcmd` | Comandos a ejecutar tras el primer arranque |
| `write_files` | Archivos a crear en el sistema con su contenido |

## Estado Actual

El archivo `cloud-init-template.yml` ha sido **implementado** con la siguiente configuración:

### Configuración Implementada

| Sección | Contenido |
|---------|-----------|
| `users` | Usuario dinámico por alumn@ con nombre definido por variable `{{username}}`, grupo users, sudo sin contraseña, shell bash |
| `packages` | vim, curl, git, firefox |
| `runcmd` | Habilitar servicios SSH y xrdp |
| `write_files` | Script `guardar-estado.sh` para crear snapshots de la VM |

### Sistema de Variables

La plantilla utiliza el sistema de variables `{{variable}}` que se substituye dinámicamente al crear cada VM:
- `{{username}}`: Nombre del alumn@ (se reemplaza por el nombre de usuario correspondiente)

### Contenido del Archivo

```yaml
#cloud-config
users:
  - name: {{username}}
    primary_group: users
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash

packages:
  - vim
  - curl
  - git
  - firefox

runcmd:
  - systemctl enable ssh
  - systemctl enable xrdp

write_files:
  - path: /usr/local/bin/guardar-estado.sh
    permissions: "0755"
    owner: root:root
    content: |
      #!/bin/bash
      lxc snapshot $(hostname) {{username}}-estado
```

## Referencia

- [Documentación oficial de cloud-init](https://cloudinit.readthedocs.io/)