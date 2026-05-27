# -*- coding: utf-8 -*-
# Enrutamiento de URLs de WebSockets para la aplicación betting
from django.urls import re_path
from betting import consumers

websocket_urlpatterns = [
    # Canal para las actualizaciones de marcador y cuotas de un partido específico
    re_path(r'^ws/events/(?P<event_id>\d+)/$', consumers.EventConsumer.as_asgi()),
    
    # Canal privado para notificaciones del usuario autenticado (apuestas y transacciones)
    re_path(r'^ws/notifications/$', consumers.UserNotificationConsumer.as_asgi()),
]
