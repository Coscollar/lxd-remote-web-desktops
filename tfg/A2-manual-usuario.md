# Anexo A2. Manual de usuario

Este anexo describe el uso de la plataforma desde los dos perfiles que contempla: el alumno y el administrador. Es una redacción de síntesis sobre la guía de uso operativa del repositorio (`docs/USO.md`), a la que se remite para los detalles de línea de comandos. <!-- fuente: docs/USO.md -->

## A2.1 Manual del alumno

### Acceso al portal

1. Abrir `https://lab.<dominio>` en cualquier navegador moderno. No se requiere instalar software alguno.
2. Introducir el correo electrónico con el que se está matriculado en el laboratorio.
3. El sistema envía un *magic link* al buzón indicado, válido durante 15 minutos y de un solo uso. Al abrirlo se inicia la sesión (cookie con caducidad de 1 hora). Si el mensaje no aparece, conviene revisar la carpeta de correo no deseado. <!-- fuente: docs/USO.md:Para el alumno -->
4. Si el alumno está matriculado en varios laboratorios, se muestra un panel (*dashboard*) con los laboratorios disponibles y las aplicaciones de cada uno; con un único laboratorio, el acceso es directo al escritorio.

### Trabajo con el escritorio

Al pulsar "Abrir escritorio" se lanza la máquina virtual personal del alumno si no existía y se carga el escritorio MATE en la propia pestaña del navegador. El primer arranque tarda entre uno y tres minutos, tiempo que emplea la inicialización automática de la máquina; los arranques posteriores son inmediatos. <!-- fuente: docs/USO.md:Para el alumno -->

Dentro de la máquina virtual, el alumno dispone de tres órdenes de autoservicio:

| Orden | Efecto |
|---|---|
| `lab-save` | Crea una instantánea (`k1`..`k5`) del estado actual; al superar cinco, se elimina automáticamente la más antigua (rotación FIFO). |
| `lab-reset` | Restaura la máquina a su estado inicial `base`, perdiendo los cambios no guardados. Pide confirmación (`--yes` para omitirla). |
| `lab-heartbeat` | Señal de vida enviada automáticamente cada cinco minutos por el sistema; no debe ejecutarse manualmente. |

<!-- fuente: docs/USO.md:Scripts de laboratorio -->

El fichero `/etc/lab/identity` contiene el testigo de servicio personal de la máquina; es rotatorio y no debe compartirse ni eliminarse.

### Aplicaciones efímeras

Cada laboratorio puede ofrecer aplicaciones web adicionales (por ejemplo, un cuaderno Jupyter) que se abren desde el panel con un clic. Existen dos modalidades: **compartidas**, una única instancia para todo el laboratorio, útil para demos y material de consulta; y **por alumno**, una instancia propia que se destruye a los 30 minutos desde su último lanzamiento o reinicio (véase la precisión técnica en el Capítulo 4) y que el alumno puede reiniciar (destrucción y recreación) desde el propio panel. El reinicio de una aplicación compartida queda reservado al administrador, puesto que afecta a todos los alumnos. <!-- fuente: docs/USO.md:Apps stateless -->

### Caducidades que el alumno debe conocer

- La sesión del navegador caduca a la hora; basta solicitar un nuevo enlace.
- Una máquina virtual sin actividad durante 60 minutos se destruye automáticamente; el trabajo guardado con `lab-save` y el estado del disco persisten según la política del laboratorio, y volver a entrar la relanza.
- Si el administrador ha fijado una fecha límite del laboratorio o del curso, la guía de uso prevé la destrucción de las instancias al superarse esa fecha (su aplicación automática está pendiente; véase el Capítulo 9). <!-- fuente: docs/USO.md:Sesión y caducidad; provision/reap.py -->

## A2.2 Manual del administrador

### Acceso a la consola

La consola se sirve en `https://lab.<dominio>/admin/login`. El acceso exige que el correo del administrador figure en la tabla `admins`; el enlace de acceso admin caduca a los 5 minutos y la sesión resultante a los 30, sin renovación automática. La guía de uso contempla un segundo factor TOTP opcional, cuya verificación no está aún implementada en el código (véase el Capítulo 9). Cada canje de enlace genera un correo de notificación, lo que permite detectar accesos no reconocidos. <!-- fuente: docs/USO.md:Consola admin -->

### Operaciones disponibles

La consola se organiza en pestañas:

- **Instancias**: listado paginado de todas las máquinas virtuales y aplicaciones vivas, con la posibilidad de destruir cualquiera de ellas.
- **Labs**: creación y edición de laboratorios (imagen base, fecha límite) y activación/desactivación; la desactivación es reversible y no borra datos.
- **Matrículas**: alta, baja y realta de alumnos por laboratorio, con filtro y paginación, y lanzamiento anticipado de la máquina de un alumno (encola el mismo trabajo que usaría el propio alumno).
- **Apps**: alta y edición de aplicaciones del catálogo (imagen, puerto, modalidad compartida o por alumno, límites de CPU y memoria, laboratorios asociados), desactivación con destrucción diferida de las instancias vivas, y arranque/parada/reinicio de la instancia compartida. <!-- fuente: docs/USO.md:Consola admin -->

Por diseño, **el alta de nuevos administradores no existe ni en la consola ni en la API**: al ser el privilegio máximo, se gestiona exclusivamente por SQL sobre la base de datos, desde la sesión de sistema del host. El primer administrador lo siembra el instalador. <!-- fuente: docs/USO.md:Alta de admins -->

### Operación por línea de comandos

Toda la funcionalidad de la consola existe también como API autenticada (`X-Admin-Token`) y consultas SQL directas, pensadas para automatización o como respaldo si el portal no está disponible: gestión de labs y matrículas, listados de instancias, destrucción manual, disparo manual de los procesos de limpieza (*reapers*), inspección de instantáneas, reconstrucción de imágenes y rotación de secretos JWT sin invalidar sesiones (variable `*_PREV`). Los comandos concretos se recogen en `docs/USO.md` del repositorio. <!-- fuente: docs/USO.md:Operación avanzada -->
