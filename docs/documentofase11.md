# Fase 11: Apuestas Combinadas e In-Play

Esta fase del proyecto **FairBet Lab** introduce las funcionalidades avanzadas de **Apuestas Combinadas (Acumuladas)** y el motor de **Apuestas In-Play (Apuestas en Vivo)** con suspensión en tiempo real de mercados ante goles y reanudación temporizada por Celery, cumpliendo con las regulaciones de la **Ley 31557** de Perú.

---

## 1. Características Implementadas

### A. Apuestas Combinadas (Acumuladas)
* **Producto de Cuotas**: El usuario puede agrupar múltiples selecciones independientes en un único ticket. La cuota final acumulada se calcula dinámicamente como el producto de las cuotas individuales de cada selección.
* **Integración Contable de Partida Doble**:
  - Al colocar la apuesta combinada, se debita el stake total del balance del usuario y se retiene en la cuenta de custodia temporal `apuestas_pendientes`.
  - Si una sola selección del acumulador se resuelve como **perdida**, todo el boleto se liquida de forma transaccional como **perdida** y la casa retiene el stake (`CASA` recibe un crédito por el stake).
  - Si todas las selecciones ganan, la apuesta se liquida como **ganada** y el usuario recibe el retorno total (`payout = stake × cuota_combinada`).
  - Si ocurren cancelaciones/anulaciones de partidos, esa selección se reduce a cuota `1.0` (efectuando un recálculo justo de la cuota final acumulada).
* **Validación de Exclusión Mutua**: El backend síncrono rechaza automáticamente cualquier intento de combinar múltiples opciones pertenecientes al mismo evento deportivo (ej: apostar a "Real Madrid Gana" y "Empate" del mismo clásico), protegiendo la viabilidad matemática de la casa.

### B. Apuestas In-Play (En Vivo)
* **Aceptación de Apuestas en Juego**: El sistema permite colocar boletos síncronos sobre eventos deportivos que ya han iniciado, siempre y cuando su estado sea `'in_play'` (en vivo).
* **Fluctuación de Cuotas**: Las cuotas en vivo se actualizan periódicamente y son transmitidas al instante mediante WebSockets para la visualización del usuario.

### C. Suspensión Temporizada ante Eventos Críticos (Goles)
Para mitigar el riesgo de arbitraje por latencia (ventaja informativa de transmisiones más rápidas que el feed de datos de la casa):
* **Detección en Vivo**: Durante la ejecución periódica de `sync_live_scores`, si se detecta un cambio en el marcador (`home_score` o `away_score`), el sistema activa la suspensión de seguridad.
* **Inhabilitación Transaccional**: Todos los mercados asociados al partido son marcados inmediatamente como inactivos en base de datos (`is_active = False`).
* **Rechazo Síncrono**: Cualquier petición síncrona HTTP POST para colocar una apuesta sobre un mercado suspendido es ineludiblemente rechazada por el serializer con un código HTTP `400 Bad Request`.
* **Notificaciones WebSocket**: Se transmite el evento `market_suspended` de forma instantánea a los clientes conectados para deshabilitar las opciones de apuesta en la interfaz.
* **Reactivación Automática con Celery**: Al gatillarse la suspensión, se programa la tarea Celery `resume_markets_after_suspension` especificando un retraso asíncrono nativo (**countdown de 15 segundos**). Al ejecutarse, la tarea reactiva los mercados (`is_active = True`) y transmite el evento `market_resumed` por WebSockets.

---

## 2. Decisiones de Arquitectura

* **ADR 0012 (Política de Suspensión In-Play)**: Detalla la lógica de la suspensión temporal transitoria de 15 segundos. Se optó por el programador nativo de `Celery` con `countdown` en lugar de retrasos síncronos (`time.sleep()`), previniendo el bloqueo innecesario de hilos de trabajadores Celery y asegurando una altísima escalabilidad bajo picos de concurrencia en partidos importantes.

---

## 3. Mensajes en Tiempo Real (WebSockets)

* **`market_suspended`**:
  Enviado por WebSocket al grupo `event_{id}` cuando un gol gatilla la suspensión:
  ```json
  {
      "type": "market_suspended",
      "event_id": 901,
      "duration": 15,
      "reason": "goal",
      "message": "Mercados suspendidos temporalmente debido a un evento crítico en vivo (GOL)."
  }
  ```
* **`market_resumed`**:
  Enviado por WebSocket al grupo `event_{id}` cuando se cumple el cooldown de 15 segundos y los mercados vuelven a abrirse:
  ```json
  {
      "type": "market_resumed",
      "event_id": 901,
      "message": "Los mercados se han reanudado y vuelven a recibir apuestas."
  }
  ```

---

## 4. Cobertura y Resultados de Pruebas

La suite completa de pruebas unitarias y de integración en `apps/betting/tests.py` consta de **36 pruebas**, aprobadas al **100%** de forma exitosa. Se destaca el nuevo bloque `LiveAndCombinadasTestCase` que cubre:
1. Colocación exitosa de combinadas, producto de cuotas y liquidación como ganada en partida doble.
2. Colocación de combinadas y resolución como perdida ante fallo de una única opción.
3. Colocación exitosa de boletos in-play sobre eventos activos.
4. Detección automática de goles, suspensión y bloqueo síncrono del serializer.
5. Reactivación automática de mercados mediante Celery.
6. Coexistencia sin bloqueos síncronos en pruebas de concurrencia gracias al patch de simulación forense de IP.

### Cobertura de Código Obtenida:
* **Cobertura de betting**: **88%** (superando holgadamente el 80% reglamentario del reto).
* **Tests de in-play y combinadas**: **100% exitosos** (5 pruebas agregadas, aprobadas con éxito en 7.10 segundos).
