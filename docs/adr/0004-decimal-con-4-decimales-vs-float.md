# ADR 0004: Decimal con 4 Decimales vs. Float para Montos Financieros

* **ID:** 0004
* **Título:** Precisión numérica: Decimal(18,4) vs. float
* **Fecha:** 2026-05-26
* **Autor:** Grupo de Desarrollo - FairBet Lab
* **Estado:** Decisión Tomada

---

## Contexto

FairBet Lab maneja montos de fichas virtuales que representan valores financieros. La elección del tipo de dato numérico para almacenar y operar estos montos es crítica para la integridad del sistema. Las opciones principales son:

1. **`float` / `double`**: Tipos de punto flotante de precisión binaria (IEEE 754).
2. **`Decimal`**: Tipo de punto fijo con precisión configurable.

---

## Opciones Consideradas

### Opción 1: Float (punto flotante binario)

Usar `FloatField` en Django y `float` en Python para montos.

* **Pros:**
  * Rendimiento superior en operaciones aritméticas (hardware nativo).
  * Menor espacio de almacenamiento (8 bytes por valor).
  * APIs de terceros suelen devolver floats (API-Football).
* **Contras:**
  * **Errores de redondeo acumulativos:** `0.1 + 0.2 != 0.3` en punto flotante binario.
  * **Imprecisión en comparaciones:** Dos valores "iguales" pueden no serlo por errores de redondeo.
  * **Problemas de auditoría:** Si los montos no son exactos, no se puede verificar el invariante `suma = 0`.
  * **Regulatorio:** Ningún sistema financiero real usa float.

### Opción 2: Decimal con precisión 18,4 (Elegida)

Usar `DecimalField(max_digits=18, decimal_places=4)` en Django y `Decimal` de Python.

* **Pros:**
  * **Precisión exacta:** Cada operación aritmética mantiene la precisión configurada.
  * **Comparaciones confiables:** `Decimal('0.1') + Decimal('0.2') == Decimal('0.3')` es siempre verdadero.
  * **Auditable:** Los montos se almacenan exactamente como se ingresaron.
  * **Estándar financiero:** Todos los sistemas bancarios usan decimal con precisión fija.
  * **Soporte nativo de PostgreSQL:** `NUMERIC(18,4)` es el tipo recomendado por PostgreSQL para datos financieros.
* **Contras:**
  * Menor rendimiento aritmético (software vs hardware).
  * Mayor espacio de almacenamiento (variable, típicamente 9-13 bytes).
  * Requiere conversión explícita al interactuar con APIs que devuelven floats.

---

## Decisión

Hemos elegido la **Opción 2 (Decimal con max_digits=18, decimal_places=4)**.

**Justificación:** El requerimiento explícito del reto prohíbe el uso de `float` en montos. Además, la precisión exacta de `Decimal` es indispensable para:
1. Verificar el invariante `SUM(credits) - SUM(debits) = 0`.
2. Calcular payouts de apuestas sin errores de redondeo.
3. Garantizar que los límites de juego responsable se cumplan exactamente.

Los 4 decimales permiten representar fracciones de fichas con precisión suficiente para cuotas decimales (ej: 2.5000) y evitar errores de truncamiento.

---

## Consecuencias

* **Lo que se vuelve más fácil:**
  * Verificación de invariantes financieros con exactitud.
  * Cálculo de cuotas y payouts sin errores de redondeo.
  * Conversión a tipos numéricos de PostgreSQL sin pérdida.
* **Lo que se vuelve más difícil:**
  * Interacción con APIs externas que devuelven floats (requiere conversion `Decimal(str(valor))`).
  * Serialización JSON: `Decimal` no es serializable por defecto; se debe convertir a string.
* **Deuda técnica asumida:**
  - Los valores en JSON se transmiten como strings (ej: `"2.5000"`) en lugar de números.
  - El rendimiento de agregaciones `SUM` en tablas grandes puede ser ligeramente menor que con `float`.
