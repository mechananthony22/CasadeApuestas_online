# Reporte de Cumplimiento Normativo (Compliance) y Autocrítica - Ley 31557

Este documento expone detalladamente el diseño arquitectónico y de seguridad de la plataforma educativa **FairBet Lab**, justificando cómo garantiza la integridad financiera de las transacciones, la protección al jugador y el alineamiento técnico con la **Ley 31557** de Perú y su reglamento **DS 005-2023-MINCETUR**.

---

## 1. Integridad Financiera y Contabilidad de Partida Doble

Para asegurar la infalibilidad y evitar cualquier desvío de balances o alteración de fondos de los usuarios, **FairBet Lab** implementa un motor contable rígido basado en el estándar de **Partida Doble**:

### A. Saldo Derivado y Balance Inmutable
* **Inexistencia de Saldo Almacenado**: No existe ninguna columna `saldo` o `balance` en la base de datos que se pueda modificar de forma directa con un SQL `UPDATE` simple. El saldo de cualquier cuenta se calcula estrictamente sumando todas las transacciones históricas registradas en el modelo `LedgerEntry`:
  $$\text{Balance} = \sum (\text{Créditos}) - \sum (\text{Débitos})$$
* **Transacciones Balanceadas**: Cada operación financiera (recarga, colocación de apuesta, liquidación de premios, cash-out) genera obligatoriamente como mínimo dos registros contables indexados bajo un mismo identificador de transacción (`transaction_id`). La suma algebraica de los montos de una misma transacción es exactamente **cero**, garantizando la inalterabilidad global del sistema.

### B. Concurrencia y Bloqueo Pesimista
* **select_for_update**: Toda mutación en la billetera virtual ejecuta una transacción atómica protegida con bloqueo pesimista en base de datos. Se bloquean las filas del usuario (`User.objects.select_for_update()`) durante la colocación de apuestas, depósitos o liquidaciones. Esto previene de forma absoluta condiciones de carrera y ataques de **doble gasto** bajo peticiones masivas y concurrentes.

---

## 2. Decisiones de Diseño y Controles de Juego Responsable

En concordancia con el artículo 12 de la Ley 31557 de protección al jugador, el simulador impone restricciones lógicas ineludibles:

### A. Límites de Depósito Configurables
* **Períodos Soportados**: Diarios (24 horas), Semanales (7 días) y Mensuales (30 días).
* **Regla de Cooldown Preventivo (24 horas)**:
  * Las **reducciones** de límites (más restrictivos) se aplican de forma inmediata.
  * Los **incrementos** o las solicitudes para **eliminar** un límite quedan en estado pendiente y se les aplica un temporizador preventivo de 24 horas. El usuario sigue operando bajo su límite anterior y más restrictivo durante el cooldown. Una tarea de Celery consolidará los límites cuando expire el cooldown.

### B. Autoexclusión Temporal y Permanente
* **Temporal (7, 30 o 90 días)** o **Permanente (Indefinida)**.
* **Bloqueo Total**: Un usuario autoexcluido tiene totalmente bloqueadas las capacidades de depositar saldo y colocar apuestas.
* **Reactivación Automática**: Las autoexclusiones temporales se rehabilitan al vuelo de forma transparente cuando expira el período de suspensión, restaurando el perfil a `'verified'`.

---

## 3. Matriz de Cumplimiento - Ley 31557 y Reglamento MINCETUR

A continuación se presenta un análisis honesto de qué requisitos de la normativa peruana están cubiertos por el simulador y cuáles representan exclusiones debidas a su naturaleza educativa:

| Requisito Regulatorio | Implementación en FairBet Lab | Estado |
| :--- | :--- | :--- |
| **Validación de Identidad y Mayoría de Edad (Art. 8)** | Verificación local de mayoría de edad (DNI peruano de 8 dígitos validado mediante el algoritmo Módulo-11 de dígito verificador). | **CUBIERTO (Local)** |
| **Límites de Juego Responsable (Art. 12)** | Límites diarios, semanales y mensuales de depósito con cooldown preventivo de 24 horas e imposición inmediata de límites restrictivos. | **CUBIERTO** |
| **Autoexclusión (Art. 12)** | Autoexclusión atómica (temporal o indefinida) que inhabilita síncronamente apuestas y depósitos. | **CUBIERTO** |
| **Auditoría y Trazabilidad (Art. 15)** | Registro inmutable de transacciones, apuestas, cambios de límites y cuotas mediante una bitácora encadenada por hashes SHA-256 (`AuditLogEntry`). | **CUBIERTO** |
| **Monitoreo de Lavado de Activos** | Motor anti-fraude que detecta depósito inmediato seguido de cash-out (<15 min), multicuentas por IP y amaño sindicalizado. | **CUBIERTO** |
| **Dashboard y Reportes Regulatorios** | Panel administrador con GGR en vivo, exposición financiera por evento y reporte mensual exportable estilo MINCETUR (CSV). | **CUBIERTO** |
| **Validación Directa RENIEC** | No integrado con servicios reales del Estado. Se simula localmente la validación algorítmica del DNI. | *EXCLUIDO (Educativo)* |
| **Pasarelas de Pago Reales** | No se integran tarjetas ni pasarelas reales. Todo depósito/retiro es una recarga simulada sin valor real. | *EXCLUIDO (Educativo)* |

---

## 4. Justificación de la Arquitectura Híbrida

El sistema implementa una **Arquitectura Híbrida** para balancear fiabilidad matemática e interactividad ágil:

1. **Protocolo HTTP Síncrono (Operaciones Críticas)**:
   * **Por qué**: Colocar apuestas, solicitar cash-out, depositar fondos y modificar límites de juego responsable modifican directamente el balance financiero o el estado de juego del usuario. Estas operaciones requieren garantías **ACID** transaccionales estrictas y bloqueos de base de datos (`select_for_update`). Utilizar WebSockets para mutaciones contables introduce riesgos de pérdida de paquetes, procesamiento desordenado y condiciones de carrera.
2. **Protocolo WebSocket Asíncrono (Canales en Tiempo Real)**:
   * **Por qué**: Actualizar cuotas dinámicas (odds) de partidos en vivo, marcadores en tiempo real (goles), suspensiones transitorias y notificaciones de apuestas liquidadas son operaciones de **solo lectura** o notificaciones asíncronas ligeras. Utilizar HTTP para esto implicaría polling repetitivo, saturando innecesariamente la base de datos local. Los WebSockets permiten empujar estas actualizaciones instantáneamente a miles de clientes conectados con mínima latencia y sin bloqueos transaccionales.

---

## 5. Escalabilidad para Múltiples Ligas

Para llevar la plataforma a un nivel de producción masivo soportando cientos de ligas simultáneas:
* **Colas dedicadas de Celery**: Segmentar Celery en colas especializadas (`live_queue` para sincronización de marcadores y cuotas en vivo cada 10/30 segundos, y `prematch_queue` para fixtures futuros cada 2 horas).
* **Caching de Lecturas**: Almacenar las cuotas de lectura de todos los partidos activos en Redis para evitar consultas pesadas al PostgreSQL cuando miles de usuarios cargan el catálogo al mismo tiempo.
