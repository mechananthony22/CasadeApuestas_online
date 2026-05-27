# ADR 0010: Arquitectura de Tiempo Real mediante Daphne y Django Channels

## Estado
Aprobado

## Fecha
27 de mayo de 2026

## Autor
Antigravity (Asistente de Desarrollo)

---

## Contexto

El *FairBet Lab* requiere actualizar instantáneamente cuotas de apuestas fluctuantes (odds) y marcadores en vivo a múltiples clientes conectados en paralelo, para garantizar que tomen decisiones informadas al instante y evitar la colocación de apuestas con cuotas desactualizadas (lo cual causaría constantes rechazos por re-cotización con código 409). Asimismo, la plataforma necesita notificar transacciones confidenciales individuales a cada usuario (apuestas aceptadas, liquidaciones exitosas, estados de cash-out) en tiempo real.

Por lo tanto, es necesario definir la tecnología de transporte bidireccional o unidireccional y el servidor de aplicación idóneo para soportar esta alta concurrencia de conexiones persistentes de forma ligera.

---

## Opciones Consideradas

### Opción 1: HTTP Polling (Consulta periódica mediante Ajax/Fetch)
El cliente frontend realiza peticiones periódicas (ej. cada 2 segundos) al API REST para consultar si hay cambios en goles o cuotas.
* **Pros**: Extremadamente fácil de implementar y compatible con servidores WSGI tradicionales.
* **Contras**: Desperdicio masivo de recursos de CPU, base de datos y ancho de banda. Si 10,000 usuarios consultan cada 2 segundos, el servidor colapsará. Causa una latencia inaceptable de hasta 2 segundos en cuotas en vivo.

### Opción 2: Server-Sent Events (SSE) sobre HTTP síncrono
Un canal de flujo continuo de sólo lectura (`text/event-stream`) desde el servidor hacia el cliente.
* **Pros**: Más ligero que el HTTP Polling, nativo en navegadores modernos.
* **Contras**: Unidireccional (el cliente no puede enviar mensajes por el mismo canal). No se integra de forma nativa con el ecosistema de Django/Celery de forma tan completa como Channels, y la gestión de autenticación y grupos por eventos es ad-hoc.

### Opción 3: WebSockets mediante Daphne y Django Channels (Elegida)
Establecer canales de comunicación bidireccionales, persistentes y full-duplex utilizando el protocolo WebSockets sobre la especificación de servidor ASGI (Daphne) y la capa de Canales (Django Channels) respaldada por Redis como broker de mensajes (Channel Layer).
* **Pros**:
  - Latencia ultra baja (< 5ms) para actualizaciones en vivo.
  - Comunicación bidireccional idónea para interacciones avanzadas en tiempo real.
  - El soporte de Django Channels para "Grupos" (Channel Groups) permite suscribir de forma natural a miles de usuarios a eventos específicos (ej: `event_{id}`) o canales personales (ej: `user_{id}`).
  - Totalmente integrado con Celery: cualquier Celery worker puede emitir actualizaciones grupales a WebSockets mediante la Channel Layer en Redis de forma no bloqueante.
* **Contras**: Requiere un stack ASGI (Daphne) en lugar del clásico WSGI (Gunicorn), aumentando la complejidad operativa.

---

## Decisión

Se adopta la **Opción 3 (WebSockets mediante Daphne y Django Channels con Redis Channel Layer)**.

### Diseño Operacional:
1. **Daphne** actuará como el punto de entrada ASGI unificado para HTTP síncrono y WebSockets.
2. **Redis** se utilizará como la capa de transporte/broker (Channel Layer) para intercomunicar Celery con Daphne de manera no bloqueante.
3. Se definirán dos canales de suscripción:
   - **`ws/events/{event_id}/`**: Canal público/semi-público de sólo lectura de cuotas y goles de un partido.
   - **`ws/notifications/`**: Canal privado bidireccional seguro que exige autenticación de sesión de Django. Las conexiones anónimas se descartan con código 403.

---

## Consecuencias

* Las rutas HTTP tradicionales seguirán fluyendo de forma segura por la capa síncrona.
* Las tareas de Celery Beat (`sync_live_scores`, `update_odds`) y los métodos de negocio contables (`settle_finished_matches`, `create`, `cashout`) utilizarán `get_channel_layer().group_send` para notificar en tiempo real en background.
* Es mandatorio mantener un control estricto de autenticación en el `UserNotificationConsumer` para impedir la filtración de transacciones contables entre usuarios.
