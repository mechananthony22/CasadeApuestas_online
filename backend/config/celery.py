import os
from celery import Celery

# Establece el módulo de configuración de Django por defecto para Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

app = Celery('fairbet')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tarea de prueba para verificar que el worker está funcionando correctamente."""
    print(f'Petición debug recibida: {self.request!r}')

