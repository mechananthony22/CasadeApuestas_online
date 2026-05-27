# -*- coding: utf-8 -*-
# Rutas de enrutamiento URL de Django REST Framework para la aplicación fraud
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from fraud.views import SuspiciousActivityViewSet

# Enrutador automático de DRF para alertas de comportamiento sospechoso
router = DefaultRouter()
router.register(r'fraud/alerts', SuspiciousActivityViewSet, basename='fraud-alerts')

urlpatterns = [
    path('', include(router.urls)),
]
