# FairBet Lab - AGENTS.md

## Quick Start (Docker-based)

```bash
cp .env.example .env
docker-compose up -d --build
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser
docker-compose exec backend python manage.py sync_fixtures
docker-compose exec backend pytest
```

## Key Commands

```bash
make up          # Start containers
make down        # Stop containers
make logs        # Tail logs
make migrate     # Run migrations
make test        # Run pytest
make shell       # Django shell
make makemigrations  # Create migrations
```

To run a single test: `docker-compose exec backend pytest apps/wallet/tests.py::TestClassName::test_method`

## Tech Stack

- **Backend**: Django 5 + DRF + Django Channels
- **ASGI Server**: Daphne (required - not runserver)
- **Task Queue**: Celery + Celery Beat
- **DB**: PostgreSQL 16
- **Cache/Broker**: Redis 7
- **Lang/Zone**: Python 3.12, America/Lima (Peru)

## App Layout

`backend/apps/` contains 7 domain apps:
- `users` - KYC registration, JWT auth
- `wallet` - Double-entry ledger (deposits/withdrawals)
- `betting` - Events, markets, selections, bets, cashout
- `responsible` - Deposit limits, self-exclusion
- `audit` - SHA-256 chained audit logs
- `fraud` - Suspicious activity detection
- `dashboard` - Operator metrics, MINCETUR reports

Plus `frontend` (template views) and `config/` (Django settings, Celery, ASGI).

## Critical Quirks

- **Daphne is required**: `daphne` must be first in `INSTALLED_APPS` to override WSGI. Without it WebSocket handshake fails.
- **Idempotency-Key header**: All mutating financial endpoints (bet placement, deposits, withdrawals) require `Idempotency-Key: <uuid>` header, cached in Redis for 5 minutes.
- **Celery Beat tasks**: Scheduled tasks in `config/settings/base.py` CELERY_BEAT_SCHEDULE include: sync_fixtures (2h), sync_live_scores (30s), update_odds (10s), apply_expired_limits (1h), settle_finished_matches (5min).
- **Decimal for money**: All monetary amounts use `Decimal` with 4 decimal places, never float.

## Code Quality

```bash
docker-compose exec backend black --check apps/
docker-compose exec backend flake8 apps/
```

## Architecture Notes

- `sys.path` is modified in `config/settings/base.py` to allow `from users.models` instead of `from apps.users.models`.
- `ASGI_APPLICATION = 'config.asgi.application'`
- Channel layers use Redis: `CHANNEL_LAYERS['default']['BACKEND'] = 'channels_redis.core.RedisChannelLayer'`
- Wallet balance is derived (sum of ledger entries), not stored.