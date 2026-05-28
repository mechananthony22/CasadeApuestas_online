import os
import sys
from pathlib import Path
from decimal import Decimal

# Construye rutas dentro del proyecto de esta manera: BASE_DIR / 'subdirectorio'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Agrega la carpeta 'apps/' a sys.path para permitir importaciones limpias
# (por ejemplo: 'from users.models import ...' en lugar de 'from apps.users.models import ...')
sys.path.insert(0, os.path.join(BASE_DIR, 'apps'))

# ADVERTENCIA DE SEGURIDAD: ¡Mantén la clave secreta (SECRET_KEY) a salvo en producción!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-fairbet-lab-default-key-change-in-prod')

# ADVERTENCIA DE SEGURIDAD: ¡No ejecutes con DEBUG=True en entornos de producción!
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Definición de aplicaciones instaladas
INSTALLED_APPS = [
    # Daphne debe estar obligatoriamente antes de staticfiles para anular el servidor WSGI de desarrollo
    'daphne',
    
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Paquetes y librerías de terceros
    'rest_framework',
    'corsheaders',
    'channels',
    'rest_framework_simplejwt',
    'django_celery_beat',
    
    # Aplicaciones locales de FairBet Lab
    'users.apps.UsersConfig',
    'wallet.apps.WalletConfig',
    'betting.apps.BettingConfig',
    'responsible.apps.ResponsibleConfig',
    'audit.apps.AuditConfig',
    'fraud.apps.FraudConfig',
    'dashboard.apps.DashboardConfig',
    
    # Frontend template views
    'frontend.apps.FrontendConfig',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
# Daphne maneja la aplicación a través de la interfaz ASGI
ASGI_APPLICATION = 'config.asgi.application'

# Configuración de localización e internacionalización (Perú)
LANGUAGE_CODE = 'es-pe'
TIME_ZONE = 'America/Lima'
USE_I18N = True
USE_TZ = True

# Archivos estáticos y multimedia (CSS, JavaScript, imágenes)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'mediafiles'

# Tipo de campo de clave primaria por defecto
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Configuración de Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
}

# Configuración de CORS (Permitir todos los orígenes en desarrollo)
CORS_ALLOW_ALL_ORIGINS = True

# Configuración de la capa de canales (Channel Layer) para WebSockets utilizando Redis
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')],
        },
    },
}

# Opciones de configuración para el motor de tareas de Celery
CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# Margen del operador aplicado a las cuotas locales (5%)
OPERATOR_MARGIN = Decimal(os.environ.get('OPERATOR_MARGIN', '0.05'))

# --- CONFIGURACIÓN DE INTEGRACIÓN CON THE ODDS API (V4) ---
SPORTS_API_PROVIDER = os.environ.get('SPORTS_API_PROVIDER', 'the_odds_api')
THE_ODDS_API_KEY = os.environ.get('THE_ODDS_API_KEY', '')
THE_ODDS_API_URL = os.environ.get('THE_ODDS_API_URL', 'https://api.the-odds-api.com/v4')

# Mapeo de IDs de liga locales a sport_key de The Odds API
# SOLO FÚTBOL: Solo soccer para el tier gratuito (gratis) de The Odds API
THE_ODDS_API_SPORTS = {
    140: 'soccer_spain_la_liga',       # La Liga
    39: 'soccer_epl',                  # Premier League
    2: 'soccer_uefa_champs_league',    # Champions League
    13: 'soccer_conmebol_copa_libertadores', # Copa Libertadores
    247: 'soccer_conmebol_copa_sudamericana', # Copa Sudamericana
    135: 'soccer_italy_serie_a',       # Serie A
    78: 'soccer_germany_bundesliga',   # Bundesliga
    61: 'soccer_france_ligue_one',     # Ligue 1
    71: 'soccer_brazil_campeonato',    # Brasileirão Série A
    262: 'soccer_mexico_liga_mx',      # Liga MX
}
# Nota: NBA, NFL, MLB, etc. fueron removidos porque el tier gratuito de The Odds API
# solo cubre soccer. Si necesitas esos deportes, necesitas un plan pagado.

# --- CACHE TTL CONFIGURATION PARA THE ODDS API ---
# Estos valores controlan cuánto tiempo se mantienen los datos en Redis antes de
# hacer un nuevo request a la API externa. Esto protege los API credits del desperdicio.
ODDS_CACHE_TTL_FIXTURES = 7200   # 2 horas - Tiempo entre sincronizaciones de fixtures
ODDS_CACHE_TTL_LIVE_SCORES = 30  # 30 segundos - Marcadores en vivo
ODDS_CACHE_TTL_ODDS = 10        # 10 segundos - Cuotas en vivo
ODDS_CACHE_TTL_API_ERROR = 300  # 5 minutos - Cuando la API falla (401, 429, timeout),
                                  # guardamos el error por este tiempo para no hacer
                                  # retries inmediatos que gastarían credits innecesariamente.

# --- PLANIFICACIÓN DE TAREAS PERIÓDICAS (CELERY BEAT) ---
CELERY_BEAT_SCHEDULE = {
    'sincronizar-partidos-cada-2-horas': {
        'task': 'betting.tasks.sync_fixtures',
        'schedule': 7200.0,  # Cada 2 horas en segundos
    },
    'sincronizar-marcadores-en-vivo-cada-30-segundos': {
        'task': 'betting.tasks.sync_live_scores',
        'schedule': 30.0,   # Cada 30 segundos
    },
    'actualizar-cuotas-en-vivo-cada-10-segundos': {
        'task': 'betting.tasks.update_odds',
        'schedule': 10.0,   # Cada 10 segundos
    },
    'aplicar-limites-juego-responsable-cada-hora': {
        'task': 'responsible.tasks.apply_expired_limits',
        'schedule': 3600.0,  # Cada hora en segundos
    },
    'liquidar-apuestas-cada-5-minutos': {
        'task': 'betting.tasks.settle_finished_matches',
        'schedule': 300.0,  # Cada 5 minutos
    },
    'escaneo-retroactivo-antifraude-cada-hora': {
        'task': 'fraud.tasks.rescan_fraud_patterns',
        'schedule': 3600.0,  # Cada 1 hora
    },
}

# --- CONFIGURACIÓN JWT (djangorestframework-simplejwt) ---
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=24),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# --- CONFIGURACIÓN DE APUESTAS EN VIVO (LIVE / IN-PLAY) ---
LIVE_SUSPENSION_COOLDOWN = int(os.environ.get('LIVE_SUSPENSION_COOLDOWN', 15))

