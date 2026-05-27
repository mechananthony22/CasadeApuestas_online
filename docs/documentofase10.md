# Fase 10: Dashboard del Operador y Reporte MINCETUR

Esta fase implementa el panel operativo de control (Dashboard) y el sistema de reportes regulatorios mensuales en formato CSV del proyecto **FairBet Lab**, en cumplimiento estricto con los estándares de la **Ley 31557** de Perú y su reglamento **DS 005-2023-MINCETUR**.

---

## 1. Características Implementadas

### A. Métricas Operativas en Vivo (Dashboard)
El endpoint `GET /api/v1/dashboard/metrics/` expone las métricas críticas del simulador consolidadas en tiempo real:
* **GGR (Gross Gaming Revenue)**:
  Se calcula de forma dinámica agregando sobre los registros resueltos de la tabla `Bet`:
  $$\text{GGR} = \sum (\text{Monto Apostado}) - \sum (\text{Premios Pagados})$$
  * Las apuestas **perdidas** aportan positivamente al GGR (retorno = 0).
  * Las apuestas **ganadas** o con **cobro anticipado (Cash-out)** restan del GGR en función del premio real pagado al usuario.
  * Las apuestas **canceladas/anuladas** tienen impacto neutro (retorno = stake, GGR nulo).
  * Las apuestas **abiertas** (`accepted`) se omiten del cálculo de GGR hasta su liquidación.
* **Volumen de Apuestas**:
  * Cantidad y montos totales históricos.
  * Cantidad y montos de apuestas activas en custodia.
  * Cantidad y montos de apuestas colocadas en las últimas 24 horas.
* **Usuarios Activos**:
  Determina usuarios únicos con actividad física o lógica en ventanas de tiempo de **24 horas**, **7 días** y **30 días**, evaluando interacciones combinadas de inicio de sesión (`last_login`), colocación de apuestas (`created_at` en `Bet`) y transacciones contables (`created_at` en `LedgerEntry`).

### B. Análisis de Exposición y Riesgo por Evento (Exposure)
Calcula en tiempo real para todos los eventos activos (`scheduled` o `in_play`) la exposición y riesgo financiero potencial por cada opción de mercado en caso de resultar ganadora:
* **Fórmula de Exposición Neta**:
  $$\text{Net Exposure}_S = \text{Payout Potencial}_S - \sum \text{Stakes Totales del Mercado}$$
* Le permite al operador monitorear en tiempo real el desbalance de cuotas o concentración de stakes para anticipar pérdidas potenciales netas de la casa de apuestas.

### C. Reporte Mensual Regulatorio MINCETUR
El endpoint `GET /api/v1/dashboard/mincetur-report/` genera un archivo CSV descargable estructurado para auditorías de cumplimiento:
* Filtra las apuestas liquidadas (`settled_at`) dentro del año y mes indicados.
* Contiene datos de **KYC del jugador** (DNI, nombre de usuario) cruzados de forma atómica para cumplir las normas de verificación de identidad.
* Expone información detallada de cada ticket: ID de ticket, fecha de colocación, fecha de resolución, tipo (Simple/Combinada), mercados/selecciones jugadas, cuota final, monto apostado, estado final, premio neto acreditado y el GGR exacto aportado por la transacción en la moneda del sistema ("Fichas Virtuales").
* Incorpora el **BOM de UTF-8** para asegurar la compatibilidad y correcta visualización de caracteres especiales en Microsoft Excel en Windows.

---

## 2. Decisiones de Arquitectura e Integración

1. **Integración con la Arquitectura Existente**:
   No se crearon nuevos modelos redundantes en base de datos. En su lugar, el sistema consulta de forma atómica e indexada los modelos base `Bet`, `BetSelection`, `User`, `UserProfile` y `LedgerEntry` para evitar desvíos e inconsistencias financieras de balances y estados.
2. **Seguridad y Privilegios**:
   Todos los endpoints de métricas y exportación están restringidos estrictamente para uso exclusivo de administradores/operadores del sistema mediante la clase de permisos `IsAdminUser` de Django REST Framework.
3. **Cálculo Optimizado con Django ORM**:
   Los cálculos agregados (como sumas condicionales para determinar retornos pagados) se ejecutan mediante agregaciones y anotaciones a nivel de base de datos (`Sum`, `Case`, `When`) reduciendo drásticamente el consumo de memoria RAM del servidor web.

---

## 3. Estructura de Endpoints de la API

* **`GET /api/v1/dashboard/metrics/`**:
  * **Permisos**: Requiere autenticación de usuario administrador.
  * **Respuesta**: JSON con el disclaimer legal obligatorio, valor consolidado de GGR, stakes, payouts, volumen de apuestas segmentado, conteo de usuarios activos y el listado de exposición detallado de todos los eventos deportivos activos en vivo o programados.
* **`GET /api/v1/dashboard/mincetur-report/?year=YYYY&month=MM`**:
  * **Permisos**: Requiere autenticación de usuario administrador.
  * **Parámetros**: `year` (opcional, entero) y `month` (opcional, entero). Si no se proveen, se calculan automáticamente para el mes actual.
  * **Respuesta**: Archivo CSV adjunto (`reporte_mincetur_YYYY_MM.csv`) descargable.

---

## 4. Cobertura de Pruebas Automatizadas

La suite de pruebas automatizadas en `apps/dashboard/tests.py` alcanza una cobertura global del **97%** en la aplicación `dashboard` y un **93%** en `apps/dashboard/views.py`, validando con absoluto éxito todos los escenarios de negocio críticos:
1. **Control de Accesos**: Confirma el rechazo `403 Forbidden` a usuarios no autorizados y el acceso correcto de administradores.
2. **Métricas de GGR**: Valida la suma matemática precisa de stakes y payouts considerando apuestas ganadas, perdidas, cash-out, canceladas y abiertas de forma independiente.
3. **Cálculo de Exposición por Evento**: Comprueba el cálculo correcto de `net_exposure` y `gross_exposure` para selecciones con stakes o vacías.
4. **Generación del Reporte CSV de MINCETUR**: Verifica la estructura de encabezados regulatorios del archivo, el filtrado temporal por mes exacto de liquidación, el formato de descarga y la integridad de los datos cruzados del perfil de usuario (DNI).

### Reporte final de pytest con Cobertura:
```text
Name                         Stmts   Miss  Cover
------------------------------------------------
apps\dashboard\__init__.py       0      0   100%
apps\dashboard\apps.py           4      0   100%
apps\dashboard\models.py         1      0   100%
apps\dashboard\tests.py        135      0   100%
apps\dashboard\urls.py           3      0   100%
apps\dashboard\views.py         97      7    93%
------------------------------------------------
TOTAL                          240      7    97%
```
