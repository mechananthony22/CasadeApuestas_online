from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def api_status_view(request):
    return JsonResponse({
        'status': 'online',
        'service': 'FairBet Lab API',
        'version': '1.0.0',
        'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.',
    })


urlpatterns = [
    path('admin/', admin.site.urls),

    # JWT endpoints
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token-obtain'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

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

    # Frontend: template views (login, register, dashboard)
    path('', include('frontend.urls')),
]
