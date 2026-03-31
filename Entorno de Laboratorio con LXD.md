**Entorno de Laboratorio con LXD**

**Objetivo:**  
Diseño de un sistema de laboratorios virtuales basado en Ubuntu con LXD (Linux Containers), donde los alumnos pueden acceder a máquinas virtuales y aplicaciones stateless a través del navegador, con provisión dinámica de instancias, persistencia de sesiones y opciones de guardado y reset. LXD es perfecto, porque maneja contenedores y VMs de forma ligera y escalable. La arquitectura debe ser escalable, fácil de implementar y ha de hacer uso de herramientas open-source para complementar LXD.

**Arquitectura:**

* **Server:** Servidor Ubuntu (última LTS [https://ubuntu.com/download/server](https://ubuntu.com/download/server)) con LXD ([https://canonical.com/lxd](https://canonical.com/lxd)) instalado (para contenedores/apps y VMs).  
* **Acceso web:** Apache Guacamole ([https://guacamole.apache.org/releases/](https://guacamole.apache.org/releases/)) como gateway para el acceso a las instancias en el navegador con VNC o RDP por ejemplo.  
* **Provisión dinámica:** Scripts en Python/Bash con un webhook o API simple para detectar conexiones y crear instancias on-demand.  
* **Inicialización automática:** Uso de cloud-init en las VMs para configurar el entorno del alumno en el primer arranque (usuario, paquetes, servicios, scripts de guardado/reset).  
* **Persistencia:** Snapshots nativos de LXD solo para VMs (no para apps/contenedores, que serán stateless).  
* **URLs por Alumno/Lab:** Nginx ([https://nginx.org/](https://nginx.org/) ) como reverse proxy para enrutar URLs personalizadas (ej: [lab1.alumno@dominio.com](mailto:lab1.alumno@dominio.com)).  
* **Autenticación:** AÚN POR VER  
* **Escalabilidad:** Solo una instancia por lab y alumno, con auto-destrucción tras inactividad, fecha o a conveniencia (por ejemplo: termina el curso escolar).

**Flujo básico:**

1. El alumno accede a una URL específica y Nginx autentica y redirige a Guacamole.  
2. Si no hay instancia activa, en el caso de VMs, cloud-init aplica la configuración inicial automáticamente (instalación de servicios, creación del usuario y entorno de trabajo).  
3. Si hay una instancia activa, se carga.  
4. Conexión vía Guacamole al puerto de la instancia (VNC o RDP).  
5. Dentro de la VM, un script permite "guardar estado" (snapshot) o "reset"  
   (borrar snapshot).  
6. Las apps no permiten guardar estado (stateless).

