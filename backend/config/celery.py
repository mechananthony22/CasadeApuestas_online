import os
from celery import Celery

# Establece el módulo de configuración de Django por defecto para Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

app = Celery('fairbet')

# Carga la configuración de Celery usando las variables definidas en los settings de Django
# que comiencen con el prefijo 'CELERY_' (ejemplo: CELERY_BROKER_URL)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodescubre y registra tareas asíncronas en todos los archivos 'tasks.py' de tus apps locales
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tarea de prueba para verificar que el worker está funcionando correctamente."""
    print(f'Petición debug recibida: {self.request!r}')

