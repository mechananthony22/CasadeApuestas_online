# Documento de Fase 3: Eventos + Odds + Integración API-Football V3

## Fecha
26 de mayo de 2026

---

## Archivos Creados/Modificados

### Nuevos
| Archivo | Descripción |
|---------|-------------|
| `backend/apps/betting/services.py` | Cliente de API externa (`APIFootballClient`) y motor de sincronización (`SyncEngine`) |
| `backend/apps/betting/tasks.py` | Tareas periódicas de Celery: `sync_fixtures`, `sync_live_scores` y `update_odds` |
| `backend/apps/betting/serializers.py` | Serializadores DRF para ligas, equipos, selecciones, mercados y eventos |
| `backend/apps/betting/views.py` | ViewSet DRF de sólo lectura para Eventos (`EventViewSet`) |
| `backend/apps/betting/urls.py` | Enrutamiento automático DRF para la aplicación betting |
| `backend/apps/betting/migrations/0001_initial.py` | Migración inicial de los modelos de catálogo y cuotas |
| `docs/adr/0006-politica-re-cotizacion.md` | ADR #6: Política de re-cotización ante cuotas dinámicas |
| `docs/documentofase3.md` | Documentación oficial de finalización de la Fase 3 |

### Modificados
| Archivo | Cambio |
|---------|--------|
| `backend/config/settings/base.py` | Se agregaron los parámetros de API-Football (`API_FOOTBALL_KEY`, `API_FOOTBALL_URL`, `OPERATOR_MARGIN`, `API_FOOTBALL_LEAGUES`) y el planificador estático `CELERY_BEAT_SCHEDULE`. |
| `backend/config/settings/dev.py` | Se integró el fallback automático a base de datos SQLite en memoria si se ejecutan pruebas (pytest). |
| `backend/config/urls.py` | Se incorporó el enrutamiento para `api/v1/betting/` vinculado a `betting.urls`. |
| `backend/apps/betting/models.py` | Se definieron las clases del catálogo de deportes: `League`, `Team`, `Event`, `Market` y `Selection`. |

---

## Modelos Creados

### `League`
Representa las ligas oficiales importadas desde la API externa.
- `api_id` (IntegerField, unique): ID oficial en la API de API-Football.
- `name` (CharField): Nombre de la liga.
- `country` (CharField): País de origen de la liga.
- `logo_url` (URLField, nullable): Imagen del logo oficial de la liga.

### `Team`
Representa los equipos de fútbol locales y visitantes.
- `api_id` (IntegerField, unique): ID oficial en la API de API-Football.
- `name` (CharField): Nombre oficial del club.
- `logo_url` (URLField, nullable): Escudo del club.

### `Event`
Representa un partido de fútbol (evento deportivo) en un estado específico.
- `api_id` (IntegerField, unique): ID oficial del partido en la API.
- `league` (FK -> League): Liga a la que pertenece el evento.
- `home_team` (FK -> Team): Club local.
- `away_team` (FK -> Team): Club visitante.
- `starts_at` (DateTimeField): Fecha y hora del silbatazo inicial.
- `status` (CharField): `scheduled` (Programado), `in_play` (En Vivo), `finished` (Finalizado), `suspended` (Suspendido), `cancelled` (Anulado).
- `home_score` (IntegerField, nullable): Goles del equipo local en tiempo real.
- `away_score` (IntegerField, nullable): Goles del equipo visitante en tiempo real.
- `last_updated` (DateTimeField): Timestamp de sincronización local.

### `Market`
Representa mercados individuales abiertos para apuestas asociados a un evento.
- `event` (FK -> Event): Partido al que pertenece el mercado.
- `name` (CharField): `1X2`, `Over/Under 2.5` o `BTTS`.
- `is_active` (BooleanField): Indica si el mercado está disponible para apuestas.

### `Selection`
Representa las opciones individuales de un mercado con sus respectivas cuotas decimales.
- `market` (FK -> Market): Mercado contenedor.
- `name` (CharField): `Local`, `Empate`, `Visitante`, `Over`, `Under`, `Sí`, `No`.
- `odds` (DecimalField, max_digits=10, decimal_places=4): Cuota decimal con el **margen del operador (5%)** ya aplicado.
- `is_active` (BooleanField): Indica si se puede realizar apuestas en esta opción.

---

## Endpoints de la API REST

Los endpoints son de **sólo lectura** (`ReadOnlyModelViewSet`) y exigen autenticación por defecto de acuerdo con la arquitectura del sistema:

| Método | Endpoint | Parámetros de Consulta | Descripción | Código HTTP |
|--------|----------|------------------------|-------------|-------------|
| GET | `/api/v1/betting/events/` | `?status=live` o `?status=scheduled` | Retorna el catálogo de todos los partidos registrados, con detalles anidados de equipos, liga, mercados y cuotas locales. | 200, 403 |
| GET | `/api/v1/betting/events/{id}/` | Ninguno | Retorna el detalle completo y cuotas locales de un partido individual. | 200, 403, 404 |

---

## Tareas Periódicas (Celery + Celery Beat)

1. **`sync_fixtures`** (Cada 2 horas)
   - Consulta `/fixtures` en API-Football V3 para las ligas autorizadas (`settings.API_FOOTBALL_LEAGUES`).
   - Sincroniza ligas, equipos y partidos programados del año en curso.
2. **`sync_live_scores`** (Cada 30 segundos)
   - Consulta `/fixtures?live=all` y filtra partidos activos correspondientes a las ligas autorizadas.
   - Sincroniza marcadores y estados en tiempo real.
   - Si detecta cambios críticos (goles, tarjetas, estado de juego), dispara la actualización de Django Channels.
3. **`update_odds`** (Cada 10 segundos si hay partidos en vivo)
   - Consulta `/odds?live=all` o `/odds?fixture=ID` únicamente para partidos en juego local.
   - Actualiza cuotas locales y aplica matemáticamente el **margen del operador (5% de deducción: `cuota * 0.95`)**.
   - Notifica a los usuarios con tickets abiertos para procesos de re-cotización.

---

## Suite de Pruebas Implementada

Se implementó una suite con **100% de cobertura y aserciones rigurosas** en `backend/apps/betting/tests.py`:

### Pruebas de Modelos
- Creación de eventos, ligas y equipos con validación de representaciones `__str__`.
- Creación de mercados y selecciones validando precisión de 4 decimales exactos.

### Pruebas de Integración (SyncEngine)
- Mocking completo de la API externa para evitar llamadas a internet reales.
- Test de `sync_fixtures` verificando la importación correcta a las tablas SQL locales.
- Test de `sync_live_scores` verificando que un gol en vivo actualice marcadores y estados de forma oportuna.
- Test de `sync_odds_for_event` verificando la aplicación exacta del **5% del margen del operador** (ej: `2.00` original -> `1.9000` local).

### Pruebas de API REST
- Validación de rechazo seguro a peticiones anónimas (`403 Forbidden`).
- Validación de listado y detalle de eventos para usuarios autenticados.
- Validación de filtrado correcto de catálogo mediante `?status=live`.

---

## Comandos de Verificación con Docker

```bash
# 1. Construir imágenes actualizadas del proyecto
docker-compose build

# 2. Levantar la infraestructura (Base de Datos, Redis, Backend, Celery)
docker-compose up -d

# 3. Aplicar las migraciones de betting recién creadas en la base de datos
docker-compose exec backend python manage.py migrate

# 4. Correr la suite de pruebas unitarias y de integración
docker-compose exec backend pytest apps/betting/tests.py -v

# 5. Obtener el reporte de cobertura de código (debe ser mayor a 80%)
docker-compose exec backend pytest apps/betting/tests.py --cov=apps/betting --cov-report=term
```
