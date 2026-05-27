# -*- coding: utf-8 -*-
# Enrutamiento de URLs para la aplicación responsible
from django.urls import path
from responsible.views import ResponsibleGamingLimitView

urlpatterns = [
    # Gestión de límites de depósito
    path('responsible/limits/', ResponsibleGamingLimitView.as_view(), name='responsible-limits'),
]
