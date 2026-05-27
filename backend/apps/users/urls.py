# -*- coding: utf-8 -*-
"""
Configuración de rutas URL para la aplicación de usuarios (Fase 1).

Estas URLs mapean los endpoints del plan de desarrollo a sus vistas correspondientes.
Todas estas rutas son de tipo HTTP síncrono, siguiendo la Regla de Oro del proyecto:
    - HTTP → operaciones que modifican datos del usuario o la cuenta.
    - WebSocket → solo actualizaciones de cuotas y marcadores en vivo.
"""
from django.urls import path
from .views import RegistroView, VerificarDniView, MiPerfilView, AutoexclusionView

# Se prefija con 'api/v1/' desde config/urls.py (ver su inclusión)
urlpatterns = [
    # POST /api/v1/auth/register/ → Registro de nuevo usuario con KYC
    path('auth/register/', RegistroView.as_view(), name='auth-register'),

    # POST /api/v1/auth/verify-dni/ → Verificación del DNI con Módulo-11
    path('auth/verify-dni/', VerificarDniView.as_view(), name='auth-verify-dni'),

    # GET /api/v1/users/me/ → Consulta del perfil del usuario autenticado
    path('users/me/', MiPerfilView.as_view(), name='users-me'),

    # POST /api/v1/users/self-exclude/ → Autoexclusión del usuario (Ley 31557 Art. 12)
    path('users/self-exclude/', AutoexclusionView.as_view(), name='users-self-exclude'),
]
