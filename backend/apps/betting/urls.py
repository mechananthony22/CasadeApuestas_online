# -*- coding: utf-8 -*-
# Definición de rutas URL para la API de betting (Fase 3)
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from betting.views import EventViewSet, BetViewSet

# Enrutador automático de DRF para simplificar las rutas REST
router = DefaultRouter()
router.register(r'events', EventViewSet, basename='event')
router.register(r'bets', BetViewSet, basename='bet')

urlpatterns = [
    path('', include(router.urls)),
]
