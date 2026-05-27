# Documento de Fase 6: Tiempo Real (WebSockets + Daphne + Channels)

## Fecha
27 de mayo de 2026

---

## Archivos Creados/Modificados

### Nuevos
| Archivo | Descripción |
|---------|-------------|
| `docs/adr/0010-tiempo-real-channels.md` | ADR #10: Arquitectura de Tiempo Real mediante Daphne y Django Channels |
| `backend/apps/betting/consumers.py` | Consumidores de WebSockets (`EventConsumer` y `UserNotificationConsumer`) para gestionar la comunicación bidireccional y grupos. |
| `backend/apps/betting/routing.py` | Definición de las expresiones regulares de enrutamiento WebSocket (`websocket_urlpatterns`). |
| `docs/documentofase6.md` | Documentación oficial de finalización de la Fase 6 |

### Modificados
| Archivo | Cambio |
|---------|--------|
| `backend/config/asgi.py` | Incorporación y enrutamiento del stack de protocolos WebSockets mediante `AuthMiddlewareStack` y `URLRouter` vinculados a `websocket_urlpatterns`. |
| `backend/apps/betting/tasks.py` | Integración de disparadores síncronos de WebSockets (`group_send`) al confirmar transacciones de liquidación de apuestas en `settle_finished_matches()`. |
| `backend/apps/betting/tests.py` | Ampliación de la suite de pruebas unitarias con la clase `WebSocketRealTimeTestCase` utilizando `WebsocketCommunicator` para validar canales públicos y privados seguros. |

---

## Canales y Mensajes de WebSockets

Se habilitaron dos canales de comunicación de tiempo real de alta eficiencia y baja latencia (< 5ms):

### 1. Canal Público de Eventos (`ws/events/{event_id}/`)
* **Consumidor**: `EventConsumer` (suscrito al grupo `event_{event_id}`).
* **Mensajes Emitidos**:
  - **`event_update`**: Notifica en vivo cambios en marcadores (goles local/visitante) o estados de partidos (ej. programado -> en vivo -> finalizado).
  - **`odds_changed`**: Notifica fluctuaciones de cuotas de mercados del partido (re-cotización en tiempo real).

### 2. Canal Privado de Notificaciones (`ws/notifications/`)
* **Consumidor**: `UserNotificationConsumer` (suscrito al grupo `user_{user_id}`).
* **Seguridad Estricta**: Exige autenticación obligatoria del usuario conectado (`scope["user"].is_authenticated`). Si es anónimo, la conexión es rechazada por seguridad (`403 Forbidden`).
* **Mensajes Emitidos**:
  - **`bet_accepted`**: Confirmación inmediata del ticket aceptado tras HTTP síncrono.
  - **`cashout_accepted`**: Confirmación inmediata de cobro anticipado exitoso.
  - **`bet_settled`**: Alerta instantánea emitida por Celery al liquidarse las apuestas asociadas como ganadoras, perdidas o anuladas.

---

## Integración con Daphne y Celery Workers

1. **ASGI Daphne Server**: El servidor Daphne intercepta el tráfico de red de forma unificada. Mapea peticiones estándar HTTP al WSGI clásico y desvía conexiones persistentes `ws://` a la capa ASGI de Channels.
2. **Redis Channel Layer**: Los Celery workers (que se ejecutan en procesos aislados) se comunican con los WebSockets de Daphne enviando mensajes a través de Redis como broker común (`channel_layer.group_send`), lo cual garantiza una arquitectura escalable y distribuida de alta disponibilidad.

---

## Suite de Pruebas y Cobertura

Se implementó la suite completa de pruebas utilizando **`WebsocketCommunicator`** en la clase **`WebSocketRealTimeTestCase`**:
1. **Conexión Pública Exitosa (`test_conexion_publica_event_consumer_exitosa`)**: Valida que un cliente común pueda conectarse al canal de un partido y recibir en vivo fluctuaciones de cuotas enviadas por el servidor.
2. **Rechazo de Usuarios Anónimos (`test_conexion_privada_user_notification_consumer_anonimo_rechazada`)**: Valida que las conexiones a la ruta de notificaciones privadas sean rechazadas si no están autenticadas.
3. **Notificación Privada Segura (`test_conexion_privada_user_notification_consumer_autenticado_exitosa`)**: Valida que un usuario autenticado reciba con éxito notificaciones sobre la resolución de sus tickets.
