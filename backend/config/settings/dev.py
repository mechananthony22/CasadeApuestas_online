from .base import *
import urllib.parse

DEBUG = True

# ADVERTENCIA DE SEGURIDAD: ¡Mantén la clave secreta (SECRET_KEY) a salvo en desarrollo y producción!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-fairbet-lab-super-secret-development-key-2026')

# Configuración de la base de datos
USE_SQLITE = os.environ.get('USE_SQLITE', 'False').lower() in ('true', '1', 't')

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
    # En desarrollo local sin Docker/Redis, usamos la capa de canales en memoria
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        }
    }
else:
    # Se intenta parsear DATABASE_URL desde variables de entorno, de lo contrario se usa la configuración local (PostgreSQL)
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        # Parsea la URL de conexión postgres://usuario:contraseña@host:puerto/nombre_db
        parsed = urllib.parse.urlparse(DATABASE_URL)
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': parsed.path.lstrip('/'),
                'USER': parsed.username,
                'PASSWORD': parsed.password,
                'HOST': parsed.hostname,
                'PORT': parsed.port or 5432,
            }
        }
    else:
        # Configuración de respaldo (fallback) cuando se corre fuera de Docker en el host (PostgreSQL)
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': os.environ.get('DB_NAME', 'fairbet'),
                'USER': os.environ.get('DB_USER', 'postgres'),
                'PASSWORD': os.environ.get('DB_PASSWORD', 'postgres'),
                'HOST': os.environ.get('DB_HOST', 'localhost'),
                'PORT': os.environ.get('DB_PORT', '5432'),
            }
        }

import sys

# Si se están ejecutando pruebas unitarias o de integración (con pytest o manage.py test),
# se utiliza SQLite en memoria para independizar los tests de PostgreSQL y acelerar su ejecución.
if 'test' in sys.argv or 'pytest' in sys.argv or any('pytest' in arg for arg in sys.argv):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
    ALLOWED_HOSTS = ['*']



