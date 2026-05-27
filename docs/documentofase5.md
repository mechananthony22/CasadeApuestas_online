# Documento de Fase 5: Liquidación + Cashout

## Fecha
27 de mayo de 2026

---

## Archivos Creados/Modificados

### Nuevos
| Archivo | Descripción |
|---------|-------------|
| `docs/adr/0009-politica-cashout.md` | ADR #9: Algoritmo actuarial y control transaccional de *Cash-out* |
| `docs/documentofase5.md` | Documentación oficial de finalización de la Fase 5 |

### Modificados
| Archivo | Cambio |
|---------|--------|
| `backend/apps/betting/models.py` | Implementación de los métodos del ciclo de vida financiero y de estados del modelo `Bet`: `settle_as_won`, `settle_as_lost`, `settle_as_cancelled` y `perform_cash_out` en partida doble. |
| `backend/apps/betting/tasks.py` | Implementación de la tarea de Celery `settle_finished_matches` para liquidación automática de apuestas simples y combinadas (con recálculo de cuotas por anulaciones) de forma transaccional. |
| `backend/apps/betting/views.py` | Implementación del endpoint de cobro anticipado (`POST /api/v1/betting/bets/{id}/cashout/`) bajo bloqueo pesimista `select_for_update` y validación de eventos activos. |
| `backend/apps/betting/tests.py` | Ampliación de la suite de pruebas unitarias e integración con la clase `SettleAndCashoutTestCase` para la validación automática de liquidaciones de Celery, cobros de cash-out dinámicos e invariantes contables. |

---

## Lógica y Métodos del Modelo `Bet`

Para garantizar la inmutabilidad y la consistencia del Ledger contable de partida doble, se implementaron métodos específicos encapsulados dentro de la clase `Bet`:

### 1. `settle_as_won(payout_amount, transaction_id)`
Liquida la apuesta como ganada.
* **Regla de Partida Doble**:
  - **Débito** en `apuestas_pendientes` por el monto del `stake` original.
  - **Débito** en `casa` por la ganancia neta (`payout_amount - stake`) si el payout supera el stake.
  - **Crédito** en `wallet_usuario` por el monto total del `payout_amount`.
  - Si el payout es menor al stake por anulaciones, la casa recibe el crédito por la diferencia.

### 2. `settle_as_lost(transaction_id)`
Liquida la apuesta como perdida.
* **Regla de Partida Doble**:
  - **Débito** en `apuestas_pendientes` por el monto del `stake` original.
  - **Crédito** en `casa` por el monto del `stake` original, absorbiendo los fondos.

### 3. `settle_as_cancelled(transaction_id)`
Anula la apuesta por eventos cancelados o reprogramados.
* **Regla de Partida Doble**:
  - **Débito** en `apuestas_pendientes` por el monto del `stake`.
  - **Crédito** en `wallet_usuario` por el monto del `stake`, reembolsando los fondos íntegramente.

### 4. `perform_cash_out(cashout_amount, transaction_id)`
Realiza el cobro anticipado síncrono.
* **Regla de Partida Doble**:
  - **Débito** en `apuestas_pendientes` por el monto del `stake`.
  - **Crédito** en `wallet_usuario` por el `cashout_amount` calculado.
  - **Crédito/Débito** en `casa` para saldar la diferencia exacta según si el cash-out es menor o mayor que la apuesta inicial.

---

## Tarea de Liquidación Periódica Celery

La tarea **`settle_finished_matches()`** se ejecuta periódicamente o bajo demanda para realizar la conciliación de apuestas:
1. Resuelve el estado (`won`, `lost`, `void`) de cada selección en base a los marcadores reales de partidos con estado `finished` o `cancelled`:
   - **1X2**: Local, Empate o Visitante.
   - **Over/Under 2.5**: Goles totales mayores o menores/iguales a 2.5.
   - **BTTS**: Ambos equipos anotan goles.
2. Analiza los tickets (`Bet`) en estado `accepted` que contengan estas selecciones.
3. Si todas las selecciones de un boleto están resueltas:
   - Si tiene al menos una pérdida, liquida como `lost`.
   - Si todas se anulan (`void`), liquida como `cancelled` (reembolso total).
   - De lo contrario, calcula el payout dinámico y liquida como `won` multiplicando las cuotas ganadoras (las selecciones anuladas aportan factor `1.0`).

---

## Endpoint de Cash-out

Se expone un endpoint RESTful transaccional bajo autenticación:

| Método | Endpoint | Descripción | Código HTTP |
|--------|----------|-------------|-------------|
| POST | `/api/v1/betting/bets/{id}/cashout/` | Calcula el cobro anticipado de un boleto en estado `accepted` usando la fórmula actuarial con factor de casa del $5\%$ ($0.95$). Actualiza el saldo en el Ledger en partida doble. | 200, 400, 404 |

* **Fórmula de cálculo matemático**:
  $$\text{cashout} = \text{stake} \times \left(\frac{\text{odds\_original}}{\text{odds\_actual}}\right) \times 0.95$$

---

## Suite de Pruebas y Cobertura

Se implementó la suite completa de integración en la clase **`SettleAndCashoutTestCase`** que verifica:
1. **Liquidación Ganadora (`test_liquidacion_apuesta_simple_ganadora`)**: Valida que una apuesta ganadora incremente el saldo disponible del usuario, libere los fondos en custodia y mantenga el invariante del Ledger global en cero.
2. **Liquidación Perdida (`test_liquidacion_apuesta_simple_perdedora`)**: Valida que una apuesta perdida asigne de forma segura los fondos a la cuenta de la casa y mantenga el Ledger balanceado.
3. **Combinada con Anulación (`test_liquidacion_apuesta_combinada_recalculo_anulacion`)**: Valida que si un partido de una combinada se anula y el otro se gana, el ticket se resuelva como ganado recalculando la cuota final excluyendo la selección anulada (factor 1.0).
4. **Cash-out Exitoso (`test_cashout_exitoso_ganancia`)**: Valida la fórmula matemática de cash-out dinámico y el abono contable correcto al usuario y a la casa.
5. **Cash-out Bloqueado por Partido Iniciado/Terminado (`test_cashout_bloqueado_si_partido_iniciado_o_finalizado`)**: Impide el cobro anticipado si el evento ya no está activo.
6. **Cash-out Duplicado (`test_cashout_doble_gasto_bloqueado`)**: Previene condiciones de carrera o intentos repetidos de cobro sobre el mismo boleto.
