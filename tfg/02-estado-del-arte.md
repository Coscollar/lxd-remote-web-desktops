# Capítulo 2. Estado del arte

Este capítulo sitúa el trabajo en su contexto tecnológico: el panorama de escritorios remotos e infraestructura de escritorio virtual (2.1), las tecnologías de virtualización ligera subyacentes (2.2) y los antecedentes de laboratorios virtuales docentes (2.3); cierra con una crítica a las soluciones existentes (2.4) y la propuesta de este trabajo (2.5).

## 2.1 Escritorios remotos e infraestructura de escritorio virtual

Un *escritorio remoto* es un esquema de computación en el que la sesión gráfica de un usuario (aplicaciones, ficheros y configuración) se ejecuta en una máquina distinta de la que tiene delante: el equipo remoto genera la imagen de pantalla y la transmite por red, y el equipo local se limita a mostrarla y devolver las pulsaciones de teclado y ratón. Los dos protocolos dominantes son RDP (*Remote Desktop Protocol*), de Microsoft e implementado en Linux por servidores libres, y VNC (*Virtual Network Computing*), basado en el protocolo RFB (*Remote Framebuffer*) y concebido desde su origen como un cliente "ultraligero", sin estado en el terminal del usuario (Richardson et al., 1998).

Esta idea de terminal mínimo dio lugar en los años noventa al *thin client*: un dispositivo de bajo coste cuya única función es presentar sesiones ejecutadas en un servidor central. Con HTML5 y WebSocket, un navegador web estándar puede actuar hoy como cliente de escritorio remoto sin instalar software alguno. Son representativas de esta etapa las soluciones libres noVNC, un cliente VNC en JavaScript que se ejecuta íntegramente en el navegador[^1], y, sobre todo, Apache Guacamole, una pasarela "sin cliente" (*clientless*) bajo licencia Apache-2.0: un demonio intermedio (guacd) traduce RDP, VNC o SSH a un protocolo propio que el navegador consume vía HTML5, de modo que los puertos de escritorio remoto nunca se exponen al exterior[^2]. En Linux, xrdp aporta una implementación libre de servidor RDP que publica la sesión gráfica local[^3].

Sobre estos protocolos se asienta el modelo VDI (*Virtual Desktop Infrastructure*): los escritorios se ejecutan como máquinas virtuales en el centro de datos y se entregan bajo demanda a cualquier dispositivo. Entre las plataformas comerciales más extendidas están Citrix DaaS[^4] y Omnissa Horizon (antes VMware Horizon)[^5], propietarias y con licenciamiento por usuario, con *brokers* de conexión —el componente que asigna a cada usuario su escritorio y encamina la sesión—, gestión de imágenes y alta disponibilidad. Su evolución más reciente es el DaaS (*Desktop as a Service*), en el que el plano de control —y a menudo los escritorios— reside en la nube del proveedor y se factura por suscripción o uso; son ejemplos Azure Virtual Desktop[^6] y Amazon WorkSpaces[^7]. A medio camino, Kasm Workspaces ofrece *streaming* de escritorios y aplicaciones en contenedores hacia el navegador, con edición comunitaria gratuita para uso individual y de pruebas[^8]. En ciencia de datos, JupyterHub[^12] sirve entornos de *notebooks* por usuario (sección 2.3). La Tabla 2.1 compara estas soluciones según cuatro criterios relevantes para un laboratorio docente: licencia, aprovisionamiento, requisitos de cliente y coste.

| Solución | Modelo de licencia | Aprovisionamiento | Requisitos de cliente | Coste |
|---|---|---|---|---|
| Citrix DaaS | Propietaria | Plano de control gestionado por el proveedor | Cliente propio o navegador | Suscripción por usuario |
| Omnissa Horizon 8 | Propietaria | Autoalojado (consola propia) o nube | Cliente propio o navegador | Licencia comercial |
| Azure Virtual Desktop | Servicio propietario | Nativo de la nube Azure | Cliente propio o navegador | Pago por uso |
| Amazon WorkSpaces | Servicio propietario | Nativo de la nube AWS | Cliente propio o navegador | Pago por uso |
| Apache Guacamole | Libre (Apache-2.0) | No incluido (solo pasarela de acceso) | Navegador HTML5 | Sin coste de licencia |
| noVNC | Libre | No incluido (solo cliente VNC) | Navegador HTML5 | Sin coste de licencia |
| Kasm Workspaces | *Freemium* | Contenedores efímeros bajo demanda | Navegador HTML5 | Edición comunitaria limitada; licencias de pago |
| JupyterHub | Libre | Un servidor de *notebooks* por usuario | Navegador HTML5 | Sin coste de licencia |
| **Propuesta de este TFG** | Libre (composición de software libre) | Orquestador propio: VMs persistentes y contenedores efímeros LXD bajo demanda | Navegador HTML5 | Sin coste de licencia |

*Tabla 2.1. Comparativa de soluciones de escritorio remoto y entrega de entornos existentes. Elaboración propia a partir de la documentación de los fabricantes y proyectos (notas al pie 1-2, 4-8 y 12).*

## 2.2 Virtualización ligera: máquinas virtuales y contenedores

Las plataformas anteriores necesitan una capa de virtualización que ejecute los entornos de cada usuario. Una *máquina virtual* (VM) emula un computador completo —con su propio núcleo de sistema operativo y hardware virtualizado— gestionado por un *hipervisor*; en Linux, el hipervisor de referencia es KVM (*Kernel-based Virtual Machine*), integrado en el propio núcleo. Un *contenedor*, en cambio, es un entorno aislado que comparte el núcleo del anfitrión: no arranca un sistema operativo completo, por lo que su coste de memoria y arranque es muy inferior. Esta virtualización a nivel de sistema operativo fue caracterizada por Soltesz et al. (2007) como alternativa escalable y de alto rendimiento a los hipervisores, a costa de un aislamiento más débil; los estudios comparativos posteriores confirmaron que los contenedores igualan o superan a las VMs en casi toda carga de trabajo (Felter et al., 2015).

Dentro de los contenedores conviene distinguir dos familias. Los *contenedores de aplicación*, popularizados por Docker, empaquetan un único proceso con sus dependencias en imágenes inmutables y efímeras (Merkel, 2014); sobre ellos se construyó Kubernetes, el orquestador que gestiona flotas de contenedores en clústeres (Burns et al., 2016). Este modelo, orientado a microservicios sin estado, encaja mal con el problema de este trabajo: un escritorio gráfico persistente ligado a un alumno concreto no es un microservicio. Los *contenedores de sistema*, en cambio, ejecutan una distribución Linux completa con su propio arranque, comportándose ante el usuario como una máquina ligera.

LXD, ya presentado en el Capítulo 1, ocupa una posición híbrida: administra contenedores de sistema y máquinas virtuales KVM bajo una misma API y una misma línea de comandos, con perfiles de configuración, instantáneas de bajo coste sobre ZFS y descarga de imágenes oficiales mediante el protocolo *simplestreams*[^9] (existe además un derivado comunitario, Incus, surgido en 2023 y compatible en conceptos y comandos[^13]). Esta dualidad es precisamente la que aprovecha este proyecto: VMs para los escritorios persistentes de los alumnos (aislamiento fuerte, núcleo propio) y contenedores para las aplicaciones efímeras (densidad y arranque rápido), todo sobre un único host y una única herramienta. <!-- fuente: Entorno de Laboratorio con LXD.md:Objetivo y Arquitectura -->

Otras plataformas libres cubren un ámbito más amplio, a costa de mayor complejidad. Proxmox VE es una plataforma completa de virtualización (KVM y contenedores LXC, la tecnología de contenedores de sistema sobre la que se construye el propio LXD) con consola web de administración y soporte de clúster, concebida para la gestión de infraestructura por parte de administradores, no para entregar escritorios a usuarios finales[^10]. OpenStack es una plataforma IaaS (*Infrastructure as a Service*) de nube privada pensada para centros de datos multi-servidor, cuya complejidad operativa resulta desproporcionada para un laboratorio sobre un único host[^11]. Frente a ambas, LXD ofrece la funcionalidad necesaria para este caso de uso (instancias, perfiles, redes, instantáneas) con una API automatizable por completo desde scripts, lo que lo hace adecuado como base de un orquestador a medida; la comparativa sistemática de alternativas, con criterios declarados, se desarrolla en el Capítulo 3.

## 2.3 Laboratorios virtuales docentes

El acceso remoto a entornos de prácticas cuenta con literatura consolidada en educación en ingeniería. La revisión clásica de Ma y Nickerson (2006) distingue tres familias de laboratorio —presencial, simulado y remoto— y constata que los remotos, aun sacrificando la manipulación física, favorecen la comprensión conceptual y flexibilizan el acceso, un debate que la generalización del navegador como cliente universal ha reavivado.

En escritorios virtuales universitarios, Chrobak (2014) documenta una infraestructura VDI comercial (VMware Horizon View) en los laboratorios de una universidad polaca, justificada por el ahorro en mantenimiento de puestos físicos pero apoyada en licenciamiento propietario e inversión centralizada considerable. Más próximo a este trabajo, Hassan (2022) describe un laboratorio en línea para un curso masivo de ciberseguridad con una combinación muy cercana a la de este trabajo (Guacamole, LXD y Docker), que valida la viabilidad de esta pila libre en un contexto docente real. Por último, JupyterHub, presentado en 2.1, cuenta con experiencias de aula que destacan la eliminación de toda instalación local (Al-Gahmi et al., 2022), aunque su alcance se limita al entorno Jupyter.

## 2.4 Crítica al estado del arte

Del análisis anterior se desprenden tres lagunas que este trabajo pretende cubrir.

**Coste y sobredimensionamiento del VDI comercial.** Las plataformas VDI/DaaS están concebidas para parques corporativos de gran escala: incorporan *brokers* redundantes, alta disponibilidad multi-sede y consolas de gestión empresarial que un laboratorio docente de decenas de alumnos no necesita, y las facturan mediante suscripción por usuario. En el caso de los servicios de nube (Azure Virtual Desktop, Amazon WorkSpaces), al coste recurrente se añade la dependencia estructural del proveedor: los datos y los escritorios residen fuera de la institución y el gasto crece con cada hora de uso.

**Componentes libres que solo resuelven una parte.** Las piezas de código abierto disponibles son fragmentos de la solución, no la solución: Apache Guacamole resuelve el túnel de acceso, pero no crea las máquinas de los alumnos ni gestiona su identidad o su destrucción por inactividad; noVNC es únicamente un cliente; xrdp, únicamente el servidor dentro de la máquina. El esfuerzo de integración —aprovisionamiento, autenticación, persistencia, ciclo de vida, aislamiento de red— recae íntegramente en cada institución; las herramientas genéricas de automatización alivian el despliegue inicial, pero no aportan la lógica de negocio del laboratorio, que sigue habiendo que construir. Kasm Workspaces empaqueta parte de esa integración, pero su modelo se centra en sesiones de contenedor efímeras y su edición gratuita se orienta a uso individual y de pruebas.

**Antecedentes docentes parciales.** Los trabajos académicos revisados confirman el interés del problema, pero no lo resuelven por completo: la implantación de Chrobak (2014) depende de una pila propietaria; JupyterHub solo entrega un tipo de aplicación; y la experiencia de Hassan (2022), el antecedente más próximo, se describe como una solución ligada a un curso concreto de ciberseguridad, sin plantear una plataforma generalista con escritorios persistentes por alumno, catálogo de aplicaciones y despliegue reproducible. No se ha localizado una solución integral, autoalojada y sin coste de licencias que combine escritorios persistentes por alumno y aplicaciones efímeras sobre un único servidor, con el ciclo de vida completo automatizado.

## 2.5 Propuesta

Este trabajo se sitúa en esa laguna: integra LXD, Apache Guacamole y un orquestador propio desarrollado en FastAPI —un *framework* web para Python[^14]— sobre un único servidor Ubuntu, de modo que cada alumno dispone de un escritorio Linux persistente (una VM con MATE y xrdp, tunelizada por guacd hasta su navegador) y de aplicaciones web efímeras en contenedores, sin instalar nada en su equipo. <!-- fuente: README.md:Qué es --> Todos los componentes son software libre, por lo que el coste de licencias es nulo, y la plataforma reside íntegramente en la institución, sin dependencia de nube ni facturación por uso.

Frente a los antecedentes revisados, la propuesta aporta tres diferenciadores concretos. Primero, una autenticación sin contraseñas mediante *magic link* (véase la sección 1.2), de forma que el sistema no almacena ni gestiona contraseñas de estudiantes. <!-- fuente: README.md:Identidad y seguridad --> Segundo, la persistencia en autoservicio: el propio alumno guarda y restaura instantáneas de su escritorio, con una política automática de retención que protege el almacenamiento del servidor. <!-- fuente: README.md:Ciclo de vida de las instancias --> Y tercero, la reproducibilidad de la implantación: un instalador único y dirigido despliega la plataforma completa sobre un servidor limpio con un solo comando, lo que la hace transferible a otras asignaturas o centros. <!-- fuente: README.md:Qué es; install-all.sh -->

La propuesta no compite con el VDI corporativo en escala ni en alta disponibilidad: renuncia deliberadamente a la redundancia multi-servidor para maximizar la sencillez y minimizar el coste a escala de asignatura. El Capítulo 3 analiza los requisitos, riesgos y alternativas de diseño que concretan esta propuesta.

[^1]: noVNC, cliente VNC para navegador. https://novnc.com/ [consulta: 15 de julio de 2026].
[^2]: Apache Guacamole, pasarela de escritorio remoto sin cliente. https://guacamole.apache.org/ [consulta: 15 de julio de 2026].
[^3]: xrdp, servidor RDP libre para Linux. https://github.com/neutrinolabs/xrdp [consulta: 15 de julio de 2026].
[^4]: Citrix DaaS. https://www.citrix.com/platform/citrix-daas/ [consulta: 15 de julio de 2026].
[^5]: Omnissa Horizon 8. https://www.omnissa.com/products/horizon-8/ [consulta: 15 de julio de 2026].
[^6]: Microsoft Azure Virtual Desktop. https://azure.microsoft.com/es-es/products/virtual-desktop/ [consulta: 15 de julio de 2026].
[^7]: Amazon WorkSpaces. https://aws.amazon.com/workspaces/ [consulta: 15 de julio de 2026].
[^8]: Kasm Workspaces. https://kasm.com/ [consulta: 15 de julio de 2026].
[^9]: Canonical LXD. https://canonical.com/lxd [consulta: 15 de julio de 2026].
[^10]: Proxmox Virtual Environment. https://www.proxmox.com/en/proxmox-virtual-environment [consulta: 15 de julio de 2026].
[^11]: OpenStack. https://www.openstack.org/ [consulta: 15 de julio de 2026].
[^12]: JupyterHub. https://jupyter.org/hub [consulta: 15 de julio de 2026].
[^13]: Incus. https://linuxcontainers.org/incus/ [consulta: 15 de julio de 2026].
[^14]: FastAPI. https://fastapi.tiangolo.com/ [consulta: 15 de julio de 2026].

<!-- Las referencias bibliográficas de este capítulo están consolidadas en tfg/10-referencias.md -->

