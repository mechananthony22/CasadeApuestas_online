# ADR 0009: Política de Cash-out y Diseño de Liquidación de Apuestas

## Estado
Aprobado

## Fecha
27 de mayo de 2026

## Autor
Antigravity (Asistente de Desarrollo)

---

## Contexto

El *Cash-out* (cobro anticipado) permite a los usuarios mitigar riesgos asegurando ganancias o reduciendo pérdidas antes de que finalicen los eventos asociados a sus boletos de apuesta. Desde una perspectiva técnica e integridad financiera (particularmente bajo la regulación del MINCETUR Ley 31557), el *Cash-out* debe ser:
1. **Dinámico**: Debe responder a las fluctuaciones en tiempo real de las cuotas de mercado.
2. **Seguro contra fraudes y doble gasto**: No debe permitirse si el partido ya finalizó o fue suspendido, ni ejecutarse dos veces para el mismo boleto.
3. **Auditable y consistente**: Debe registrarse mediante partida doble contable ineludible en el Ledger general de la plataforma.

---

## Opciones Consideradas

### Opción 1: Cash-out con valor estático o discrecional
Definir un valor fijo para el reembolso (ej. retornar el 50% de la apuesta inicial) o permitir al usuario ingresar el monto que desea cobrar.
* **Pros**: Extremadamente fácil de implementar.
* **Contras**: Cero realismo matemático. Vulnerable a pérdidas masivas si el evento ya está ganado por el apostador, y no cumple con el estándar de una plataforma de simulación educativa avanzada.

### Opción 2: Fórmula actuarial estándar con factor de casa (Elegida)
Calcular el monto dinámicamente según la probabilidad en vivo del mercado mediante la fórmula:
$$\text{cashout} = \text{stake} \times \left(\frac{\text{odds\_original}}{\text{odds\_actual}}\right) \times \text{factor\_casa}$$
* **`odds_original`**: Cuota combinada total acordada originalmente.
* **`odds_actual`**: Cuota combinada actual en base a las cotizaciones de mercado vigentes.
* **`factor_casa`**: Coeficiente multiplicador establecido en `0.95` (comisión del 5% del operador).
* **Pros**: 
  - Simula de manera exacta el comportamiento financiero de una casa de apuestas real.
  - El factor de casa garantiza una retención justa que protege el balance de simulación general.
  - Ofrece una experiencia educativa enriquecida y fiel a la industria.
* **Contras**: Mayor complejidad matemática y requiere validación rigurosa de las cuotas activas actuales.

---

## Decisión

Se adopta la **Opción 2 (Fórmula actuarial estándar con factor de casa del 5%)**.
El cálculo se realizará síncronamente sobre HTTP, aplicando un bloqueo pesimista en el registro `Bet` (`select_for_update()`) para evitar condiciones de carrera o intentos duplicados de cash-out simultáneos.

### Reglas de Negocio Bloqueantes:
1. La apuesta original debe tener estado `accepted`.
2. Todos los partidos de las selecciones asociadas deben estar activos (estados `scheduled` o `in_play`).
3. Si alguna selección tiene estado `lost`, `won` o `void`, o su partido ha sido `finished`, `cancelled` o `suspended`, se prohíbe el cash-out de inmediato.
4. El factor de casa se define como `0.95` y se calcula con precisión de 4 decimales (`Decimal`).

---

## Consecuencias

* Se implementará la ruta `/api/v1/betting/bets/{id}/cashout/` que responderá a peticiones `POST`.
* Toda la operación financiera se registrará en partida doble contable bajo un UUID de transacción único:
  - **Débito** en `apuestas_pendientes` por el monto del `stake` original.
  - **Crédito** en `wallet_usuario` por el monto calculado del `cashout_amount`.
  - Diferencia saldada contra la cuenta de la `casa` (debitando si el cashout es mayor al stake, o acreditando si es menor).
* Se mantendrá el principio de inmutabilidad del Ledger.
