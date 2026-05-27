# ADR 0011: Controles de Juego Responsable y Lógica de Cooldown de Límites

## Estado
Aprobado

## Fecha
27 de mayo de 2026

## Autor
Antigravity (Asistente de Desarrollo)

---

## Contexto

El *FairBet Lab*, conforme al artículo 12 de la Ley 31557 peruana y su reglamento DS 005-2023-MINCETUR, debe ofrecer medidas robustas para mitigar conductas de riesgo en los jugadores. Específicamente, el sistema debe proveer:
1. **Límites de Recargas configurables** (diarios, semanales, mensuales). Las solicitudes para reducir límites o establecerlos por primera vez deben ser de **ejecución inmediata**. Los aumentos o eliminaciones de límites deben requerir obligatoriamente un **cooldown preventivo de 24 horas**.
2. **Autoexclusiones temporales** (opciones de 7, 30 y 90 días) y **permanentes** (indefinidas).
3. **Bloqueo ineludible** de colocación de apuestas y depósitos síncronos mientras exista una autoexclusión activa.

---

## Opciones Consideradas

### Opción 1: Almacenar límites directamente en la cuenta de usuario sin historial
Mantener los límites actuales como simples columnas numéricas en `UserProfile`. Al cambiar de límite, se pisa el valor anterior de forma síncrona o mediante un timer simple.
* **Pros**: Simple y requiere menos modelos.
* **Contras**: Pérdida total de consistencia operativa. Si el usuario sube un límite, no hay manera de guardar el valor "pendiente" manteniendo el límite anterior "activo" durante las 24 horas del cooldown, lo cual viola la norma regulatoria de protección.

### Opción 2: Modelo independiente de Límites con estados activos y pendientes (Elegida)
Crear un modelo dedicado `ResponsibleGamingLimit` que contenga por cada usuario tanto sus límites **activos** (`daily_limit`, `weekly_limit`, `monthly_limit`) como sus valores **pendientes** (`pending_daily_limit`, etc.) y marcas de tiempo (`cooldown_until_daily`, etc.).
* **Pros**: 
  - Permite validar depósitos utilizando estrictamente los límites anteriores activos durante el período de cooldown.
  - Ofrece total consistencia transaccional y facilita auditorías de cumplimiento normativo.
  - Es resistente a reinicios de servidores, al estar el cooldown persistido de forma segura en base de datos.
* **Contras**: Requiere mayor planificación lógica en la actualización de estados.

---

## Decisión

Se adopta la **Opción 2 (Modelo independiente de Límites con estados activos y pendientes)** para garantizar la integridad y el cumplimiento regulatorio de protección al jugador.

### Algoritmo de Actualización de Límites:
- **Reducción de Límite**: Si el nuevo valor propuesto $X$ es inferior al valor activo actual $Y$ ($X < Y$), o si no había límite previo (estableciendo un límite por primera vez), se aplica de manera **inmediata** en la base de datos.
- **Incremento de Límite o Eliminación**: Si el nuevo valor $X > Y$ o se desea establecer a `None` (ilimitado), el valor se asigna a `pending_limit` y se calcula la fecha de liberación:
  $$\text{cooldown\_until} = \text{ahora} + 24\text{ horas}$$
  Durante este tiempo, se sigue validando contra el límite activo restrictivo $Y$.

---

## Consecuencias

* Se creará la aplicación `responsible` con los modelos `ResponsibleGamingLimit` y `AutoExclusion`.
* Se interceptará la recarga de saldo (`DepositoView`) y la colocación de apuestas (`BetCreateSerializer`) para forzar las validaciones ineludibles.
* Se agregará la tarea periódica `apply_expired_limits` en Celery para consolidar de forma automatizada los límites pendientes tras la expiración del cooldown, aunque también se implementará una consolidación dinámica en el API para asegurar máxima exactitud en tiempo real.
