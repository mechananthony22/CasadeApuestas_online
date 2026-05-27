# ADR 0003: Partida Doble vs. Saldo Almacenado

* **ID:** 0003
* **Título:** Estrategia de contabilidad: partida doble vs. saldo almacenado
* **Fecha:** 2026-05-26
* **Autor:** Grupo de Desarrollo - FairBet Lab
* **Estado:** Decisión Tomada

---

## Contexto

El sistema de wallet de FairBet Lab debe manejar montos de fichas virtuales con precisión quirúrgica, ya que sobre esta base se construyen todas las operaciones financieras: depósitos, retiros, apuestas, cashouts y liquidaciones. Existen dos estrategias principales para modelar el saldo del usuario:

1. **Saldo almacenado (columna `balance` en UserProfile)**: Mantener una columna `balance` que se actualiza en cada operación.
2. **Partida Doble (LedgerEntry)**: No almacenar el saldo, sino calcularlo dinámicamente como `SUM(credits) - SUM(debits)` a partir de un libro contable inmutable.

La elección tiene implicaciones directas sobre la integridad financiera, la auditabilidad y la complejidad del sistema.

---

## Opciones Consideradas

### Opción 1: Saldo Almacenado en Columna (Balance caching)

Mantener un campo `balance` en `UserProfile` que se actualiza atómicamente en cada operación.

* **Pros:**
  * Consulta de saldo O(1) — extremadamente rápida, sin JOINs ni agregaciones.
  * Implementación simple y familiar para desarrolladores nuevos.
  * Menos carga en la base de datos para lecturas frecuentes.
* **Contras:**
  * **Riesgo de desincronización:** Si una transacción falla a medias (por error de red, crash del servidor), el `balance` puede quedar en un estado inconsistente respecto a los movimientos reales.
  * **Sin pista de auditoría:** No hay un registro histórico de cómo se llegó a ese saldo. Es imposible demostrar que el saldo es correcto sin logs externos.
  * **Dificultad para detectar fraudes:** Sin un libro contable, es difícil rastrear movimientos sospechosos.
  * **Problemas de concurrencia:** Múltiples transacciones simultáneas pueden causar race conditions en la actualización del campo `balance`.

### Opción 2: Partida Doble con LedgerEntry (Elegida)

Registrar cada operación como entradas inmutables en un libro contable (`LedgerEntry`), donde cada transacción crea al menos dos registros balanceados (débito + crédito), y el saldo se calcula mediante agregación.

* **Pros:**
  * **Integridad financiera demostrable:** El invariante `SUM(credits) - SUM(debits) = 0` por transacción se puede verificar mediante queries. Si alguna transacción está desbalanceada, el sistema lo detecta.
  * **Pista de auditoría completa:** Cada movimiento tiene un registro inmutable con timestamp, usuario, monto, dirección y un UUID de transacción que agrupa las contrapartidas.
  * **Sin estado almacenado:** No existe un solo campo de "saldo" que pueda corromperse. El saldo es un dato derivado, no almacenado.
  * **Recuperación ante fallos:** Si un servidor se cae a media transacción, la base de datos garantiza que ninguna entrada quede huérfana (gracias a `transaction.atomic`).
  * **Detección de fraudes:** Cualquier manipulación del historial requiere modificar entradas individuales, lo cual rompe los invariantes agregados.
* **Contras:**
  * **Consulta de saldo O(n):** Calcular el saldo requiere scanear todas las entradas del usuario en `wallet_usuario` (mitigado con índices en `user`+`account` y `direction`).
  * **Mayor almacenamiento:** Cada transacción genera múltiples registros (mínimo 2 por operación).
  * **Complejidad conceptual:** Los desarrolladores deben entender el modelo de partida doble para trabajar correctamente con el wallet.

---

## Decisión

Hemos elegido la **Opción 2 (Partida Doble — LedgerEntry)**.

**Justificación:** El requerimiento explícito del reto establece que "el saldo siempre se calcula por SUM(credits) − SUM(debits), nunca se guarda". Además, la partida doble es el estándar de la industria financiera real (bancos, casas de bolsa, exchanges) y es la única manera de demostrar integridad financiera en una auditoría.

---

## Consecuencias

* **Lo que se vuelve más fácil:**
  * Auditoría completa y demostrable de todos los movimientos financieros.
  * Detección automática de inconsistencias mediante queries de verificación.
  * Cumplimiento del requisito explícito del reto (partida doble).
* **Lo que se vuelve más difícil:**
  * Las consultas de saldo requieren índices adecuados para ser rápidas (índice compuesto en `user`+`account`+`direction`).
  * El volumen de datos crece 2x-3x más rápido que con saldo almacenado.
  * La lógica de las vistas debe usar `select_for_update` y `transaction.atomic` consistentemente.
* **Deuda técnica asumida:**
  - No hay un caché de saldo. Para usuarios con millones de transacciones, la consulta de saldo podría requerir optimizaciones futuras como una tabla de snapshot diario.
  - Los queries de balance no usan `read-your-writes` si se consulta fuera de la transacción.
