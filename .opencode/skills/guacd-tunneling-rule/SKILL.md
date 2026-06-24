---
name: guacd-tunneling-rule
description: Regla de oro. Las conexiones RDP/VNC al navegador SIEMPRE pasan por guacd. No exponer 3389/5900 directamente. Config de Guacamole debe referenciar guacd, no los puertos crudos de las VMs.
---

# guacd SIEMPRE intermedio

Topologia obligatoria:
```
 alumno (navegador)
   └─ HTTPS -> Nginx reverse proxy
       └─ Guacamole Server (servlet/reset)
           └─ guacd (demonio proxy)
               └─ xrdp:3389 / VNC:5900 (dentro de la VM del alumno, en lab-persistent 10.50.20.0/24)
```

## Prohibido
- Nginx/Guacamole apuntando directamente a 3389/5900 de la VM saltando guacd.
- Abrir 3389/5900 hacia el navegador del alumno.
- Acceso RDP/VNC saltandose el web gateway.

## Config tipica de conexion (user-mapping/schema dinamico)
```xml
<config name="labX" protocol="rdp">
  <param name="hostname" value="10.50.20.<ip-vm>"/>   <!-- IP de la VM en lab-persistent -->
  <param name="port" value="3389"/>
  <param name="username" value="alumno"/>
  <param name="ignore-cert" value="true"/>
</config>
```
El cliente (navegador) habla con Guacamole Server; Guacamole Server habla con guacd; guacd habla con la VM. Nada expone 3389 hacia fuera de `lab-persistent`.

## Coordinacion con provision-api
Cada VM nueva queda registrada con su IP/puerto RDP; Guacamole debe poder consumir ese mapping (DB, archivo regenerado o API) — no hardcodear XML estatico.

## TLS / edge
- Nginx termina TLS en el edge (443).
- guacd <-> VM en red interna (sin NAT tocada por el alumno).
- `admin-net` 10.50.100.0/24 (sin NAT) es donde corren servicios de gestion, NO visible para el alumno.