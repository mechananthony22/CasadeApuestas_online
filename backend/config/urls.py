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

    # Rutas de la API v1 - Fase 3: Catálogo de Eventos y Cuotas
    path('api/v1/betting/', include('betting.urls')),

    # Rutas de la API v1 - Fase 7: Juego Responsable
    path('api/v1/', include('responsible.urls')),

    # Rutas de la API v1 - Fase 8: Auditoría inmutable
    path('api/v1/', include('audit.urls')),

    # Rutas de la API v1 - Fase 9: Anti-fraude básico
    path('api/v1/', include('fraud.urls')),

    # Rutas de la API v1 - Fase 10: Dashboard del operador y Reporte MINCETUR
    path('api/v1/', include('dashboard.urls')),
]
