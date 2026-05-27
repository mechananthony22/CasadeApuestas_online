# Fase 8: Auditoría Inmutable (Cadena de Hash)

Esta fase implementa la bitácora de auditoría inmutable regulada para garantizar el cumplimiento normativo exigido por el Artículo 18 de la Ley 31557 de Perú, utilizando una estructura criptográfica encadenada (tipo Blockchain básico) que impide de forma absoluta la alteración o el borrado malicioso de los registros históricos del simulador.

---

## 1. Características Implementadas

### A. Estructura Criptográfica de Auditoría
* **Modelo `AuditLogEntry`**:
  * Registra las acciones transaccionales clave con campos `event_type`, `payload` (detalles en formato JSON), `previous_hash` y `current_hash`.
  * **Encadenamiento Hash**: Cada bloque se vincula con el anterior de manera indisoluble calculando:
    $$\text{hash}_n = \text{SHA256}(\text{hash}_{n-1} + \text{dumps}(\text{payload}_n, \text{sort\_keys=True}))$$
    *(La serialización en JSON canónico garantiza que el orden de las claves siempre sea idéntico en el hashing).*
  * **Génesis de la Cadena**: El primer log de auditoría utiliza un hash inicial por defecto (`'0' * 64`).

### B. Inmutabilidad en Base de Datos (Append-Only)
* **Bloqueo a Nivel de Código**:
  * Se sobrescribió el método `save()` para lanzar un error de validación (`ValidationError`) si se intenta actualizar un registro ya creado (donde `self.pk is not None`).
  * Se sobrescribió el método `delete()` para denegar y lanzar un error incondicional al intentar borrar cualquier registro de la bitácora.
  * Esto asegura que la base de datos sea puramente de tipo **append-only**.

### C. Interceptores de Auditoría Desacoplados (Señales de Django)
* **Movimientos Contables (`LedgerEntry`)**:
  * Captura de forma automática e inmediata cada débito/crédito en el Ledger de partida doble, registrando emisor, receptor, cuenta, monto, dirección y la clave única de transacción.
* **Ciclo de Vida de Apuestas (`Bet`)**:
  * Registra la colocación del boleto de apuestas y cualquier cambio de estado posterior (`accepted`, `won`, `lost`, `cancelled`, `cashout`).
* **Fluctuaciones de Cuotas (`Selection`)**:
  * Intercepta modificaciones al campo `odds` de las selecciones deportivas, comparando en `pre_save` y `post_save` para documentar la re-cotización en tiempo real.

### D. Endpoint de Verificación de Integridad Forense
* **Acceso Exclusivo**: `GET /api/v1/audit/verify/` restringido a usuarios administradores (`IsAdminUser`).
* **Algoritmo de Verificación**:
  * Barre de forma secuencial la tabla desde el ID inicial, recalculando en memoria el hash de cada registro encadenado con el anterior.
  * Si la cadena es 100% íntegra, retorna un reporte conforme con HTTP 200 OK y estado `'verified'`.
  * Si detecta cualquier alteración en el payload o en la firma de un bloque anterior, detiene el proceso y retorna HTTP 400 Bad Request con estado `'compromised'` indicando con exactitud el **ID del registro comprometido** para su rápida auditoría.

---

## 2. Archivos Creados y Modificados

### Nuevos Archivos
| Ruta del Archivo | Descripción |
|------------------|-------------|
| `backend/apps/audit/signals.py` | Implementación de interceptores `@receiver` para capturar de forma desacoplada las transacciones de las apps. |
| `backend/apps/audit/urls.py` | Enrutador de URLs para la ruta de verificación. |
| `backend/apps/audit/views.py` | Implementación de `AuditVerifyView` y del barrido de integridad forense. |
| `backend/apps/audit/tests.py` | Suite de pruebas unitarias e integración de auditoría. |
| `docs/documentofase8.md` | Documentación oficial de cierre de la Fase 8. |

### Archivos Modificados
| Ruta del Archivo | Cambios Realizados |
|------------------|--------------------|
| `backend/apps/audit/models.py` | Implementación del modelo criptográfico `AuditLogEntry`, método de cálculo SHA-256 canónico y protección inmutable. |
| `backend/apps/audit/apps.py` | Registro del import de `audit.signals` dentro del método `ready()`. |
| `backend/config/urls.py` | Registro de las rutas de auditoría bajo la ruta global `/api/v1/`. |

---

## 3. Cobertura de Pruebas Automatizadas

La suite de pruebas automatizadas en `apps/audit/tests.py` alcanza una cobertura del **93%**, validando con éxito los siguientes escenarios críticos de la fase:
1. **Auditoría de Wallet (`test_audit_log_created_on_wallet_movement`)**: Valida el registro automático al depositar saldo en la billetera virtual.
2. **Auditoría de Apuestas (`test_audit_log_created_on_bet_placement_and_settlement`)**: Valida la trazabilidad de colocación y posterior liquidación.
3. **Auditoría de Cuotas (`test_audit_log_created_on_odds_fluctuation`)**: Valida que las fluctuaciones de cuotas de selecciones en el catálogo queden debidamente registradas.
4. **Barrido de Integridad Conforme (`test_audit_verify_view_integrity_and_tampering_detection` - Parte 1)**: Confirma la aprobación de la bitácora cuando no ha sido alterada.
5. **Detección de Manipulación / Hack (`test_audit_verify_view_integrity_and_tampering_detection` - Parte 2)**: Simula un ataque cibernético saltándose el ORM (vía consulta SQL directa `QuerySet.update()`) para manipular un payload e incrementar el saldo de forma artificial. Confirma que la API de verificación detecta inmediatamente el fraude, rechaza la solicitud e indica el ID comprometido.
6. **Bloqueo Append-Only (`test_audit_log_entry_blocks_manual_updates_and_deletions`)**: Verifica que cualquier intento de actualizar o borrar una entrada lance un error controlado.
