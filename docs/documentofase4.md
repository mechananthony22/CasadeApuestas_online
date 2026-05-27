# Documento de Fase 4: Apuestas + Idempotencia

## Fecha
26 de mayo de 2026

---

## Archivos Creados/Modificados

### Nuevos
| Archivo | Descripción |
|---------|-------------|
| `backend/apps/betting/migrations/0002_bet_betselection.py` | Migración para los modelos `Bet` y `BetSelection` |
| `docs/adr/0007-maquina-estados-bet.md` | ADR #7: Ciclo de vida y transiciones de la máquina de estados de apuesta |
| `docs/adr/0008-estrategia-idempotencia.md` | ADR #8: Control híbrido de idempotencia en Redis y PostgreSQL |
| `docs/documentofase4.md` | Documentación oficial de finalización de la Fase 4 |

### Modificados
| Archivo | Cambio |
|---------|--------|
| `backend/apps/betting/models.py` | Definición de los modelos relacionales de apuestas: `Bet` y `BetSelection`. |
| `backend/apps/betting/serializers.py` | Definición de `BetSerializer`, `BetSelectionPostSerializer`, `BetSelectionDetailSerializer` y la excepción de API `OddsChangedException`. |
| `backend/apps/betting/views.py` | Implementación del controlador `BetViewSet` con control de concurrencia (`select_for_update`) e idempotencia en Redis. |
| `backend/apps/betting/urls.py` | Registro del endpoint de apuestas `/api/v1/betting/bets/`. |
| `backend/apps/betting/tests.py` | Incorporación de la suite de pruebas síncronas, re-cotización, idempotencia en caché, bloqueos KYC y concurrencia multi-hilo de doble gasto. |

---

## Modelos Creados

### `Bet`
Representa el ticket o boleto de apuesta colocado por un apostador.
- `user` (FK -> User): Apostador que generó el boleto.
- `status` (CharField): `accepted` (Aceptada), `won` (Ganada), `lost` (Perdida), `cancelled` (Cancelada), `cashed_out` (Cobro Anticipado).
- `type` (CharField): `simple` (Simple) o `accumulator` (Combinada).
- `stake` (DecimalField, max_digits=18, decimal_places=4): Monto de fichas virtuales apostado.
- `potential_payout` (DecimalField, max_digits=18, decimal_places=4): Ganancia potencial calculada en base a las cuotas capturadas.
- `idempotency_key` (UUIDField, unique, db_index=True): Clave UUID única de transacción.
- `created_at` (DateTimeField): Fecha y hora de colocación.
- `settled_at` (DateTimeField, nullable): Fecha y hora de resolución del ticket.

### `BetSelection`
Relación intermedia que vincula el boleto de apuesta con sus cuotas seleccionadas, congelando históricamente la cuota al momento exacto de apostar.
- `bet` (FK -> Bet): Boleto contenedor.
- `selection` (FK -> Selection): Selección deportiva específica elegida.
- `odds_at_bet` (DecimalField, max_digits=10, decimal_places=4): Cuota decimal inmutable en el instante del guardado.
- `status` (CharField): `pending` (Pendiente), `won` (Ganada), `lost` (Perdida), `void` (Anulada).

---

## Endpoints de la API REST

Los endpoints de apuestas son de **escritura transaccional y lectura paginada** con autenticación obligatoria:

| Método | Endpoint | Cabecera Obligatoria | Descripción | Código HTTP |
|--------|----------|----------------------|-------------|-------------|
| POST | `/api/v1/betting/bets/` | `Idempotency-Key: <UUID>` | Coloca síncronamente una apuesta (simple o combinada), realizando validaciones de KYC, cuotas reales, fondos, y ejecutando partida doble contable. | 201, 400, 409 |
| GET | `/api/v1/betting/bets/` | Ninguna | Lista de forma paginada y segura los boletos de apuestas colocados por el usuario autenticado. | 200, 403 |
| GET | `/api/v1/betting/bets/{id}/` | Ninguna | Consulta detallada y anidada de un boleto específico del usuario. | 200, 403, 404 |

---

## Suite de Pruebas y Cobertura

Se implementó una suite con **100% de éxito y 90% de cobertura de código global** en `backend/apps/betting/tests.py`:

1. **Colocación Exitosa (`test_colocacion_apuesta_simple_exitosa`)**:
   - Valida el flujo exitoso por HTTP síncrono.
   - Verifica los débitos en `LedgerEntry` en partida doble: **DÉBITO** en `wallet_usuario` y **CRÉDITO** en `apuestas_pendientes` (suma neta = 0.0000).
2. **Rechazo por Falta de Idempotencia (`test_rechazo_apuesta_sin_cabecera_idempotencia`)**:
   - Rechaza solicitudes que no incluyan la cabecera `Idempotency-Key` con código `400 Bad Request`.
3. **Estrategia de Idempotencia en Redis (`test_estrategia_idempotencia_respuesta_cacheada`)**:
   - Envía dos solicitudes concurrentes con la misma `Idempotency-Key`.
   - Verifica que el segundo intento retorne inmediatamente la respuesta original cacheada, **sin crear duplicados en la base de datos** y **sin volver a debitar saldo**.
4. **Política de Re-Cotización (`test_politica_re_cotizacion_odds_cambiaron`)**:
   - Envía una apuesta con una cuota obsoleta.
   - Verifica que el backend rechace la colocación con código **`409 Conflict`** y un payload estructurado conteniendo las diferencias de cuota para reconfirmación.
5. **Bloqueo KYC de Juego Responsable (`test_bloqueo_juego_responsable_kyc_no_verificado`)**:
   - Bloquea intentos de apuesta de usuarios con estado KYC pendiente o excluido (`400 Bad Request`).
6. **Prevención de Doble Gasto / Concurrencia (`test_prevencion_doble_gasto_concurrencia_hilos`)**:
   - Simula mediante **hilos en paralelo** (`ThreadPoolExecutor`) 3 peticiones de apuestas simultáneas de 80 fichas cada una, teniendo el usuario sólo 100 fichas de saldo disponible.
   - Gracias a `select_for_update` transaccional, valida que **únicamente pase una apuesta (201 Created)** y **las otras dos sean rechazadas de forma segura (409 Conflict)**, asegurando que el saldo final quede exactamente en 20 fichas sin generar sobregiros.

---

## Comandos de Verificación con Docker

```bash
# 1. Reconstruir imágenes tras cambios de base.py
docker-compose build

# 2. Levantar el stack completo (Base de Datos, Redis, Backend, Celery)
docker-compose up -d

# 3. Aplicar las migraciones de apuestas en la base de datos PostgreSQL
docker-compose exec backend python manage.py migrate

# 4. Correr la suite completa de pruebas unitarias, integración y concurrencia
docker-compose exec backend pytest apps/betting/tests.py -v

# 5. Medir la cobertura de código (debe superar el 80% obligatorio)
docker-compose exec backend pytest apps/betting/tests.py --cov=apps/betting --cov-report=term
```
