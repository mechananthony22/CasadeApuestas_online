# ADR 0001: Modelo de Contenedores y Persistencia de Datos

* **ID:** 0001
* **Título:** Modelo de contenedores y persistencia
* **Fecha:** 2026-05-26
* **Autor:** Grupo de Desarrollo - FairBet Lab

---

## Contexto
Para el desarrollo de la plataforma educativa de simulación de apuestas deportivas **FairBet Lab**, se requiere configurar un entorno local robusto, reproducible y escalable. El sistema depende de múltiples servicios clave:
1. Un servidor de aplicaciones web (Django) con soporte de tiempo real (Daphne/WebSockets).
2. Un motor de base de datos relacional (PostgreSQL) para la persistencia transaccional ACID de la contabilidad de partida doble.
3. Un intermediario de mensajería rápido en memoria (Redis) para servir como Channel Layer en WebSockets y como bróker de tareas asíncronas de Celery.
4. Tareas asíncronas en segundo plano (Celery Worker) y temporizadores (Celery Beat) para la actualización en vivo de cuotas y resolución de apuestas.

Necesitamos decidir cómo empaquetar, ejecutar y persistir los datos de todos estos servicios en desarrollo local de manera limpia y portable.

---

## Opciones Consideradas

### Opción 1: Instalación Nativa en la Máquina Local (Host)
Ejecutar PostgreSQL, Redis, Django y Celery instalados directamente en el sistema operativo del desarrollador.

* **Pros:**
  * Menor consumo de recursos de CPU y RAM en comparación con la virtualización o contenedores.
  * Acceso directo a los servicios en localhost sin configuraciones de red virtual.
* **Contras:**
  * Inconsistencias de versiones ("en mi máquina funciona"): diferencias entre entornos macOS, Windows y Linux.
  * Proceso de instalación complejo y propenso a errores para cada desarrollador (configurar extensiones de postgres, sockets de redis, colas de celery, etc.).
  * Dificultad extrema para simular exactamente el entorno de producción (PostgreSQL 16, Redis 7).

### Opción 2: Virtualización Total (Máquinas Virtuales con Vagrant/VirtualBox)
Crear una máquina virtual completa que contenga todo el entorno.

* **Pros:**
  * Aislamiento completo a nivel de Kernel del sistema operativo.
* **Contras:**
  * Consumo excesivo de memoria RAM y almacenamiento en disco.
  * Tiempos de arranque lentos.
  * Dificultad para mantener carpetas sincronizadas en tiempo real sin latencia al editar código.

### Opción 3: Contenerización Modular con Docker y Docker Compose (Elegida)
Definir cada servicio como un contenedor Docker ligero e independiente, orquestado localmente mediante Docker Compose, con volúmenes nombrados para persistencia.

* **Pros:**
  * **Consistencia absoluta:** El entorno de desarrollo local es idéntico al de producción.
  * **Portabilidad:** Se levanta todo el stack completo con un único comando (`docker-compose up`).
  * **Aislamiento modular:** Si un servicio falla o se reinicia (ej. la base de datos), no afecta el estado del host.
  * **Persistencia inmutable:** El uso de volúmenes de Docker (`postgres_data`, `redis_data`) garantiza que los datos financieros e históricos no se pierdan cuando los contenedores se destruyan o actualicen.
  * **Live-Reload en caliente:** Mediante montajes de volúmenes tipo bind (`./backend:/app`), cualquier cambio de código en el host se refleja instantáneamente dentro del contenedor.
* **Contras:**
  * Pequeña sobrecarga en Windows/macOS debido a la capa de traducción de la máquina virtual WSL2/Hyper-V (mínima con hardware moderno).

---

## Decisión
Hemos elegido la **Opción 3 (Docker & Docker Compose)**. 

Se define una arquitectura distribuida en 5 contenedores independientes y especializados compartiendo una misma red virtual (`fairbet_network`):
1. **`db`**: PostgreSQL 16 (con volumen persistente `fairbet_postgres_data` montado en `/var/lib/postgresql/data`).
2. **`redis`**: Redis 7 (con volumen persistente `fairbet_redis_data` montado en `/data`), actuando como bróker.
3. **`backend`**: Django levantado mediante el servidor ASGI **Daphne** para dar soporte nativo a HTTP y WebSockets (Channels).
4. **`celery_worker`**: Proceso separado de Celery para procesar transacciones asíncronas y consumo de la API en background.
5. **`celery_beat`**: Planificador para disparar las tareas de sincronización periódicas.

Se utiliza además un archivo `docker-compose.override.yml` para habilitar el live-reload en desarrollo montando el código fuente local en `/app`.

---

## Consecuencias
* **Lo que se vuelve más fácil:**
  * Onboarding de nuevos desarrolladores instantáneo (`make up`).
  * Las pruebas de integración y los tests unitarios corren de forma aislada y limpia.
  * Cero riesgo de corrupción de datos locales gracias a la persistencia en volúmenes Docker con nombres fijos.
* **Lo que se vuelve más difícil:**
  * El debugging interactivo directo requiere adjuntar la terminal (`docker attach` o `make shell`).
  * Es obligatorio gestionar variables de entorno seguras mediante archivos `.env` no versionados.
* **Deuda técnica asumida:**
  * Dependencia directa de la instalación de Docker Desktop en el host.
