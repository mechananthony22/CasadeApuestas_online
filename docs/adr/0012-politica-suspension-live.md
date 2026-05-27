# ADR 0012: Política de Suspensión Automática de Mercados en Vivo (In-Play)

## Estado
Aprobado

## Fecha
27 de mayo de 2026

## Autor
Antigravity (Asistente de Desarrollo)

---

## Contexto

El *FairBet Lab*, bajo los lineamientos de juego justo e integridad financiera de la Ley 31557 peruana, debe prevenir el arbitraje y la colocación de apuestas abusivas por parte de jugadores que cuenten con feeds de datos en tiempo real de menor latencia (como transmisiones de video en vivo de alta velocidad) en comparación con el feed del operador.

Específicamente, cuando ocurre un "evento crítico" (por ejemplo, un gol o una expulsión de tarjeta roja):
1. Las cuotas y probabilidades locales del partido se vuelven temporalmente inválidas y obsoletas.
2. Los apostadores aventajados pueden colocar tickets a cuotas desactualizadas muy altas antes de que el motor de cuotas local del operador se actualice, generando pérdidas seguras para la casa de apuestas.
3. Se requiere suspender inmediatamente la aceptación de apuestas y notificar en tiempo real a los clientes suscritos.

---

## Opciones Consideradas

### Opción 1: Procesar la actualización y dejar que las cuotas cambien sin suspensión
Permitir que el motor de sincronización (`sync_live_scores` o `update_odds`) actualice los marcadores y las cuotas sin inhabilitar el mercado, confiando exclusivamente en el mecanismo de re-cotización HTTP 409 Conflict.
* **Pros**: Menos complejidad lógica en Channels y Celery.
* **Contras**:
  - Muy alta vulnerabilidad al abuso. Un milisegundo de diferencia entre la confirmación y el cambio de cuota puede permitir apuestas a cuotas erróneas.
  - La re-cotización síncrona solo protege al usuario si este envía la cuota vieja, pero no bloquea activamente al sistema de recibir apuestas pre-match o in-play abusivas en segundos críticos.

### Opción 2: Suspensión automática transitoria con reactivación mediante tareas retrasadas de Celery (Elegida)
Al detectarse un gol (cambio en `home_score` o `away_score`) o un evento crítico durante la sincronización:
1. Inhabilitar de forma atómica en base de datos todos los mercados del evento (`is_active = False`).
2. Transmitir el evento de suspensión (`market_suspended`) mediante Django Channels.
3. Programar una tarea asíncrona de Celery (`resume_markets_after_suspension`) con un retraso nativo (**countdown de 15 segundos**) para volver a habilitar los mercados y notificar la reanudación (`market_resumed`).
* **Pros**:
  - Bloqueo robusto y definitivo en base de datos. Cualquier intento síncrono de apuesta es inmediatamente rechazado por el serializer.
  - Totalmente automatizado y desacoplado, sin interferir en los flujos principales.
  - El countdown de Celery es altamente escalable y no bloquea el hilo de ejecución con retardos síncronos.
* **Contras**: Requiere la implementación de tareas retrasadas y manejo de Channels.

---

## Decisión

Se adopta la **Opción 2 (Suspensión automática transitoria con reactivación mediante Celery)** por sus superiores garantías de seguridad transaccional e integridad operativa.

El valor predeterminado del cooldown se establece en **15 segundos**, el cual es configurable en el archivo de entorno mediante la constante `LIVE_SUSPENSION_COOLDOWN`.

---

## Consecuencias

* Se modificará `EventConsumer` en `apps/betting/consumers.py` para retransmitir eventos de suspensión y reanudación de mercados.
* Se agregará la tarea de Celery `resume_markets_after_suspension` en `apps/betting/tasks.py`.
* Se interceptará la sincronización en vivo (`SyncEngine.sync_live_scores`) para gatillar la suspensión automática ante cambios de marcador.
* Se validará la inhabilitación mediante pruebas de integración robustas.
