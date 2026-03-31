## **Orden resumen**

 1️⃣ Infra LXD → ✅  
 2️⃣ Imagen base VM →   
 3️⃣ Cloud-init alumno  
 4️⃣ Provisión on-demand  
 5️⃣ Acceso web  
 6️⃣ Políticas (snapshot, destroy)

Herramientas:

1. UBUNTU Server [https://ubuntu.com/download/server/thank-you?version=24.04.3\&architecture=amd64\&lts=true](https://ubuntu.com/download/server/thank-you?version=24.04.3&architecture=amd64&lts=true)   
   2. LXD [https://documentation.ubuntu.com/lxd/stable-5.21/tutorial/first\_steps/](https://documentation.ubuntu.com/lxd/stable-5.21/tutorial/first_steps/)   
   3. Apache Guacamole   
   4. Nginx

**INSTALACIÓN Y CONFIGURACIÓN DE LXD**  
Instalar LXD:   
sudo snap install LXD  
Ver que el user de la maquina es parte del grupo de LXD:   
getent group lxd | grep "$USER"  
Si el comando no saca nada ejecutar:  
	sudo usermod \-aG lxd "$USER"  
newgrp lxd  
Añadir el remote oficial de ubuntu para mas imagenes  
lxc remote add ubuntu-releases https://cloud-images.ubuntu.com/releases \--protocol simplestreams  
Inicializar LXD a partir de un archivo de configuración  
	lxd init \--preseed \< lxd-preseed.yaml  
Cada vez que se carga un archivo de configuración se machaca la configuración anterior

**Ejemplo de configuración avanzada:**

| `# Configuración global del demonio LXD config:   core.https_address: "127.0.0.1:50000"   core.trust_password: "123456"   images.auto_update_interval: "0" # Redes virtuales networks:   # Red de laboratorio para contenedores stateless   - name: lab-stateless     type: bridge     config:       ipv4.address: 10.50.10.1/24       ipv4.nat: "true"       ipv6.address: none       dns.domain: "lab.internal"       dns.mode: "managed"   # Red de VMs persistentes   - name: lab-persistent     type: bridge     config:       ipv4.address: 10.50.20.1/24       ipv4.nat: "true"       ipv6.address: none       dns.domain: "vm.lab.internal"       dns.mode: "managed"   # Red de administración   - name: admin-net     type: bridge     config:       ipv4.address: 10.50.100.1/24       ipv4.nat: "false"       ipv6.address: none # Pools de almacenamiento storage_pools:   - name: stateless-pool     driver: zfs     config:       size: 20GB   - name: persistent-pool     driver: zfs     config:       size: 40GB # Perfiles de laboratorio profiles:   - name: stateless     description: Contenedores sin persistencia     config:       limits.cpu: "2"       limits.memory: 2GB     devices:       root:         type: disk         pool: stateless-pool         path: /       eth0:         type: nic         network: lab-stateless         name: eth0   - name: persistent     description: VMs persistentes para alumnos     config:       limits.cpu: "4"       limits.memory: 4GB     devices:       root:         type: disk         pool: persistent-pool         path: /       eth0:         type: nic         network: lab-persistent         name: eth0   - name: admin     description: Entorno de administración     config:       limits.cpu: "2"       limits.memory: 2GB     devices:       root:         type: disk         pool: persistent-pool         path: /       eth0:         type: nic         network: admin-net         name: eth0 # Proyectos projects:   - name: test     description: Proyecto por defecto para pruebas     config: {}   - name: labs     description: Entorno de laboratorio de alumnos     config:       features.images: "true"       features.networks: "true"       features.profiles: "true"` |
| :---- |

Importante:

- Como no hay discos extra, la forma más segura es usar archivos de loop para los pools ZFS es simular discos físicos, sin tocar NVMe.   
- No se disponen de imagenes porque no se pueden pre-cargar directamente en el archivo de configuracion .yaml

Pools ZFS:

- Crea el pool ZFS para contenedores stateless

sudo lxc storage create stateless-pool zfs size=20GB

- Crea el pool ZFS para VMs persistentes

sudo lxc storage create persistent-pool zfs size=40GB

Imágenes (puede disponerse de otras):

- Obtener lista de imagenes

	lxc image list ubuntu-releases: | grep 22.04 | grep x86\_64

- Nos quedamos con la ultima de container y virtual-machine  
  lxc image copy ubuntu-releases:cf181d732f32 local: \--alias ubuntu-22.04-vm  
  lxc image copy ubuntu-releases:a6d2f7222476 local: \--alias ubuntu-22.04-container

Los valores asignados a cada uno de los campos se definirán más adelante para el cluster del laboratorio.

**Validaciones tras la configuración:**

| `lxc storage list +-----------------+--------+----------------------------------------------------+-------------+---------+---------+ |      NAME       | DRIVER |                       SOURCE                       | DESCRIPTION | USED BY |  STATE  | +-----------------+--------+----------------------------------------------------+-------------+---------+---------+ | default         | dir    | /var/snap/lxd/common/lxd/storage-pools/default     |             | 1       | CREATED | +-----------------+--------+----------------------------------------------------+-------------+---------+---------+ | persistent-pool | zfs    | /var/snap/lxd/common/lxd/disks/persistent-pool.img |             | 2       | CREATED | +-----------------+--------+----------------------------------------------------+-------------+---------+---------+ | stateless-pool  | zfs    | /var/snap/lxd/common/lxd/disks/stateless-pool.img  |             | 1       | CREATED | +-----------------+--------+----------------------------------------------------+-------------+---------+---------+` |
| :---- |
| `lxc network list +----------------+----------+---------+-----------------+---------------------------+-------------+---------+---------+ |      NAME      |   TYPE   | MANAGED |      IPV4       |           IPV6            | DESCRIPTION | USED BY |  STATE  | +----------------+----------+---------+-----------------+---------------------------+-------------+---------+---------+ | admin-net      | bridge   | YES     | 10.50.100.1/24  | none                      |             | 1       | CREATED | +----------------+----------+---------+-----------------+---------------------------+-------------+---------+---------+ | lab-persistent | bridge   | YES     | 10.50.20.1/24   | none                      |             | 1       | CREATED | +----------------+----------+---------+-----------------+---------------------------+-------------+---------+---------+ | lab-stateless  | bridge   | YES     | 10.50.10.1/24   | none                      |             | 1       | CREATED | +----------------+----------+---------+-----------------+---------------------------+-------------+---------+---------+ | lxdbr0         | bridge   | YES     | 10.185.121.1/24 | fd42:a62a:6aaa:de4d::1/64 |             | 1       | CREATED | +----------------+----------+---------+-----------------+---------------------------+-------------+---------+---------+ | wlo1           | physical | NO      |                 |                           |             | 0       |         | +----------------+----------+---------+-----------------+---------------------------+-------------+---------+---------+` |
| `lxc profile list +------------+----------------------------------------+---------+ |    NAME    |              DESCRIPTION               | USED BY | +------------+----------------------------------------+---------+ | admin      | Entorno de administración              | 0       | +------------+----------------------------------------+---------+ | default    | Default LXD profile                    | 0       | +------------+----------------------------------------+---------+ | persistent | VMs persistentes para alumnos          | 0       | +------------+----------------------------------------+---------+ | stateless  | Contenedores efímeros sin persistencia | 0       | +------------+----------------------------------------+---------+` |
| `lxc project list +-------------------+--------+----------+-----------------+-----------------+----------+---------------+-----------------------------------+---------+ |       NAME        | IMAGES | PROFILES | STORAGE VOLUMES | STORAGE BUCKETS | NETWORKS | NETWORK ZONES |            DESCRIPTION            | USED BY | +-------------------+--------+----------+-----------------+-----------------+----------+---------------+-----------------------------------+---------+ | default (current) | YES    | YES      | YES             | YES             | YES      | YES           | Default LXD project               | 8       | +-------------------+--------+----------+-----------------+-----------------+----------+---------------+-----------------------------------+---------+ | labs              | YES    | YES      | YES             | YES             | YES      | NO            | Entorno de laboratorio de alumnos | 1       | +-------------------+--------+----------+-----------------+-----------------+----------+---------------+-----------------------------------+---------+ | test              | YES    | YES      | YES             | YES             | NO       | NO            | Proyecto por defecto para pruebas | 1       | +-------------------+--------+----------+-----------------+-----------------+----------+---------------+-----------------------------------+---------+` |
| `lxc image list local +------------------------+--------------+--------+---------------------------------------------+--------------+-----------------+-----------+-----------------------------+ |         ALIAS          | FINGERPRINT  | PUBLIC |                 DESCRIPTION                 | ARCHITECTURE |      TYPE       |   SIZE    |         UPLOAD DATE         | +------------------------+--------------+--------+---------------------------------------------+--------------+-----------------+-----------+-----------------------------+ | ubuntu-22.04-container | a6d2f7222476 | no     | ubuntu 22.04 LTS amd64 (release) (20251122) | x86_64       | CONTAINER       | 444.46MiB | Dec 2, 2025 at 6:13pm (UTC) | +------------------------+--------------+--------+---------------------------------------------+--------------+-----------------+-----------+-----------------------------+ | ubuntu-22.04-vm        | cf181d732f32 | no     | ubuntu 22.04 LTS amd64 (release) (20251122) | x86_64       | VIRTUAL-MACHINE | 628.65MiB | Dec 2, 2025 at 6:12pm (UTC) | +------------------------+--------------+--------+---------------------------------------------+--------------+-----------------+-----------+-----------------------------+` |

LO SIGUIENTE ES CREAR UNA IMAGEN BASE CON CLUD-INIT PARA CREAR LAS MAQUINAS PARA LOS ALUMNOS Y UN CLOUD-INIT POR ALUMNO (UTILIZAR PLANTILLA) PAR TERMINAR DE CONFIGURAR LA IMAGEN