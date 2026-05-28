# -*- coding: utf-8 -*-
# Controladores basados en Django REST Framework para la gestión de fraude en FairBet Lab
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from fraud.models import SuspiciousActivity
from fraud.serializers import SuspiciousActivitySerializer

class SuspiciousActivityViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet administrativo para visualizar y gestionar alertas de actividad sospechosa (Fase 9). Solo accesible para operadores del sistema (`IsAdminUser`).
    """
    
    queryset = SuspiciousActivity.objects.all().select_related('user', 'resolved_by').order_by('-created_at')
    serializer_class = SuspiciousActivitySerializer
    permission_classes = [permissions.IsAdminUser]

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        alert = self.get_object()
        
        # Validar el nuevo estado recibido en el body
        new_status = request.data.get('status', '').strip()
        if new_status not in [SuspiciousActivity.STATUS_REVIEWED, SuspiciousActivity.STATUS_DISMISSED]:
            return Response(
                {'error': f"El estado debe ser '{SuspiciousActivity.STATUS_REVIEWED}' o '{SuspiciousActivity.STATUS_DISMISSED}'."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if alert.status != SuspiciousActivity.STATUS_PENDING:
            return Response(
                {'error': "Esta alerta ya ha sido auditada previamente y se encuentra cerrada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            alert.status = new_status
            alert.resolved_at = timezone.now()
            alert.resolved_by = request.user
            alert.save(update_fields=['status', 'resolved_at', 'resolved_by'])

        serializer = self.get_serializer(alert)
        return Response(serializer.data, status=status.HTTP_200_OK)
