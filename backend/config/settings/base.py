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
    'django_celery_beat',
    
    # Aplicaciones locales de FairBet Lab
    'users.apps.UsersConfig',
    'wallet.apps.WalletConfig',
    'betting.apps.BettingConfig',
    'responsible.apps.ResponsibleConfig',
    'audit.apps.AuditConfig',
    'fraud.apps.FraudConfig',
    'dashboard.apps.DashboardConfig',
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
        'DIRS': [],
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

# --- CONFIGURACIÓN DE INTEGRACIÓN CON API-FOOTBALL V3 ---
# Clave de autenticación para la API externa
API_FOOTBALL_KEY = os.environ.get('API_FOOTBALL_KEY', '')
# URL base oficial de la API de API-Football
API_FOOTBALL_URL = os.environ.get('API_FOOTBALL_URL', 'https://v3.football.api-sports.io')
# Margen del operador aplicado a las cuotas locales (5%)
OPERATOR_MARGIN = Decimal(os.environ.get('OPERATOR_MARGIN', '0.05'))
# Ligas a sincronizar por defecto (por ejemplo: Premier League ID 39, LaLiga ID 140)
API_FOOTBALL_LEAGUES = [39, 140]

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
}

# --- CONFIGURACIÓN DE APUESTAS EN VIVO (LIVE / IN-PLAY) ---
# Tiempo de enfriamiento (cooldown) en segundos para reanudar mercados tras suspensión automática
LIVE_SUSPENSION_COOLDOWN = int(os.environ.get('LIVE_SUSPENSION_COOLDOWN', 15))

