# -*- coding: utf-8 -*-
# Definición de rutas URL para la aplicación audit (Fase 8)
from django.urls import path
from audit.views import AuditVerifyView

urlpatterns = [
    # GET /api/v1/audit/verify/ → Verificación forense de la cadena de bloques
    path('audit/verify/', AuditVerifyView.as_view(), name='audit-verify'),
]
