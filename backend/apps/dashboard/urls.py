# -*- coding: utf-8 -*-
# Rutas de enrutamiento URL para la aplicación dashboard
from django.urls import path
from dashboard.views import OperatorDashboardView, MinceturReportView

urlpatterns = [
    # Métricas del Dashboard del Operador en vivo
    path('dashboard/metrics/', OperatorDashboardView.as_view(), name='operator-dashboard-metrics'),
    
    # Reporte mensual en cumplimiento reglamentario con MINCETUR (CSV)
    path('dashboard/mincetur-report/', MinceturReportView.as_view(), name='operator-mincetur-report'),
]
