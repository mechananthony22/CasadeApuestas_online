# -*- coding: utf-8 -*-
# Vistas basadas en Django REST Framework para controles de juego responsable
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from responsible.models import ResponsibleGamingLimit
from responsible.serializers import ResponsibleGamingLimitSerializer

class ResponsibleGamingLimitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        limit_obj, _ = ResponsibleGamingLimit.objects.get_or_create(user=request.user)
        
        # Aplicar límites pendientes expirados antes de retornar
        limit_obj.clean_expired_cooldowns()
        
        serializer = ResponsibleGamingLimitSerializer(limit_obj)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        limit_obj, _ = ResponsibleGamingLimit.objects.get_or_create(user=request.user)
        
        # Aplicar límites pendientes expirados primero
        limit_obj.clean_expired_cooldowns()

        # Validar formato e importes positivos
        serializer = ResponsibleGamingLimitSerializer(limit_obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Reglas de negocio para cada límite
        with transaction.atomic():
            now = timezone.now()
            cooldown_period = timezone.timedelta(hours=24)
            mensajes_alerta = []

            for field in ['daily_limit', 'weekly_limit', 'monthly_limit']:
                if field in request.data:
                    # El serializer ya parseó el valor a Decimal o None
                    raw_val = request.data[field]
                    new_val = Decimal(str(raw_val)) if raw_val is not None else None
                    current_val = getattr(limit_obj, field)
                    suffix = field.split('_')[0]

                    # Caso A: Imposición inicial de límite (antes ilimitado)
                    # Se considera una restricción inmediata y se aplica al instante.
                    if current_val is None and new_val is not None:
                        setattr(limit_obj, field, new_val)
                        setattr(limit_obj, f"pending_{field}", None)
                        setattr(limit_obj, f"cooldown_until_{suffix}", None)
                        mensajes_alerta.append(f"Límite {field} establecido inmediatamente en {new_val} fichas.")

                    # Caso B: Reducción del límite actual
                    # Se considera una restricción inmediata y se aplica al instante.
                    elif current_val is not None and new_val is not None and new_val < current_val:
                        setattr(limit_obj, field, new_val)
                        setattr(limit_obj, f"pending_{field}", None)
                        setattr(limit_obj, f"cooldown_until_{suffix}", None)
                        mensajes_alerta.append(f"Límite {field} reducido inmediatamente a {new_val} fichas.")

                    # Caso C: Incremento o eliminación del límite actual (menos restrictivo)
                    # Requiere obligatoriamente cooldown preventivo de 24h
                    elif (current_val is not None and new_val is None) or (current_val is not None and new_val is not None and new_val > current_val):
                        setattr(limit_obj, f"pending_{field}", new_val)
                        setattr(limit_obj, f"cooldown_until_{suffix}", now + cooldown_period)
                        tipo = "desactivación" if new_val is None else f"aumento a {new_val} fichas"
                        mensajes_alerta.append(f"La solicitud de {tipo} para el límite {field} requiere un cooldown preventivo de 24 horas.")

            limit_obj.save()

        # Serializar salida actualizada
        output_serializer = ResponsibleGamingLimitSerializer(limit_obj)
        return Response({
            'mensaje': 'Configuración de límites procesada de acuerdo a las políticas de juego responsable.',
            'detalles': mensajes_alerta,
            'limites': output_serializer.data,
            'disclaimer': 'Juego responsable: El juego en exceso puede causar adicción. Juega con moderación.'
        }, status=status.HTTP_200_OK)
