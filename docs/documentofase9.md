# Fase 9: Anti-fraude Básico (Alertas de Comportamiento Sospechoso)

Esta fase implementa el motor automatizado de detección de comportamiento sospechoso y anti-fraude en tiempo real de acuerdo al Nivel 3 de las especificaciones y la Ley 31557 de Perú, con el fin de resguardar la integridad financiera del simulador y prevenir abusos como multicuenta, lavado de activos virtual y apuestas coordinadas (sindicalización/amaño).

---

## 1. Características Implementadas

### A. Reglas Heurísticas de Anti-fraude
El motor de anti-fraude (`FraudDetector`) analiza en tiempo real cada transacción contable y colocación/cierre de apuestas aplicando tres reglas críticas de riesgo:
1. **Detección de Multicuenta (`MULTIPLE_ACCOUNTS_SAME_IP`)**:
   * Intercepta la dirección IP de origen (`REMOTE_ADDR` o `HTTP_X_FORWARDED_FOR`) en depósitos y colocación de apuestas.
   * Si una misma IP es compartida por **más de 3 cuentas distintas**, se genera automáticamente una alerta de severidad media `PENDING` para auditoría administrativa.
2. **Lavado de Activos Virtual (`IMMEDIATE_DEPOSIT_CASHOUT`)**:
   * Si un usuario solicita el cobro anticipado (*Cash-out*) de cualquier boleto de apuestas dentro de los **15 minutos** posteriores a realizar un depósito (`Recarga`), se genera una alerta de severidad alta `PENDING`.
3. **Sindicalización / Amaños de Apuestas (`IDENTICAL_BET_PATTERN`)**:
   * Si **3 o más usuarios diferentes** colocan una apuesta con el mismo stake exacto y sobre las mismas selecciones en una ventana de **5 minutos**, se genera una alerta de severidad alta `PENDING` detallando la lista completa de cuentas involucradas en el sindicato.

### B. Gestión y Resolución de Alertas Administrativas
* **Modelo `SuspiciousActivity`**:
  * Consolda todas las alertas gatilladas con su tipo de actividad, payload (detalles forenses JSON), severidad (`LOW`, `MEDIUM`, `HIGH`) y estado (`PENDING`, `REVIEWED`, `DISMISSED`).
* **Endpoint de Gestión RESTful**:
  * `GET /api/v1/fraud/alerts/`: Lista todas las alertas ordenadas por fecha (solo accesible para administradores mediante `IsAdminUser`).
  * `POST /api/v1/fraud/alerts/{id}/resolve/`: Permite a un operador administrativo auditar y archivar una alerta sospechosa, cambiando su estado a `'REVIEWED'` o `'DISMISSED'`, registrando la marca de tiempo `resolved_at` y el operador `resolved_by` responsable de la auditoría forense.

---

## 2. Archivos Creados y Modificados

### Nuevos Archivos
| Ruta del Archivo | Descripción |
|------------------|-------------|
| `backend/apps/fraud/services.py` | Implementación del motor heurístico central `FraudDetector`. |
| `backend/apps/fraud/serializers.py` | Serializador de alertas `SuspiciousActivitySerializer`. |
| `backend/apps/fraud/urls.py` | Enrutamiento de la API de alertas mediante enrutadores DRF. |
| `backend/apps/fraud/views.py` | Implementación del ViewSet administrativo `SuspiciousActivityViewSet`. |
| `backend/apps/fraud/tests.py` | Suite completa de pruebas unitarias e integración de anti-fraude. |
| `docs/documentofase9.md` | Documentación oficial de finalización de la Fase 9. |

### Archivos Modificados
| Ruta del Archivo | Cambios Realizados |
|------------------|--------------------|
| `backend/apps/fraud/models.py` | Definición de los modelos `UserIpLog` y `SuspiciousActivity` con severidades y estados de revisión. |
| `backend/apps/wallet/views.py` | Interceptación de IP remoto en `DepositoView.post` para registro de multicuenta. |
| `backend/apps/betting/views.py` | Interceptación de IP en `BetViewSet.create` y validación de reglas de sindicalización y cash-out rápido en `BetViewSet.cashout`. |
| `backend/config/urls.py` | Registro del enrutador de la aplicación `fraud` bajo la API `/api/v1/`. |

---

## 3. Cobertura de Pruebas Automatizadas

La suite de pruebas en `apps/fraud/tests.py` alcanza una cobertura del **98%**, validando con éxito los siguientes escenarios críticos:
1. **Detección de Multicuenta (`test_rule_1_multiple_accounts_same_ip`)**: Valida que al depositar desde la misma IP con 4 cuentas distintas, se levante la alerta correctamente.
2. **Cash-out apresurado (`test_rule_2_deposit_followed_by_immediate_cashout`)**: Comprueba que al recargar y hacer cash-out en menos de 15 minutos, se genere la alerta de lavado de activos.
3. **Amaño coordinado (`test_rule_3_syndicated_identical_betting`)**: Verifica que al realizar 3 apuestas idénticas por diferentes usuarios en menos de 5 minutos, se levante la alerta de sindicalización grupal.
4. **Auditoría del Operador (`test_admin_alerts_list_and_resolve`)**: Confirma la seguridad y los permisos de acceso administrativo (`IsAdminUser`), el listado correcto de alertas, y la resolución transaccional de las mismas.
