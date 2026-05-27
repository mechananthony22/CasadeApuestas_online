from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def api_status_view(request):
    """Endpoint de estado del sistema y disclaimer educativo obligatorio."""
    return JsonResponse({
        'status': 'online',
        'service': 'FairBet Lab API',
        'version': '1.0.0',
        'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.',
    })


urlpatterns = [
    # Panel de administración de Django
    path('admin/', admin.site.urls),

    # Endpoint raíz con el disclaimer educativo obligatorio
    path('', api_status_view, name='api_status'),

    # Rutas de la API v1 - Fase 1: Usuarios y KYC
    path('api/v1/', include('users.urls')),

    # Rutas de la API v1 - Fase 2: Wallet y Partida Doble
    path('api/v1/', include('wallet.urls')),
]
