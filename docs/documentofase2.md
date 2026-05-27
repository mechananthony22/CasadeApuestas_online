# Documento de Fase 2: Wallet + Partida Doble

## Fecha
26 de mayo de 2026

---

## Archivos Creados/Modificados

### Nuevos
| Archivo | Descripción |
|---------|-------------|
| `backend/apps/wallet/__init__.py` | Inicializador del paquete wallet |
| `backend/apps/wallet/apps.py` | Configuración de la aplicación Django |
| `backend/apps/wallet/models.py` | Modelo `LedgerEntry` con partida doble |
| `backend/apps/wallet/serializers.py` | Serializers: `DepositoSerializer`, `RetiroSerializer`, `BalanceSerializer`, `LedgerEntrySerializer` |
| `backend/apps/wallet/views.py` | Vistas: `DepositoView`, `RetiroView`, `BalanceView`, `HistorialView` |
| `backend/apps/wallet/urls.py` | Rutas de la API para wallet |
| `backend/apps/wallet/admin.py` | Configuración del admin para `LedgerEntry` (solo lectura) |
| `backend/apps/wallet/tests.py` | Tests unitarios, de integración, property-based (Hypothesis) y de concurrencia |
| `backend/apps/wallet/migrations/0001_initial.py` | Migración inicial del modelo `LedgerEntry` |
| `docs/adr/0003-partida-doble-vs-saldo-almacenado.md` | ADR #3: Partida doble vs saldo almacenado |
| `docs/adr/0004-decimal-con-4-decimales-vs-float.md` | ADR #4: Decimal(18,4) vs float |
| `docs/adr/0005-select-for-update-vs-locking-optimista.md` | ADR #5: select_for_update vs locking optimista |

### Modificados
| Archivo | Cambio |
|---------|--------|
| `backend/config/urls.py` | Se agregó `path('api/v1/', include('wallet.urls'))` |

---

## Modelos

### `LedgerEntry`

El corazón de la contabilidad de partida doble. Representa un movimiento individual en el libro contable.

**Campos:**
- `user` (FK → User, nullable) — Usuario asociado al movimiento
- `account` (CharField) — Cuenta contable: `wallet_usuario`, `casa`, `apuestas_pendientes`, `bonos`
- `amount` (DecimalField, max_digits=18, decimal_places=4) — Monto del movimiento
- `direction` (CharField) — `DEBIT` (salida) o `CREDIT` (entrada)
- `transaction_id` (UUIDField, db_index) — UUID que agrupa débito y crédito de una misma operación
- `description` (CharField, opcional) — Motivo legible del movimiento
- `created_at` (DateTimeField, auto_now_add) — Marca de tiempo inmutable

**Reglas de negocio:**
1. NUNCA almacenar saldo — calcular siempre mediante `SUM(credits) - SUM(debits)`
2. Cada transacción = mínimo 2 entries balanceadas (suma algebraica = 0)
3. `select_for_update` en TODA operación de wallet
4. `@transaction.atomic` en toda operación que modifica el wallet

**Métodos de clase:**
- `get_user_balance(user)` → Saldo disponible del usuario
- `get_house_balance()` → Saldo de la cuenta de la casa
- `get_pending_bets_balance()` → Fondos retenidos en apuestas pendientes
- `get_system_zero_invariant()` → Verifica que suma total del sistema = 0

---

## Endpoints de API

| Método | Endpoint | Descripción | Códigos HTTP |
|--------|----------|-------------|--------------|
| POST | `/api/v1/wallet/deposit/` | Recarga simulada de fichas | 201, 400 |
| POST | `/api/v1/wallet/withdraw/` | Retiro simulado de fichas | 200, 400, 409 |
| GET | `/api/v1/wallet/balance/` | Saldo calculado por SUM | 200 |
| GET | `/api/v1/wallet/history/` | Historial de movimientos (paginado) | 200 |

---

## Tests Implementados

### Unitarios (modelo)
- Saldo inicial cero
- Depósito incrementa balance
- Retiro decrementa balance
- Transaction UUID agrupa entries

### Invariantes
1. **Suma por transacción = 0**: Débito y crédito siempre balanceados
2. **Saldo no negativo**: Ningún usuario puede tener saldo negativo
3. **Sistema constante**: Suma de todas las cuentas = 0

### Property-Based (Hypothesis)
- Depósitos aleatorios: invariante del sistema se mantiene
- Montos aleatorios: saldo del usuario nunca negativo
- Stateful: secuencias de depósitos/retiros verifican invariantes en cada paso

### Concurrencia
- Múltiples retiros simultáneos con saldo justo para 1
- Verifica que solo 1 pasa y saldo nunca negativo

### Integración (HTTP)
- Depósito exitoso → 201
- Depósito monto 0/negativo → 400
- Depósito sin auth → 403
- Retiro exitoso → 200
- Retiro saldo insuficiente → 409
- Balance inicial = 0.0000
- Balance incluye username

---

## ADRs Creados

| # | Título | Decisión |
|---|--------|----------|
| 3 | Partida doble vs saldo almacenado | **Partida doble con LedgerEntry** — saldo calculado por SUM |
| 4 | Decimal(18,4) vs float | **DecimalField** — precisión exacta para montos financieros |
| 5 | select_for_update vs locking optimista | **select_for_update** — bloqueo pesimista contra doble gasto |

---

## Comandos de Verificación

```bash
# 1. Construir y levantar contenedores
docker-compose build
docker-compose up -d

# 2. Ejecutar migraciones
docker-compose exec backend python manage.py migrate

# 3. Ejecutar tests de wallet
docker-compose exec backend pytest apps/wallet/tests.py -v

# 4. Verificar cobertura
docker-compose exec backend pytest apps/wallet/tests.py --cov=apps/wallet --cov-report=term

# 5. Probar endpoints manualmente
# Depósito
curl -X POST http://localhost:8000/api/v1/wallet/deposit/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'usuario:contraseña' | base64)" \
  -d '{"amount": "1000.0000"}'

# Balance
curl http://localhost:8000/api/v1/wallet/balance/ \
  -H "Authorization: Basic $(echo -n 'usuario:contraseña' | base64)'

# Retiro
curl -X POST http://localhost:8000/api/v1/wallet/withdraw/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'usuario:contraseña' | base64)" \
  -d '{"amount": "500.0000"}'
```
