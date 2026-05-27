# ADR 0006: Política de Re-Cotización de Cuotas en Tiempo Real

## Estado
Aprobado

## Fecha
26 de mayo de 2026

## Autor
Antigravity (Asistente de Desarrollo)

---

## Contexto

En una plataforma de apuestas deportivas en vivo como **FairBet Lab**, las cuotas (odds) cambian constantemente en tiempo real según el desarrollo del juego (goles, tarjetas, ataques de peligro, tiempo restante). 

Cuando un usuario decide realizar una apuesta, existe un desfase temporal inevitable (latencia de red, tiempo de reflexión en la interfaz) entre el momento en el que el usuario visualiza una cuota y hace clic en "Añadir al Ticket", y el momento en el que el backend procesa la solicitud HTTP POST para confirmar la apuesta.

Si la cuota de la selección cambia durante este intervalo de tiempo, debemos contar con una política rigurosa para evitar:
1. Pérdidas matemáticas injustificadas para el operador (la casa) si la cuota sube.
2. Frustración o perjuicios para el apostador (usuario) si la cuota baja sin su consentimiento.
3. Inconsistencia financiera en el Ledger (libro contable).

---

## Opciones Consideradas

### Opción 1: Aceptar automáticamente cualquier cambio de cuota
El backend acepta la apuesta al valor de la cuota vigente en la base de datos en el momento exacto del procesamiento del request, independientemente de lo que vio el usuario en su pantalla.
* **Pros**:
  - Implementación técnica simple (no requiere comparaciones complejas).
  - Tasa de éxito de colocación del 100%.
* **Contras**:
  - Pésima experiencia de usuario si el apostador ve que su cuota cambió de `2.50` a `1.80` sin su consentimiento.
  - Potenciales reclamos legales bajo normativas de protección al consumidor y directrices del MINCETUR.

### Opción 2: Cancelar o rechazar directamente la apuesta
Si la cuota enviada por el frontend no coincide con la cuota exacta guardada en el backend, la petición se rechaza con un código de error genérico. El usuario debe refrescar manualmente el catálogo e intentarlo de nuevo.
* **Pros**:
  - Totalmente seguro para las finanzas de la casa.
  - Implementación simple en el backend.
* **Contras**:
  - Frustración del usuario al ver que sus boletos son constantemente cancelados en eventos muy dinámicos (in-play).
  - Alta fricción que reduce la actividad en la plataforma.

### Opción 3: Validación síncrona con conflicto HTTP 409 y reconfirmación explícita (Elegida)
El backend procesa la apuesta síncronamente dentro de una transacción atómica bloqueando las filas correspondientes (`select_for_update`). Compara la cuota enviada en la solicitud HTTP (`odds_at_bet`) contra la cuota vigente en la base de datos:
1. Si son iguales (o la diferencia está dentro de un rango de tolerancia configurado, ej: `0.00`), la apuesta se acepta de inmediato.
2. Si la cuota difiere, el backend rechaza la transacción y retorna un error **`HTTP 409 Conflict`** con el payload que detalla la cuota anterior y la **nueva cuota actual**.
3. El frontend intercepta este `409` y muestra un cuadro de diálogo dinámico: *"La cuota de tu selección ha cambiado de X.XX a Y.YY. ¿Aceptas la nueva cuota?"*.
4. Si el usuario hace clic en "Aceptar", el frontend reenvía la apuesta síncronamente con la cuota actualizada.

* **Pros**:
  - Máxima transparencia para el usuario, que siempre sabe a qué cuota está apostando.
  - Protección absoluta para la casa contra abusos o arbitrajes debido a latencia.
  - Cumple perfectamente con los estándares de la Ley 31557.
* **Contras**:
  - Requiere lógica adicional tanto en el frontend como en el backend.

---

## Decisión

Se elige la **Opción 3 (Validación síncrona con conflicto HTTP 409 y reconfirmación explícita)**. 

La integridad financiera y la transparencia son los valores fundamentales de **FairBet Lab**. Toda apuesta colocada por el usuario debe contar con su consentimiento matemático inequívoco.

---

## Consecuencias

* **Facilidad**: 
  - La base de datos local siempre se mantendrá consistente con la voluntad del usuario.
  - Se previenen vulnerabilidades donde bots maliciosos envíen cuotas infladas artificialmente mediante requests directos de API.
* **Complejidad**:
  - Se debe registrar en el modelo `BetSelection` el campo `odds_at_bet` capturado al momento del guardado para auditoría inmutable.
  - En la Fase 4 (Apuestas), el backend implementará la comparación estricta de cuotas en `serializers.py` o `views.py`.
