# ADR 0005: select_for_update vs. Locking Optimista para Concurrencia

* **ID:** 0005
* **Título:** Estrategia de concurrencia: bloqueo pesimista vs. optimista
* **Fecha:** 2026-05-26
* **Autor:** Grupo de Desarrollo - FairBet Lab
* **Estado:** Decisión Tomada

---

## Contexto

En FairBet Lab, múltiples operaciones concurrentes pueden intentar modificar el wallet del mismo usuario simultáneamente (ej: dos apuestas en paralelo, un retiro y una apuesta al mismo tiempo). Es necesario prevenir el **doble gasto** —que un usuario gaste las mismas fichas dos veces— sin degradar excesivamente el rendimiento.

Las estrategias principales de control de concurrencia son:

1. **Bloqueo Pesimista (`select_for_update`)**: Bloquear las filas relevantes al inicio de la transacción, impidiendo que otras transacciones las modifiquen hasta que termine.
2. **Locking Optimista (versión/checksum)**: Permitir que todas las transacciones avancen en paralelo y verificar al final que los datos no hayan cambiado.

---

## Opciones Consideradas

### Opción 1: Bloqueo Pesimista con `select_for_update`

Usar `User.objects.select_for_update().get(pk=user.pk)` dentro de una transacción atómica para bloquear el registro del usuario mientras se procesa la operación.

* **Pros:**
  * **100% prevención de doble gasto:** Ninguna transacción puede leer un estado desactualizado.
  * **Semántica simple y predecible:** El desarrollador sabe exactamente qué filas están bloqueadas.
  * **Soporte nativo de PostgreSQL:** `SELECT ... FOR UPDATE` es parte del estándar SQL y está optimizado en PostgreSQL.
  * **Recuperación automática:** Si una transacción falla, el bloqueo se libera y otras transacciones pueden continuar.
* **Contras:**
  * **Rendimiento limitado:** Las transacciones concurrentes al mismo usuario se serializan (una espera a la otra).
  * **Riesgo de deadlocks:** Si dos transacciones bloquean filas en diferente orden, puede ocurrir un deadlock.
  * **Escalabilidad horizontal limitada:** Bajo carga muy alta, la contención sobre las filas más populares puede ser un cuello de botella.

### Opción 2: Locking Optimista (Optimistic Concurrency Control)

Agregar un campo `version` (integer) o `updated_at` a la tabla del usuario, y verificar en el `UPDATE` que el valor no haya cambiado desde la última lectura.

* **Pros:**
  * **Máximo rendimiento en baja contención:** Las transacciones no se bloquean entre sí.
  * **Escalabilidad excelente:** No hay cuellos de botella por filas populares.
  * **Sin riesgo de deadlocks:** No hay bloqueos a nivel de base de datos.
* **Contras:**
  * **No apto para alta contención:** Si múltiples transacciones compiten por el mismo recurso, la mayoría fallará con "conflicto de versión" y deberá reintentar.
  * **Complejidad adicional:** El desarrollador debe manejar explícitamente los reintentos y la lógica de "mejor esfuerzo".
  * **Peor experiencia de usuario en contenido:** Un usuario podría ver un error "intente de nuevo" en lugar de una respuesta inmediata.

---

## Decisión

Hemos elegido la **Opción 1 (Bloqueo Pesimista — `select_for_update`)**.

**Justificación:** El reto explícitamente requiere `select_for_update` para operaciones de wallet. Además:
1. Las operaciones financieras en FairBet Lab son de corta duración (milisegundos), por lo que la contención es baja y los bloqueos se liberan rápidamente.
2. El doble gasto es inaceptable en un sistema financiero; el bloqueo pesimista garantiza 100% de prevención.
3. La complejidad de reintentos del locking optimista aumenta innecesariamente la superficie de bugs en un sistema educativo.
4. PostgreSQL maneja `select_for_update` de forma eficiente con row-level locking.

### Mitigación de Deadlocks:
Para evitar deadlocks, todas las transacciones que bloquean múltiples filas deben hacerlo SIEMPRE en el mismo orden (por ejemplo: primero el usuario, luego la casa, luego apuestas_pendientes).

---

## Consecuencias

* **Lo que se vuelve más fácil:**
  * Implementación simple y directa contra doble gasto.
  * Garantía matemática de que ningún saldo puede ser negativo.
  * Depuración más sencilla (el estado es determinista).
* **Lo que se vuelve más difícil:**
  * El rendimiento en escenarios de alta contención sobre un mismo usuario es limitado (ej: un bot haciendo 100 apuestas/segundo).
  * Se debe tener cuidado con el orden de bloqueo para evitar deadlocks.
* **Deuda técnica asumida:**
  - Si FairBet Lab creciera a millones de usuarios concurrentes apostando al mismo tiempo, podría necesitar migrar a una arquitectura de particionamiento por usuario o usar colas de operaciones (event sourcing).
  - Los tests de concurrencia deben ejecutarse con múltiples hilos/processos para verificar que el bloqueo funciona correctamente.
