# Fase 7: Juego Responsable (Límites de Recarga y Alertas)

Esta fase implementa los controles y validaciones para la protección del jugador de acuerdo a la Ley 31557 de Perú, fomentando el consumo saludable y la prevención de conductas nocivas mediante límites personalizables de depósitos, cooldowns de seguridad y autoexclusión de cuentas.

---

## 1. Características Implementadas

### A. Límites de Depósito Configurables
* **Períodos Soportados**: Diarios (24 horas), Semanales (7 días) y Mensuales (30 días).
* **Regla de Cooldown Preventivo (24 horas)**:
  * Las **reducciones** de límites o imposiciones iniciales se aplican al instante (de forma restrictiva).
  * Los **incrementos** o las **desactivaciones** (eliminar un límite) se registran como solicitudes pendientes y se activa un período de cooldown preventivo de 24 horas. Sigue rigiendo el límite anterior durante este período.

### B. Autoexclusión Temporal y Permanente
* **Temporal**: El usuario puede suspender su propia cuenta por un período de **7**, **30** o **90 días**.
* **Permanente**: Exclusión definitiva e indefinida.
* **Bloqueo Total**: Un usuario autoexcluido tiene totalmente bloqueadas las capacidades de depositar saldo y colocar apuestas.
* **Reactivación**: Las autoexclusiones temporales se rehabilitan de manera totalmente automática y transparente cuando expira el período temporal de suspensión.

### C. Descargo de Consumo Responsable (Disclaimer)
* Se incluye de forma obligatoria en la serialización y respuesta de cualquier ticket de apuestas (`Bet`):
  `"Juego responsable: El juego de apuestas en exceso puede causar adicción. Juega con moderación. Plataforma de simulación educativa."`

---

## 2. Decisiones de Arquitectura

1. **Cómputo en Tiempo Real**: Los límites de recarga se comprueban acumulando en tiempo real las operaciones `LedgerEntry` del tipo `Recarga` en los últimos $N$ días, previniendo cualquier desvío de balances.
2. **Restauración Transparente y Pasiva**: La expiración de autoexclusiones temporales se evalúa al vuelo en las peticiones síncronas del perfil (`MiPerfilView`), el depósito (`DepositoView`) y la colocación de apuestas (`BetSerializer`). Si ha expirado, el sistema restaura el estado a `verified` de manera transparente y atómica.
3. **Sweeper de Celery (Beat)**: Se configuró una tarea periódica por lotes (`apply_expired_limits`) ejecutada cada hora en segundo plano para barrer y consolidar los límites de depósito preventivos cuyo cooldown ya haya expirado.

---

## 3. Estructura de Base de Datos (Modelos)

### Modelo `ResponsibleGamingLimit`
* `user`: Relación `OneToOneField` con `User`.
* `daily_limit` / `weekly_limit` / `monthly_limit`: Límites de depósito activos.
* `pending_daily_limit` / `pending_weekly_limit` / `pending_monthly_limit`: Límites configurados preventivos en espera.
* `cooldown_until_daily` / `cooldown_until_weekly` / `cooldown_until_monthly`: Fecha y hora de expiración del cooldown de 24h.

### Modelo `AutoExclusion`
* `user`: Relación `OneToOneField` con `User`.
* `excluded_until`: Marca de tiempo límite para autoexclusión temporal (nulo para permanente).

---

## 4. Cobertura de Pruebas Automatizadas

La suite de pruebas automatizadas en `apps/responsible/tests.py` alcanza una cobertura de **91%**, validando con éxito los siguientes escenarios:
1. **Reducción de límites**: Verifica que la reducción de un límite se aplique de forma instantánea.
2. **Cooldown preventivo**: Valida que un aumento de límites quede en espera de 24h y no surta efecto de forma prematura.
3. **Rechazo de depósito**: Verifica que `DepositoView` rechace transferencias que superen los límites configurados.
4. **Autoexclusión bloqueante**: Comprueba que la autoexclusión bloquee con seguridad apuestas y recargas de saldo.
5. **Rehabilitación dinámica**: Confirma que el estado se restaure al instante cuando vence una autoexclusión temporal.
6. **Sweeper de Celery**: Verifica que la tarea `apply_expired_limits` procese de forma segura los cooldowns vencidos.
