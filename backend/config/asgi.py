import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

from betting.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')

# Inicializa la aplicación ASGI de Django temprano para asegurar que el registro de apps (AppRegistry) esté cargado
django_asgi_app = get_asgi_application()

# ProtocolTypeRouter enrutará el tráfico estándar HTTP mediante django_asgi_app
# y enrutará el tráfico WebSocket cuando los enrutadores sean definidos en la Fase 6.
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})

