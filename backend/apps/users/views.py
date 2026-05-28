# -*- coding: utf-8 -*-
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile
from .serializers import RegistroUsuarioSerializer, PerfilUsuarioSerializer
from .validators import validar_dni_peruano


@method_decorator(csrf_exempt, name='dispatch')
class RegistroView(APIView):
    # Este endpoint es público porque el usuario aún no tiene cuenta
    permission_classes = [AllowAny]

    def post(self, request):
        """Procesa el registro de un nuevo usuario con su perfil KYC."""
        serializer = RegistroUsuarioSerializer(data=request.data)

        if not serializer.is_valid():
            # Devuelve los errores de validación con sus respectivos campos
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Crea el usuario + perfil en una sola transacción atómica
        usuario = serializer.save()

        # Obtener el perfil recién creado para la respuesta
        perfil = usuario.profile

        # --- CONTROLES ANTI-FRAUDE: Registrar IP en registro ---
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '127.0.0.1')).split(',')[0].strip()
        from fraud.services import FraudDetector
        FraudDetector.log_and_check_ip(usuario, ip)
        # --- FIN CONTROLES ANTI-FRAUDE ---

        return Response(
            {
                'mensaje': 'Usuario registrado exitosamente. Tu cuenta está pendiente de verificación de DNI.',
                'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.',
                'usuario': {
                    'id': usuario.id,
                    'username': usuario.username,
                    'email': usuario.email,
                    'estado': perfil.get_verification_status_display(),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class VerificarDniView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Procesa la verificación del DNI del usuario autenticado."""
        try:
            perfil = request.user.profile
        except UserProfile.DoesNotExist:
            return Response(
                {'error': 'Tu perfil de usuario no existe. Contacta al soporte.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Verificar que la cuenta no esté ya verificada
        if perfil.verification_status == UserProfile.STATUS_VERIFIED:
            return Response(
                {'mensaje': 'Tu cuenta ya fue verificada correctamente. Puedes apostar.'},
                status=status.HTTP_409_CONFLICT,
            )

        # Verificar que la cuenta no esté bloqueada
        if perfil.verification_status == UserProfile.STATUS_BLOCKED:
            return Response(
                {'error': 'Tu cuenta está bloqueada. Contacta al administrador del sistema.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Obtener el DNI enviado en el cuerpo de la petición
        dni_enviado = request.data.get('dni', '').strip()

        # Validar que el DNI recibido coincide con el registrado en el sistema
        if dni_enviado != perfil.dni:
            return Response(
                {'error': 'El DNI ingresado no coincide con el registrado en tu cuenta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            perfil.verification_status = UserProfile.STATUS_VERIFIED
            perfil.save(update_fields=['verification_status', 'updated_at'])

        return Response(
            {
                'mensaje': '¡DNI verificado exitosamente! Tu cuenta está activa para apostar.',
                'estado': perfil.get_verification_status_display(),
            },
            status=status.HTTP_200_OK,
        )


class MiPerfilView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Retorna los datos del perfil del usuario autenticado."""
        try:
            perfil = request.user.profile
        except UserProfile.DoesNotExist:
            return Response(
                {'error': 'Perfil no encontrado. Contacta al soporte.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # --- CONTROLES DE JUEGO RESPONSABLE ---
        # Restaurar dinámicamente el estado si la autoexclusión ya expiró
        from responsible.models import AutoExclusion
        try:
            auto_ex = request.user.auto_exclusion
            if not auto_ex.is_active and perfil.verification_status == UserProfile.STATUS_SELF_EXCLUDED:
                perfil.verification_status = UserProfile.STATUS_VERIFIED
                perfil.save(update_fields=['verification_status'])
        except AutoExclusion.DoesNotExist:
            pass
        # --- FIN CONTROLES DE JUEGO RESPONSABLE ---

        serializer = PerfilUsuarioSerializer(perfil)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AutoexclusionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Activa la autoexclusión temporal o permanente del usuario autenticado."""
        from django.utils import timezone
        from responsible.models import AutoExclusion

        try:
            perfil = request.user.profile
        except UserProfile.DoesNotExist:
            return Response(
                {'error': 'Perfil no encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Si ya está autoexcluido, no se puede autoexcluir dos veces
        if perfil.verification_status == UserProfile.STATUS_SELF_EXCLUDED:
            return Response(
                {'error': 'Tu cuenta ya está en estado de autoexclusión activa.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Si la cuenta está bloqueada, el admin debe gestionarlo
        if perfil.verification_status == UserProfile.STATUS_BLOCKED:
            return Response(
                {'error': 'Tu cuenta está bloqueada. Contacta al administrador.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Obtener los días de autoexclusión
        dias_raw = request.data.get('dias', None)
        excluded_until = None
        
        if dias_raw is not None:
            try:
                dias = int(dias_raw)
                if dias not in [7, 30, 90]:
                    return Response(
                        {'error': 'El período de autoexclusión temporal debe ser de 7, 30 o 90 días.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                excluded_until = timezone.now() + timezone.timedelta(days=dias)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'El parámetro "dias" debe ser un número entero (7, 30, 90) o null.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Cambiar el estado a autoexcluido dentro de una transacción atómica
        with transaction.atomic():
            perfil.verification_status = UserProfile.STATUS_SELF_EXCLUDED
            perfil.save(update_fields=['verification_status', 'updated_at'])
            
            # Registrar el modelo de autoexclusión en la app responsible
            AutoExclusion.objects.update_or_create(
                user=request.user,
                defaults={'excluded_until': excluded_until}
            )

        mensaje_periodo = f"temporal hasta {excluded_until}" if excluded_until else "permanente e indefinida"
        return Response(
            {
                'mensaje': (
                    f"Autoexclusión activada de forma {mensaje_periodo}. Tu cuenta ha sido suspendida inmediatamente. "
                    "Si deseas reactivarla, contacta al soporte después de que haya expirado el período de exclusión."
                ),
                'estado': perfil.get_verification_status_display(),
                'excluido_hasta': excluded_until.isoformat() if excluded_until else None
            },
            status=status.HTTP_200_OK,
        )
