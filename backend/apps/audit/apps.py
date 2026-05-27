from django.apps import AppConfig

class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'audit'
    verbose_name = 'Auditoría Criptográfica Inmutable'

    def ready(self):
        # Registrar y cargar los interceptores de señales al iniciar Django
        import audit.signals
