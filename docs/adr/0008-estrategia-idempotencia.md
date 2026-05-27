# ADR 0008: Estrategia de Idempotencia para Colocación de Apuestas

## Estado
Aprobado

## Fecha
27 de mayo de 2026

## Autor
Antigravity (Asistente de Desarrollo)

---

## Contexto

En el desarrollo de plataformas transaccionales, las redes de datos móviles e inalámbricas sufren micro-cortes frecuentes. Si un usuario envía una solicitud HTTP POST para colocar una apuesta y la red se interrumpe justo después de que el servidor la procesa pero antes de que la respuesta retorne al dispositivo del usuario, el cliente reintentará la petición automáticamente o el usuario hará clic nuevamente en el botón "Confirmar".

Sin un mecanismo de idempotencia, esto resultaría en:
1. **Doble colocación de la misma apuesta** (gastando saldo dos veces).
2. **Duplicidad contable** en el libro diario de Ledger (partida doble).
3. **Inconformidad regulatoria** extrema según las normativas de juego del MINCETUR.

Debemos implementar una estrategia que garantice que, sin importar cuántas veces se reintente la misma petición, la apuesta se procesará **exactamente una vez** y el cliente recibirá la misma respuesta exitosa.

---

## Opciones Consideradas

### Opción 1: Idempotencia basada únicamente en la base de datos (Unique Constraint)
Se define una columna `idempotency_key` con restricción `UNIQUE` en la tabla `Bet`. Si llega un request duplicado, la base de datos bloquea el insert y lanza una excepción de integridad (`IntegrityError`).
* **Pros**: Infalible a nivel de consistencia de persistencia (garantía ACID de PostgreSQL).
* **Contras**:
  - Si el primer request fue exitoso y se reintenta, el segundo request fallará y el usuario recibirá un error feo (`500` o `400` indicando clave duplicada) en lugar de una confirmación amigable.
  - Genera sobrecarga y latencia innecesaria en la base de datos relacional para validar duplicados.

### Opción 2: Idempotencia basada en memoria caché en Redis (Redis TTL)
El cliente genera un UUID v4 antes del envío y lo añade en la cabecera `Idempotency-Key`. El servidor intercepta la solicitud, verifica si la clave existe en Redis (`idempotency_{key}`) y si es así, retorna inmediatamente la respuesta originalmente cacheada. Si no existe, procesa la apuesta y registra el resultado en Redis por 5 minutos (300 segundos).
* **Pros**:
  - Extremadamente veloz (lectura en Redis en < 2ms).
  - Permite retornar la respuesta original exacta (cuerpo JSON y código HTTP) en reintentos exitosos, simulando un procesamiento transparente.
* **Contras**: Si Redis llega a vaciarse o reiniciarse durante el intervalo, se pierde la protección contra duplicados.

### Opción 3: Estrategia híbrida: Redis Cache (TTL 5 min) + Unique DB Constraint (Elegida)
Se combinan ambas soluciones:
1. El cliente envía obligatoriamente la cabecera `Idempotency-Key` (UUID v4).
2. El backend verifica la clave en Redis. Si se encuentra, retorna la respuesta cacheada al instante.
3. Si no se encuentra en Redis, se procesa la apuesta dentro de una transacción atómica `@transaction.atomic`. La columna `idempotency_key` en la tabla `Bet` cuenta con una restricción `unique=True` y un índice de base de datos.
4. Tras registrar exitosamente la apuesta y el movimiento en Ledger, el resultado se guarda en Redis con un tiempo de expiración (TTL) de 300 segundos.

* **Pros**:
  - **Doble blindaje**: Redis proporciona una respuesta ultrarrápida y transparente para el apostador, mientras que PostgreSQL actúa como el último muro de contención infalible ante condiciones extremas de concurrencia y fallos de infraestructura.
  - Experiencia de usuario inmejorable ante desconexiones de red.
* **Contras**: Requiere mayor complejidad técnica y el uso conjunto de Redis y PostgreSQL.

---

## Decisión

Se elige la **Opción 3 (Estrategia híbrida: Redis Cache + Unique DB Constraint)** por ser la única que garantiza máxima velocidad y protección absoluta contra dobles cobros accidentales.

---

## Consecuencias

* Se definió el campo `idempotency_key = models.UUIDField(unique=True, db_index=True)` en el modelo `Bet` de `apps/betting/models.py`.
* En la vista `BetViewSet.create`, se implementó la intercepción y lectura en la caché por defecto de Django (la cual está respaldada por Redis mediante `channels_redis` y `django-celery-beat` como se configuró en `base.py`).
* Se requiere que todos los clientes de frontend generen un UUID v4 único por cada intento de colocación en el boleto y lo incluyan en la cabecera HTTP.
