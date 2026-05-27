# -*- coding: utf-8 -*-
# Vistas basadas en Django REST Framework para la verificación de integridad de la cadena de auditoría
import hashlib
import json
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from audit.models import AuditLogEntry

logger = logging.getLogger(__name__)

class AuditVerifyView(APIView):
    """
    APIView de uso exclusivo administrativo (Ley 31557) para verificar 
    la integridad criptográfica de la cadena de logs de auditoría (Blockchain append-only).
    
    Barre secuencialmente todos los registros y recalcula el hash SHA-256
    para detectar manipulaciones o eliminaciones no autorizadas.
    """
    
    # Solo accesible para administradores
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """
        GET /api/v1/audit/verify/
        Verifica criptográficamente toda la cadena de auditoría.
        """
        logs = AuditLogEntry.objects.all().order_by('id')
        total_records = logs.count()
        
        # Si no hay registros, la cadena está técnicamente vacía pero íntegra
        if total_records == 0:
            return Response({
                'status': 'verified',
                'mensaje': 'La bitácora de auditoría está vacía y se encuentra íntegra.',
                'registros_auditados': 0,
                'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.'
            }, status=status.HTTP_200_OK)

        expected_prev_hash = '0' * 64
        
        for idx, log in enumerate(logs):
            # 1. Validar que el anterior hash guardado coincida con lo esperado en la secuencia
            if log.previous_hash != expected_prev_hash:
                logger.error(f"INTEGRIDAD ROTA: Log #{log.id} tiene un hash previo inválido. Esperado: {expected_prev_hash}, Obtenido: {log.previous_hash}")
                return Response({
                    'status': 'compromised',
                    'mensaje': 'Fraude detectado: La secuencia de hashes de la cadena de auditoría ha sido rota.',
                    'registro_comprometido_id': log.id,
                    'event_type': log.event_type,
                    'created_at': log.created_at.isoformat() if log.created_at else None
                }, status=status.HTTP_400_BAD_REQUEST)

            # 2. Recalcular el hash del bloque actual de forma canónica
            try:
                canonical_payload = json.dumps(log.payload, sort_keys=True)
                sha = hashlib.sha256()
                sha.update((expected_prev_hash + canonical_payload).encode('utf-8'))
                recalculated_hash = sha.hexdigest()
            except Exception as e:
                logger.error(f"ERROR AL VERIFICAR: No se pudo serializar el payload del log #{log.id}: {str(e)}")
                return Response({
                    'status': 'error',
                    'mensaje': f'Error interno al verificar la integridad del registro #{log.id}.'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 3. Validar que el hash actual coincida con el hash recalculado
            if log.current_hash != recalculated_hash:
                logger.error(f"INTEGRIDAD ROTA: Log #{log.id} ha sido manipulado. Guardado: {log.current_hash}, Recalculado: {recalculated_hash}")
                return Response({
                    'status': 'compromised',
                    'mensaje': 'Fraude detectado: El contenido del payload o los hashes han sido alterados.',
                    'registro_comprometido_id': log.id,
                    'event_type': log.event_type,
                    'created_at': log.created_at.isoformat() if log.created_at else None
                }, status=status.HTTP_400_BAD_REQUEST)

            # Para el siguiente registro, el hash actual de este registro se vuelve el anterior esperado
            expected_prev_hash = log.current_hash

        logger.info(f"VERIFICACIÓN EXITOSA: La bitácora de auditoría es íntegra. {total_records} registros verificados.")
        return Response({
            'status': 'verified',
            'mensaje': 'La cadena de auditoría inmutable es 100% íntegra y segura.',
            'registros_auditados': total_records,
            'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.'
        }, status=status.HTTP_200_OK)
