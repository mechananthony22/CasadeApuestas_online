# FairBet Lab — Mapeo Funcionalidad → Código

## Nivel 1 — Núcleo obligatorio (55%)

### 1. Registro y KYC (Conoce tu cliente) simulado

**Cómo se usa:**

```
POST /api/v1/auth/register/
Body: { "username": "jugador1", "email": "j1@mail.com", "password": "Pass1234",
        "confirm_password": "Pass1234", "dni": "12345678", "birth_date": "2000-05-15" }
→ 201: usuario creado en estado pending_verification (o verified si auto-verificado)

POST /api/v1/auth/verify-dni/
Header: Authorization: Bearer <token>
Body: { "dni": "12345678" }
→ 200: cuenta pasa a estado verified

GET /api/v1/users/me/
Header: Authorization: Bearer <token>
→ 200: datos del perfil (estado, DNI, edad, is_able_to_bet)
```

El flujo es: el usuario se registra → el backend valida el DNI con algoritmo Módulo-11 (`validators.py:18`) y opcionalmente contra API PeruDev (`serializers.py:54`) → verifica mayoría de edad (`validators.py:35`) → crea User + UserProfile en una transacción atómica (`serializers.py:100`). El perfil tiene 4 estados posibles (`models.py:29-33`).

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Modelo `UserProfile` con estados | `backend/apps/users/models.py` | 15–119 |
| Validación DNI peruano (Módulo-11) | `backend/apps/users/validators.py` | 18–32 |
| Validación mayoría de edad (≥ 18) | `backend/apps/users/validators.py` | 35–41 |
| Endpoint `POST /api/v1/auth/register/` | `backend/apps/users/views.py` (RegistroView) | 17–53 |
| Endpoint `POST /api/v1/auth/verify-dni/` | `backend/apps/users/views.py` (VerificarDniView) | 56–102 |
| Endpoint `GET /api/v1/users/me/` | `backend/apps/users/views.py` (MiPerfilView) | 105–131 |
| Validación DNI contra API PeruDev | `backend/apps/users/serializers.py` | 54–82 |
| Rutas de users | `backend/apps/users/urls.py` | 1–22 |
| Registro atómico (User + UserProfile en una tx) | `backend/apps/users/serializers.py` | 100–131 |

### 2. Wallet con partida doble

**Cómo se usa:**

```
POST /api/v1/wallet/deposit/
Header: Authorization: Bearer <token>
Body: { "amount": 500.00 }
→ 201: CREDIT wallet_usuario + DEBIT casa (mismo transaction_id)

POST /api/v1/wallet/withdraw/
Header: Authorization: Bearer <token>
Body: { "amount": 100.00 }
→ 200: DEBIT wallet_usuario + CREDIT casa

POST /api/v1/wallet/transfer/
Header: Authorization: Bearer <token>, Idempotency-Key: <uuid>
Body: { "amount": 50.00, "receiver_username": "otro_user" }
→ 201: DEBIT sender + CREDIT receiver (mismo transaction_id)

GET /api/v1/wallet/balance/
Header: Authorization: Bearer <token>
→ 200: { "balance": "850.0000", "total_depositado": "1000.0000", ... }
```

El saldo **nunca se almacena** — siempre se calcula como `SUM(credits) − SUM(debits)` sobre `LedgerEntry` (`models.py:86-100`). La invariante del sistema (`models.py:133-143`) verifica que `total_credits − total_debits = 0` en todo el ledger. Cada operación financiera crea **mínimo 2 entradas** balanceadas. La transferencia usa `select_for_update` con orden ascendente de IDs para evitar deadlocks (`views.py:421-426`).

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Modelo `LedgerEntry` con `Account` y `Direction` | `backend/apps/wallet/models.py` | 7–84 |
| Saldo calculado (nunca almacenado) | `backend/apps/wallet/models.py` | 86–100 |
| Invariante de sistema (suma total = 0) | `backend/apps/wallet/models.py` | 133–143 |
| `POST /api/v1/wallet/deposit/` | `backend/apps/wallet/views.py` (DepositoView) | 24–211 |
| `POST /api/v1/wallet/withdraw/` | `backend/apps/wallet/views.py` (RetiroView) | 214–293 |
| `POST /api/v1/wallet/transfer/` + Idempotency-Key | `backend/apps/wallet/views.py` (TransferenciaView) | 369–481 |
| `GET /api/v1/wallet/balance/` | `backend/apps/wallet/views.py` (BalanceView) | 296–333 |
| `GET /api/v1/wallet/history/` | `backend/apps/wallet/views.py` (HistorialView) | 336–366 |
| Rutas de wallet | `backend/apps/wallet/urls.py` | 1–22 |

### 3. Catálogo de eventos y mercados

**Cómo se usa:**

```
GET /api/v1/betting/events/?status=live
Header: Authorization: Bearer <token>
→ 200: lista de eventos con mercados y cuotas

GET /api/v1/betting/events/?status=scheduled
→ solo programados
```

Los eventos se sincronizan automáticamente desde **The Odds API** vía el `SyncEngine` (`services.py:12`). La tarea Celery `sync_fixtures` corre cada 2 horas (`tasks.py:91`). Si la API no responde, se generan cuotas mock (`services.py:408`). El `EventViewSet` (`views.py:15`) aplica auto-transición de estados: `scheduled → in_play` cuando `starts_at <= now`, e `in_play → finished` tras 3 horas.

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Modelo `Event` con 5 estados | `backend/apps/betting/models.py` | 32–53 |
| Modelo `Market` (1X2, Over/Under, BTTS, Handicap, Moneyline) | `backend/apps/betting/models.py` | 55–61 |
| Modelo `Selection` con odds decimal | `backend/apps/betting/models.py` | 64–71 |
| Modelos `League` y `Team` | `backend/apps/betting/models.py` | 6–29 |
| Sincronización con The Odds API | `backend/apps/betting/services.py` (SyncEngine) | 12–515 |
| Margen del operador 5% | `backend/apps/betting/services.py:150`, `backend/config/settings/base.py:137` |
| Mercados mock cuando API falla | `backend/apps/betting/services.py` | 408–478 |
| `GET /api/v1/betting/events/` | `backend/apps/betting/views.py` (EventViewSet) | 15–53 |

### 4. Apuesta simple

**Cómo se usa:**

```
POST /api/v1/betting/bets/
Header: Authorization: Bearer <token>, Idempotency-Key: <uuid>
Body: { "stake": 100.00, "selections": [{ "selection_id": 1, "expected_odds": 2.1000 }] }
→ 201: apuesta creada en estado accepted, fondos bloqueados

Liquidación automática (Celery cada 5 min):
  tarea settle_finished_matches → resuelve selecciones → liquidar Bet
  Si acierta → won: CREDIT wallet con payout, DEBIT apuestas_pendientes
  Si falla  → lost: CREDIT casa, DEBIT apuestas_pendientes
```

Flujo completo: el usuario envía la apuesta → se valida la `Idempotency-Key` contra Redis (`views.py:88-92`) → se valida saldo, KYC, autoexclusión, estado del evento, montos mín/max, re-cotización de odds (`serializers.py:210-308`) → se bloquea el usuario con `select_for_update` (`views.py:117`) → se crea el `Bet` + `BetSelection` → se ejecuta la partida doble: DEBIT wallet_usuario, CREDIT apuestas_pendientes (`views.py:162-178`) → se guarda respuesta en Redis 5 min como idempotencia (`views.py:218`). La liquidación la hace `settle_finished_matches` (`tasks.py:153`) que resuelve selección por selección con `_resolve_selection_result` (`tasks.py:13`).

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Modelo `Bet` (5 estados) | `backend/apps/betting/models.py` | 74–98 |
| Modelo `BetSelection` | `backend/apps/betting/models.py` | 277–292 |
| `POST /api/v1/betting/bets/` | `backend/apps/betting/views.py` (BetViewSet.create) | 71–226 |
| Validación: saldo suficiente | `backend/apps/betting/views.py` | 120–128 |
| Validación: KYC y autoexclusión | `backend/apps/betting/serializers.py` | 222–250 |
| Validación: evento no iniciado / en vivo | `backend/apps/betting/serializers.py` | 290–299 |
| Validación: monto mínimo 1, máximo 10000 | `backend/apps/betting/serializers.py` | 198–208 |
| Bloqueo de fondos vía partida doble | `backend/apps/betting/views.py` | 162–178 |
| Idempotency-Key (UUID + Redis 5 min) | `backend/apps/betting/views.py` | 73–92, 218 |
| Liquidación: settle_as_won/lost/cancelled | `backend/apps/betting/models.py` (Bet) | 100–274 |
| Tarea Celery settle_finished_matches (c/5 min) | `backend/apps/betting/tasks.py` | 153–317 |
| Motor de resolución de selecciones | `backend/apps/betting/tasks.py` (_resolve_selection_result) | 13–88 |

### 5. Controles de juego responsable (obligatorios)

**Cómo se usa:**

```
# Límites de depósito
GET /api/v1/responsible/limits/
Header: Authorization: Bearer <token>
→ 200: { "daily_limit": "1000.0000", "weekly_limit": "5000.0000", ... }

PUT /api/v1/responsible/limits/
Header: Authorization: Bearer <token>
Body: { "daily_limit": 200.00 }  // Reducción → inmediata
Body: { "daily_limit": 1500.00 } // Aumento → cooldown 24h

# Autoexclusión
POST /api/v1/users/self-exclude/
Header: Authorization: Bearer <token>
Body: { "dias": 30 }  // 7, 30, 90 días, o null para permanente
→ 200: cuenta bloqueada inmediatamente

# Validación automática:
Al depositar → se validan límites diario/semanal/mensual (wallet/views.py:48-133)
Al apostar → se valida que no esté autoexcluido (betting/serializers.py:228-244)
Al expirar autoexclusión → se restaura estado automáticamente (users/views.py:120-127)
```

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Modelo `ResponsibleGamingLimit` | `backend/apps/responsible/models.py` | 8–111 |
| Modelo `AutoExclusion` | `backend/apps/responsible/models.py` | 114–147 |
| `GET /api/v1/responsible/limits/` | `backend/apps/responsible/views.py` | 15–22 |
| `PUT /api/v1/responsible/limits/` (cooldown 24h en aumentos) | `backend/apps/responsible/views.py` | 24–82 |
| Reglas: bajar instantáneo, subir cooldown | `backend/apps/responsible/views.py` | 49–71 |
| Autoexclusión (endpoint) | `backend/apps/users/views.py` (AutoexclusionView) | 134–205 |
| Validación de autoexclusión en apuestas | `backend/apps/betting/serializers.py` | 228–244 |
| Validación de límites en depósitos | `backend/apps/wallet/views.py` (DepositoView) | 48–133 |
| Tarea Celery apply_expired_limits (c/1h) | `backend/apps/responsible/tasks.py` | 15–44 |
| Restauración automática post autoexclusión | `backend/apps/users/views.py` (MiPerfilView) | 120–127 |
| Disclaimer obligatorio en respuestas | `backend/apps/betting/views.py` | 221–224 |

---

## Nivel 2 — Avanzado (25%)

### 6. Apuestas combinadas (acumuladoras)

**Cómo se usa:**

```
POST /api/v1/betting/bets/
Header: Authorization: Bearer <token>, Idempotency-Key: <uuid>
Body: { "stake": 50.00,
        "selections": [
          { "selection_id": 1, "expected_odds": 2.1000 },
          { "selection_id": 5, "expected_odds": 1.8500 },
          { "selection_id": 9, "expected_odds": 3.4000 }
        ] }
→ 201: type="accumulator", potential_payout = stake × (2.10 × 1.85 × 3.40)
```

Si envías múltiples `selections`, el backend detecta `len(selections) > 1` y crea un `Bet` con `type='accumulator'` (`views.py:137`). La cuota final es el **producto** de todas las cuotas individuales (`views.py:131-134`). Se valida que no hayan dos selecciones del mismo evento (`serializers.py:301-304`). En liquidación: si **alguna** selección pierde → toda la combinada es `lost`; si todas ganan → `won`; si todas son anuladas → `cancelled` (reembolso) (`tasks.py:217-257`).

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Tipo `accumulator` en modelo Bet | `backend/apps/betting/models.py` | 83–86 |
| Cálculo cuota final = producto | `backend/apps/betting/views.py` | 131–137 |
| Validación exclusiones mutuas (mismo evento) | `backend/apps/betting/serializers.py` | 301–304 |
| Liquidación combinada | `backend/apps/betting/tasks.py` | 217–257 |

### 7. Cuotas en tiempo real (WebSockets)

**Cómo se usa:**

```
# Cliente WebSocket
ws://host/ws/events/1/          → canal público del evento 1 (marcador, cuotas)
ws://host/ws/notifications/     → canal privado del usuario autenticado (notificaciones)

# El servidor envía mensajes como:
{ "type": "odds_changed", "selection_id": 5, "selection_name": "Local", "new_odds": "1.9500" }
{ "type": "event_update", "event_id": 1, "status": "in_play", "home_score": 1, "away_score": 0 }
{ "type": "bet_accepted", "bet_id": 42, "message": "Apuesta aceptada" }
{ "type": "bet_settled", "bet_id": 42, "status": "won", "payout": "210.0000" }
```

La política de **re-cotización** funciona así: cuando el usuario envía una apuesta con `expected_odds`, el serializador compara contra la cuota actual en BD (`serializers.py:267-273`). Si hay diferencia → lanza `OddsChangedException` con HTTP 409 y devuelve las nuevas cuotas para que el usuario reconfirme (`serializers.py:110-124`).

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Configuración Channels + Redis | `backend/config/settings/base.py` | 117–125 |
| ASGI Router | `backend/config/asgi.py` | 1–17 |
| Consumer `EventConsumer` (canal por evento) | `backend/apps/betting/consumers.py` | 6–51 |
| Consumer `UserNotificationConsumer` (privado) | `backend/apps/betting/consumers.py` | 54–101 |
| Enrutamiento WebSocket | `backend/apps/betting/routing.py` | 1–12 |
| Broadcast de cambios de cuota | `backend/apps/betting/services.py` (broadcast_odds_update) | 499–514 |
| Broadcast de actualización de evento | `backend/apps/betting/services.py` (broadcast_event_update) | 480–497 |
| Notificación de apuesta aceptada | `backend/apps/betting/views.py` (broadcast_bet_placed) | 228–246 |
| Notificación de cash-out | `backend/apps/betting/views.py` (broadcast_cash_out_placed) | 351–370 |
| Notificación de liquidación | `backend/apps/betting/tasks.py` | 260–277 |
| Política de re-cotización (HTTP 409) | `backend/apps/betting/serializers.py` | 110–124, 263–280 |

### 8. Apuestas en vivo (in-play)

**Cómo se usa:**

```
# No requiere endpoint especial — funciona automáticamente:
# 1. Cuando starts_at <= now, el EventViewSet pasa el evento a in_play (views.py:25-28)
# 2. sync_live_scores (cada 30s) actualiza marcadores desde The Odds API (tasks.py:113)
# 3. Si hay gol → suspend_markets_for_event desactiva mercados + envía WebSocket (services.py:345)
# 4. Tras 15s → resume_markets_after_suspension reactiva (tasks.py:291)

# Las apuestas en vivo se habilitan automáticamente (serializers.py:298):
#   event.status == 'in_play' → permite apostar
#   event.status == 'scheduled' y starts_at <= now → bloquea (ya empezó pero no está in_play)
```

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Auto-transición a `in_play` | `backend/apps/betting/views.py` (EventViewSet) | 25–28 |
| Validación: eventos `in_play` aceptan apuestas | `backend/apps/betting/serializers.py` | 298–299 |
| Sincronización de marcadores en vivo | `backend/apps/betting/services.py` | 267–343 |
| Tarea Celery sync_live_scores (c/30s) | `backend/apps/betting/tasks.py` | 113–123 |
| Suspensión automática en goles | `backend/apps/betting/services.py` (suspend_markets_for_event) | 345–373 |
| Reactivación con Celery countdown 15s | `backend/apps/betting/tasks.py` (resume_markets_after_suspension) | 291–316 |
| Broadcast de suspensión por WebSocket | `backend/apps/betting/services.py` | 351–367 |
| Tarea update_odds (c/10s) | `backend/apps/betting/tasks.py` | 127–149 |

### 9. Cash-out

**Cómo se usa:**

```
POST /api/v1/betting/bets/42/cashout/
Header: Authorization: Bearer <token>
→ 200: { "status": "cashed_out", "potential_payout": "45.6000", ... }

# Fórmula: cashout = stake × (odds_original / odds_actual) × 0.95
# Ej: stake=100, odds_orig=2.10, odds_actual=4.50 → cashout = 100 × (2.10/4.50) × 0.95 = 44.33
```

El flag `can_cashout` en el serializador (`serializers.py:181-196`) indica dinámicamente si una apuesta califica: debe estar en estado `accepted` y ningún evento asociado puede estar `finished`, `cancelled` o `suspended`. La vista `cashout` (`views.py:248`) valida todo, calcula el monto, y ejecuta `perform_cash_out` que libera `apuestas_pendientes`, acredita al usuario y salda con la casa (`models.py:220-274`).

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| `POST /api/v1/betting/bets/{id}/cashout/` | `backend/apps/betting/views.py` (BetViewSet.cashout) | 248–349 |
| Fórmula: stake × (odds_orig / odds_act) × 0.95 | `backend/apps/betting/views.py` | 297–299 |
| Método perform_cash_out con partida doble | `backend/apps/betting/models.py` (Bet.perform_cash_out) | 220–274 |
| Validación: accepted, no finished/suspended | `backend/apps/betting/views.py` | 261–281 |
| Flag can_cashout en serializador | `backend/apps/betting/serializers.py` | 181–196 |

### 10. Mercados adicionales

**Cómo se usa:**

```
# Los mercados se generan automáticamente al sincronizar eventos:
# 1X2: Local @ 2.10, Empate @ 3.40, Visitante @ 3.60
# Over/Under 2.5: Over @ 1.85, Under @ 1.95
# BTTS: Sí @ 1.75, No @ 2.05
# Handicap Asiático -0.5: Local @ 1.90, Visitante @ 1.90
# Moneyline (deportes sin empate): Local @ 1.85, Visitante @ 1.95

# Para apostar en cualquier mercado, solo cambia el selection_id:
POST /api/v1/betting/bets/
Body: { "stake": 100, "selections": [{ "selection_id": 5, "expected_odds": 1.8500 }] }
# donde selection_id=5 puede ser "Over" en Over/Under 2.5
```

La generación mock (`services.py:408-478`) crea 4 mercados para fútbol (1X2, Over/Under 2.5, BTTS, Handicap Asiático) y 2 para otros deportes (Moneyline, Over/Under dinámico). La resolución en liquidación (`tasks.py:13-88`) sabe calcular el resultado para cada tipo de mercado.

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Over/Under 2.5 + línea dinámica | `backend/apps/betting/services.py` (generate_mock_odds) | 424–432 |
| BTTS | `backend/apps/betting/services.py` | 434–442 |
| Handicap Asiático -0.5 | `backend/apps/betting/services.py` | 444–452 |
| Moneyline (deportes sin empate) | `backend/apps/betting/services.py` | 454–462 |
| Resolución de todos los mercados | `backend/apps/betting/tasks.py` (_resolve_selection_result) | 13–88 |

---

## Nivel 3 — Compliance, auditoría y operación (20%)

### 11. Auditoría inmutable

**Cómo se usa:**

```
# Automático — no requiere acción del usuario.
# Cada vez que se crea un LedgerEntry, Bet, Selection, Event o Market,
# las señales de Django (signals.py) registran automáticamente en AuditLogEntry.

# Verificación manual:
GET /api/v1/audit/verify/
Header: Authorization: Bearer <token_admin>
→ 200: { "status": "verified", "registros_auditados": 1523 }
→ 400: { "status": "compromised", "registro_comprometido_id": 42 }  // si alguien manipuló la BD

GET /api/v1/audit/export/?format=csv
→ archivo CSV con toda la cadena de auditoría

GET /api/v1/audit/export/?format=json
→ JSON con todos los registros
```

El modelo `AuditLogEntry` (`models.py:8`) implementa una **blockchain básica append-only**: cada registro almacena `previous_hash` (hash del registro anterior) y `current_hash = SHA256(previous_hash + payload)`. No se permite modificar ni borrar (`save` y `delete` lanzan `ValidationError`). El endpoint `AuditVerifyView` (`views.py:16`) recorre toda la cadena y verifica que los hashes coincidan.

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Modelo AuditLogEntry (previous_hash, current_hash, payload) | `backend/apps/audit/models.py` | 8–104 |
| Encadenamiento SHA-256 | `backend/apps/audit/models.py` (calculate_hash) | 67–83 |
| Restricción append-only (no update/delete) | `backend/apps/audit/models.py` (save, delete) | 85–104 |
| Señal: auditar LedgerEntry | `backend/apps/audit/signals.py` (audit_wallet_entry) | 13–40 |
| Señal: auditar Bet | `backend/apps/audit/signals.py` (audit_bet_change) | 43–71 |
| Señal: auditar cambios de cuota | `backend/apps/audit/signals.py` (audit_selection_odds_change) | 74–120 |
| Señal: auditar cambios de estado Event | `backend/apps/audit/signals.py` (audit_event_status_change) | 123–191 |
| Señal: auditar creación Market | `backend/apps/audit/signals.py` (audit_market_creation) | 194–216 |
| Señal: auditar creación Selection | `backend/apps/audit/signals.py` (audit_selection_creation) | 219–243 |
| `GET /api/v1/audit/verify/` | `backend/apps/audit/views.py` (AuditVerifyView) | 16–92 |
| `GET /api/v1/audit/export/` | `backend/apps/audit/views.py` (AuditExportView) | 95–145 |

### 12. Anti-fraude básico

**Cómo se usa:**

```
# Automático — se ejecuta en cada operación clave:
# Al registrarse → log_and_check_ip (users/views.py:36-38)
# Al depositar → log_and_check_ip (wallet/views.py:38-40)
# Al apostar → check_syndicated_betting + check_bonus_arbitrage (betting/views.py:207-215)
# Al hacer cashout → check_deposit_cashout_pattern (betting/views.py:309-315)

# Tarea programada:
# rescan_fraud_patterns (cada 1 hora) → escanea retroactivamente (fraud/tasks.py:15)

# Las alertas se guardan en SuspiciousActivity con severidad y estado:
# El admin las revisa manualmente y puede cambiar su estado a REVIEWED o DISMISSED
```

4 reglas de detección implementadas en `FraudDetector` (`services.py:12`):
1. **Multicuenta**: misma IP usada por >3 usuarios distintos → alerta MEDIUM
2. **Cash-out inmediato**: depósito seguido de cash-out en <15 min → alerta HIGH
3. **Apuestas sindicalizadas**: ≥3 usuarios con idéntico stake y selecciones en <5 min → alerta HIGH
4. **Abuso de bono**: apuestas cubriendo resultados opuestos del mismo mercado con bono activo → alerta HIGH

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Modelo UserIpLog | `backend/apps/fraud/models.py` | 6–32 |
| Modelo SuspiciousActivity | `backend/apps/fraud/models.py` | 35–134 |
| Regla 1: IP >3 cuentas | `backend/apps/fraud/services.py` (log_and_check_ip) | 17–51 |
| Regla 2: depósito → cashout <15 min | `backend/apps/fraud/services.py` (check_deposit_cashout_pattern) | 54–87 |
| Regla 3: apuestas idénticas en grupo | `backend/apps/fraud/services.py` (check_syndicated_betting) | 90–133 |
| Regla 4: abuso de bono (arbitraje) | `backend/apps/fraud/services.py` (check_bonus_arbitrage) | 136–199 |
| Registro IP en registro | `backend/apps/users/views.py` | 36–38 |
| Registro IP en depósitos | `backend/apps/wallet/views.py` | 38–40 |
| Verificaciones al apostar | `backend/apps/betting/views.py` | 207–215 |
| Verificación en cash-out | `backend/apps/betting/views.py` | 309–315 |
| Tarea Celery rescan_fraud_patterns (c/1h) | `backend/apps/fraud/tasks.py` | 15–99 |

### 13. Dashboard del operador

**Cómo se usa:**

```
GET /api/v1/dashboard/metrics/
Header: Authorization: Bearer <token_admin>
→ 200: {
    "ggr": "15230.5000",           // Gross Gaming Revenue
    "total_stakes": "50000.0000",
    "total_payouts": "34769.5000",
    "bet_volume": { ... },
    "active_users": { "active_users_24h": 45, "active_users_7d": 120, ... },
    "event_exposure": [             // exposición neta por evento
      { "event_id": 1, "home_team": "Real Madrid", "away_team": "Barcelona", "markets": [...] }
    ]
  }

GET /api/v1/dashboard/mincetur-report/?year=2026&month=5
Header: Authorization: Bearer <token_admin>
→ archivo CSV descargable con columnas: ticket_id, dni_jugador, username,
  fecha_colocacion, fecha_liquidacion, tipo_apuesta, evento_seleccion,
  cuota, monto_apostado, estado_apuesta, monto_pagado, ggr, moneda
```

El GGR se calcula como `total_stakes − total_payouts`, considerando `won`, `lost`, `cashed_out` y `cancelled` (`views.py:28-46`). La exposición neta por selección es `gross_exposure − total_market_stake` (`views.py:130`). El reporte MINCETUR incluye BOM UTF-8 para compatibilidad con Excel en Windows (`views.py:192-193`).

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| `GET /api/v1/dashboard/metrics/` | `backend/apps/dashboard/views.py` (OperatorDashboardView) | 22–155 |
| Cálculo de GGR | `backend/apps/dashboard/views.py` | 28–46 |
| Volumen de apuestas | `backend/apps/dashboard/views.py` | 48–66 |
| Usuarios activos (24h, 7d, 30d) | `backend/apps/dashboard/views.py` | 68–82 |
| Exposición financiera por evento | `backend/apps/dashboard/views.py` | 84–144 |
| `GET /api/v1/dashboard/mincetur-report/` | `backend/apps/dashboard/views.py` (MinceturReportView) | 158–269 |
| BOM UTF-8 para Excel | `backend/apps/dashboard/views.py` | 192–193 |
| Columnas del CSV | `backend/apps/dashboard/views.py` | 200–267 |
| Restricción IsAdminUser | `backend/apps/dashboard/views.py` | 23, 159 |

### 14. Bonos promocionales (opcional)

**Cómo se usa:**

```
# Automático en el primer depósito:
POST /api/v1/wallet/deposit/
Body: { "amount": 300.00 }
→ 201: { ..., "bono_bienvenida": { "bono_otorgado": "300.0000",
        "rollover_requerido": "1800.0000",
        "mensaje": "¡Bono de Bienvenida 100% acreditado!" } }

# El bono es el 100% del primer depósito, hasta 500 fichas.
# Rollover: debe apostar 6× el bono (ej: 300 → debe apostar 1800) antes de retirar.
# Solo cuentan apuestas con cuota total ≥ 1.5 (betting/views.py:186).

# Si intenta retirar con rollover pendiente:
POST /api/v1/wallet/withdraw/
→ 400: { "error": "No puedes retirar fondos. Tienes un bono activo con rollover pendiente..." }
```

| Sub-funcionalidad | Archivo | Líneas |
|---|---|---|
| Modelo UserBonus | `backend/apps/wallet/models.py` | 146–195 |
| Bono bienvenida 100% (hasta 500) en 1er depósito | `backend/apps/wallet/views.py` (DepositoView) | 153–192 |
| Contabilidad partida doble del bono | `backend/apps/wallet/views.py` | 175–192 |
| Actualización rollover al apostar (cuota ≥ 1.5) | `backend/apps/betting/views.py` | 180–192 |
| Bloqueo de retiro con rollover pendiente | `backend/apps/wallet/views.py` (RetiroView) | 233–250 |
| Propiedad remaining_rollover | `backend/apps/wallet/models.py` | 189–194 |

---

## Caché en Redis para proteger la API externa (The Odds API)

En `backend/apps/betting/the_odds_api.py` — clase `OddsCache`, cada método sigue el patrón **Cache-Aside**: verifica Redis antes de llamar a la API.

### Fixtures (partidos) — TTL 2 horas

```python
# Línea 119-136
cache_key = self._key_fixtures(league_id)
cached_data = cache.get(cache_key)          # ← Verifica Redis primero
if cached_data is not None:
    return cached_data                       # ← Cache HIT: devuelve sin llamar API

data = api_fetch_fn()                        # ← Cache MISS: llama a la API
if data:
    cache.set(cache_key, data, timeout=7200) # ← Guarda en Redis por 2h
return data
```

### Scores en vivo — TTL 30 segundos

```python
# Línea 147-158
cache_key = self._key_scores()
cached_data = cache.get(cache_key)          # ← Verifica Redis
if cached_data is not None:
    return cached_data

data = api_fetch_fn()
if data:
    cache.set(cache_key, data, timeout=30)  # ← Guarda 30s
return data
```

### Cuotas — TTL 10 segundos

```python
# Línea 175-186
cache_key = self._key_odds(event_id)
cached_data = cache.get(cache_key)
if cached_data is not None:
    return cached_data

data = api_fetch_fn()
if data:
    cache.set(cache_key, data, timeout=10)  # ← Guarda 10s
return data
```

### Protección contra errores (TTL 5 min)

```python
# Línea 110-117
error_key = self._key_error('fixtures', league_id)
cached_error = cache.get(error_key)          # ← Si hay error cacheado
if cached_error is not None:
    return []                                 # ← No llama a API, devuelve vacío

try:
    data = api_fetch_fn()
except Exception as e:
    cache.set(error_key, str(e), timeout=300) # ← Guarda error 5min
    return []
```

Los TTLs se definen en `backend/config/settings/base.py:168-173`:
```python
ODDS_CACHE_TTL_FIXTURES = 7200   # 2 horas
ODDS_CACHE_TTL_LIVE_SCORES = 30   # 30 segundos
ODDS_CACHE_TTL_ODDS = 10          # 10 segundos
ODDS_CACHE_TTL_API_ERROR = 300    # 5 minutos si falla
```

---

## Configuración General

| Componente | Archivo | Líneas |
|---|---|---|
| Settings base (INSTALLED_APPS, MIDDLEWARE, REST_FRAMEWORK, Channels, Celery, CORS, JWT) | `backend/config/settings/base.py` | 1–213 |
| Variables de entorno | `.env` | 1–37 |
| Docker Compose (db, redis, backend, celery_worker, celery_beat) | `docker-compose.yml` | 1–132 |
| Makefile (comandos útiles) | `Makefile` | 1–58 |
| Dockerfile del backend | `backend/Dockerfile` | — |
| README del proyecto | `README.md` | 1–187 |
| AGENTS.md (guía para agentes IA) | `AGENTS.md` | — |

---

## Flujo completo del WebSocket (Cliente → Daphne → Redis → Channels → Broadcast)

### Arquitectura general

```
Cliente WebSocket ←→ Daphne (ASGI Server) ←→ Redis (Channel Layer) ←→ Django Consumers
                                                    ↕
                                           Celery Worker (tareas)
```

### Paso a paso

**Fase de conexión:**

1. El cliente inicia conexión WebSocket a `ws://host/ws/events/{event_id}/` o `ws://host/ws/notifications/`
2. **Daphne** (servidor ASGI, `base.py:24`) recibe la solicitud y la enruta a través del `ProtocolTypeRouter` (`asgi.py:12-17`)
3. El `AuthMiddlewareStack` (`asgi.py:14`) extrae la sesión del usuario de Django y la inyecta en `scope['user']`
4. El `URLRouter` (`asgi.py:15`) dirige al consumer correspondiente según `routing.py:6-11`:
   - `r'^ws/events/(?P<event_id>\d+)/$'` → `EventConsumer`
   - `r'^ws/notifications/$'` → `UserNotificationConsumer`
5. El consumer se une a un **grupo de Channel Layer** (`consumers.py:16-18`):
   - `EventConsumer` → grupo `"event_{event_id}"`
   - `UserNotificationConsumer` → grupo `"user_{user_id}"`
6. Se acepta la conexión con `await self.accept()` (`consumers.py:20`)

**Fase de mensajes (servidor → cliente):**

7. Cuando ocurre un evento de negocio (cambio de cuota, gol, apuesta, liquidación), el código fuente llama a `get_channel_layer().group_send(grupo, mensaje)` desde cualquier parte del sistema:
   - `services.py:356-365` — suspensión de mercados
   - `services.py:486-495` — actualización de evento
   - `services.py:499-514` — cambio de cuota
   - `views.py:237-244` — apuesta aceptada
   - `views.py:357-368` — cash-out
   - `tasks.py:261-277` — liquidación de apuesta
8. **Redis** (`CHANNEL_LAYERS['default']` en `base.py:118-124`) recibe el mensaje y lo distribuye a todos los canales suscritos al grupo
9. El consumer recibe el mensaje y lo envía al cliente WebSocket mediante `self.send(text_data=json.dumps(event))` (ej: `consumers.py:33`, `consumers.py:89`)

**Diagrama de flujo para un cambio de cuota en vivo:**

```
1. The Odds API → SyncEngine.sync_odds_for_event()
2.   → Selection.objects.update_or_create() → post_save signal (audit signals.py)
3.   → broadcast_odds_update() (services.py:499)
4.     → channel_layer.group_send("event_123", { "type": "odds_changed", ... })
5.       → Redis Channel Layer (base.py:118-124)
6.         → distribuye a todos los EventConsumer conectados al grupo "event_123"
7.           → EventConsumer.odds_changed() (consumers.py:35)
8.             → self.send(text_data=...) → WebSocket → cliente
```

**Diagrama de flujo para liquidación de apuesta (Celery → WebSocket):**

```
1. Celery Beat: task settle_finished_matches cada 5 min (base.py:193-196)
2. settle_finished_matches() (tasks.py:153)
3.   → Bet.settle_as_won() o settle_as_lost() (models.py)
4.     → LedgerEntry.objects.create() (partida doble)
5.   → channel_layer.group_send("user_5", { "type": "bet_settled", ... }) (tasks.py:266-275)
6.     → Redis Channel Layer
7.       → UserNotificationConsumer.bet_settled() (consumers.py:97)
8.         → self.send(text_data=...) → WebSocket → cliente
```

**Suspensión y reanudación de mercados en vivo:**

```
1. Gol detectado en sync_live_scores() (services.py:319-323)
2. suspend_markets_for_event() (services.py:345)
3.   → markets.filter(is_active=True).update(is_active=False)
4.   → channel_layer.group_send("event_123", { "type": "market_suspended", ... }) → WebSocket
5.   → resume_markets_after_suspension.apply_async(args=[event.id], countdown=15) (services.py:372)
6.     → Celery Worker: a los 15 segundos ejecuta resume_markets_after_suspension (tasks.py:291)
7.       → Market.objects.filter(event_id=event_id).update(is_active=True)
8.       → channel_layer.group_send("event_123", { "type": "market_resumed", ... }) → WebSocket
```

**Archivos clave del flujo WebSocket:**

| Componente | Archivo | Rol |
|---|---|---|
| Configuración Channel Layer (Redis) | `backend/config/settings/base.py:118-124` | Define Redis como backend de canales |
| Router ASGI (Daphne) | `backend/config/asgi.py:12-17` | Enruta HTTP y WebSocket |
| Enrutamiento WebSocket | `backend/apps/betting/routing.py:6-11` | Mapea URLs a Consumers |
| Consumer de eventos | `backend/apps/betting/consumers.py:6-51` | Canal público por evento (marcador, cuotas) |
| Consumer de notificaciones | `backend/apps/betting/consumers.py:54-101` | Canal privado por usuario (apuestas, cashout) |
| Broadcast desde servicios | `backend/apps/betting/services.py:480-514` | Envía actualizaciones de cuotas y eventos |
| Broadcast desde apuestas | `backend/apps/betting/views.py:228-246, 351-370` | Envía notificaciones de bets y cashouts |
| Broadcast desde tareas | `backend/apps/betting/tasks.py:260-277` | Envía notificaciones de liquidación |
| Broadcast desde suspensión | `backend/apps/betting/services.py:351-367` | Envía suspensión por gol |
| Reactivación por Celery | `backend/apps/betting/tasks.py:291-316` | Reanuda mercados tras N segundos |

---

## Significado de las carpetas del proyecto (en español)

### Raíz del proyecto

| Carpeta/Archivo | Significado |
|---|---|
| `backend/` | Contiene todo el código del servidor (Django, DRF, Channels, Celery) |
| `docs/` | Documentación del proyecto por fases (Fase 2 a 12), lecciones aprendidas, compliance y anti-AI |
| `.agent/` | Configuración del agente de IA para el proyecto |
| `.git/` | Repositorio Git (control de versiones) |

### `backend/`

| Carpeta/Archivo | Significado |
|---|---|
| `apps/` | Aplicaciones Django (cada una es un módulo funcional independiente) |
| `config/` | Configuración central de Django (settings, urls, asgi, celery) |
| `frontend/` | Vistas de plantillas HTML (login, registro, dashboard visual) |
| `templates/` | Plantillas HTML genéricas del proyecto |
| `static/` | Archivos estáticos (CSS, JavaScript, imágenes) |
| `staticfiles/` | Archivos estáticos compilados/colectados para producción |
| `mediafiles/` | Archivos subidos por usuarios (imágenes, documentos) |
| `requirements/` | Dependencias de Python separadas por entorno (dev, prod) |
| `manage.py` | Script principal de Django (gestión de migraciones, servidor, etc.) |

### `backend/apps/` — Aplicaciones Django

| Carpeta | Significado |
|---|---|
| `users/` | **Usuarios**: registro con KYC, validación DNI peruano, JWT, perfiles |
| `wallet/` | **Billetera virtual**: contabilidad de partida doble, depósitos, retiros, transferencias, bonos |
| `betting/` | **Apuestas**: eventos deportivos, mercados, cuotas, colocación de apuestas, cash-out, WebSockets, sincronización con API externa |
| `responsible/` | **Juego responsable**: límites de depósito diario/semanal/mensual, autoexclusión temporal/permanente |
| `audit/` | **Auditoría**: cadena inmutable SHA-256, verificación de integridad, exportación de registros |
| `fraud/` | **Anti-fraude**: detección de multicuenta, apuestas sindicalizadas, abuso de bonos, patrones sospechosos |
| `dashboard/` | **Panel de control**: métricas operativas (GGR, exposición), reporte regulatorio MINCETUR en CSV |

### Estructura interna de cada `app/` (ej: `users/`)

| Archivo | Significado |
|---|---|
| `models.py` | Definición de tablas de base de datos (Modelos) |
| `views.py` | Lógica de los endpoints (Vistas) |
| `serializers.py` | Validación y transformación de datos de entrada/salida |
| `urls.py` | Rutas (mapeo entre URLs y Vistas) |
| `tests.py` | Pruebas unitarias y de integración |
| `admin.py` | Configuración del panel de administración de Django |
| `apps.py` | Configuración de la aplicación Django |
| `migrations/` | Migraciones de base de datos (cambios al esquema) |
| `validators.py` | Funciones de validación personalizadas (solo en `users/`) |
| `services.py` | Lógica de negocio compleja (solo en `betting/`, `fraud/`) |
| `tasks.py` | Tareas periódicas de Celery (solo en `betting/`, `responsible/`, `fraud/`) |
| `consumers.py` | Consumidores WebSocket (solo en `betting/`) |
| `routing.py` | Enrutamiento WebSocket (solo en `betting/`) |
| `signals.py` | Señales de Django para auditoría automática (solo en `audit/`) |
| `the_odds_api.py` | Cliente para la API externa de datos deportivos (solo en `betting/`) |

### `docs/`

| Archivo | Significado |
|---|---|
| `documentofase{2..12}.md` | Documentación detallada de cada fase del proyecto |
| `lecciones.md` | Lecciones aprendidas durante el desarrollo |
| `compliance.md` | Cumplimiento normativo (Ley 31557, DS 005-2023-MINCETUR) |
| `anti-ai-disclosure.md` | Divulgación sobre uso de IA en el desarrollo |
| `adr/` | Decisiones de arquitectura (Architecture Decision Records) |

### `backend/config/`

| Archivo | Significado |
|---|---|
| `settings/base.py` | Configuración base de Django (apps, middleware, BD, Redis, Celery, JWT, CORS) |
| `settings/dev.py` | Configuración para entorno de desarrollo |
| `settings/prod.py` | Configuración para entorno de producción |
| `urls.py` | Rutas principales del proyecto (API v1, admin, frontend) |
| `asgi.py` | Punto de entrada ASGI (Daphne + WebSockets + HTTP) |
| `celery.py` | Configuración de Celery (tareas en segundo plano) |
