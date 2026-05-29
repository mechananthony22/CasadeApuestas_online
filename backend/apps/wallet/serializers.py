# -*- coding: utf-8 -*-
from decimal import Decimal
from django.contrib.auth.models import User
from rest_framework import serializers

from .models import LedgerEntry


class DepositoSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal('0.0001'),
        help_text='Monto de fichas a depositar (mínimo 0.0001)'
    )

    description = serializers.CharField(
        required=False,
        default='Recarga de fichas virtuales',
        max_length=255,
        help_text='Motivo opcional del depósito'
    )


class RetiroSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal('0.0001'),
        help_text='Monto de fichas a retirar (mínimo 0.0001)'
    )

    description = serializers.CharField(
        required=False,
        default='Retiro simulado de fichas',
        max_length=255,
        help_text='Motivo opcional del retiro'
    )


class BalanceSerializer(serializers.Serializer):
    balance = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Saldo disponible calculado como SUM(credits) - SUM(debits)'
    )

    total_depositado = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Total histórico depositado'
    )

    total_retirado = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Total histórico retirado'
    )

    total_apostado = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Total apostado'
    )

    total_ganado = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Total ganado'
    )

    total_perdido = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Total perdido'
    )

    ganancia_neta_apuestas = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Ganancia neta en apuestas'
    )

    total_pendiente = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Total retenido en apuestas pendientes'
    )

    transferencias_enviadas = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Total enviado en transferencias'
    )

    transferencias_recibidas = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Total recibido en transferencias'
    )

    bonos_recibidos = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        read_only=True,
        help_text='Total de bonos recibidos'
    )

    username = serializers.CharField(
        source='user.username',
        read_only=True,
        help_text='Nombre del usuario'
    )


class LedgerEntrySerializer(serializers.ModelSerializer):
    direction_display = serializers.CharField(
        source='get_direction_display',
        read_only=True
    )
    account_display = serializers.CharField(
        source='get_account_display',
        read_only=True
    )

    class Meta:
        model = LedgerEntry
        fields = [
            'id',
            'transaction_id',
            'account',
            'account_display',
            'amount',
            'direction',
            'direction_display',
            'description',
            'created_at',
        ]
        read_only_fields = fields


class TransferenciaSerializer(serializers.Serializer):

    to_username = serializers.CharField(
        max_length=150,
        help_text='Nombre de usuario del destinatario'
    )

    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=4,
        min_value=Decimal('0.0001'),
        help_text='Monto a transferir (mínimo 0.0001)'
    )

    description = serializers.CharField(
        required=False,
        default='Transferencia interna de fichas',
        max_length=255,
        help_text='Descripción opcional de la transferencia'
    )

    def validate_to_username(self, value):
        """
        Valida que el usuario destinatario exista en el sistema.
        """
        username = value.strip()
        if not User.objects.filter(username=username).exists():
            raise serializers.ValidationError("El usuario destinatario no existe.")
        return username

    def validate(self, attrs):
        sender = self.context['request'].user
        to_username = attrs['to_username']

        if sender.username == to_username:
            raise serializers.ValidationError({
                "to_username": "No puedes transferir fondos a tu propia cuenta."
            })

        receiver = User.objects.get(username=to_username)

        # Importar modelos requeridos localmente para evitar dependencias circulares
        from users.models import UserProfile
        from responsible.models import AutoExclusion

        # Validaciones del Remitente (Sender)
        try:
            sender_profile = sender.profile
            if sender_profile.verification_status != UserProfile.STATUS_VERIFIED:
                raise serializers.ValidationError({
                    "non_field_errors": "Tu cuenta debe estar verificada para realizar transferencias."
                })
        except UserProfile.DoesNotExist:
            raise serializers.ValidationError({
                "non_field_errors": "Tu cuenta no posee un perfil KYC de verificación completo."
            })

        try:
            sender_autoex = sender.auto_exclusion
            if sender_autoex.is_active:
                raise serializers.ValidationError({
                    "non_field_errors": "No puedes transferir fondos porque tu cuenta está autoexcluida."
                })
        except AutoExclusion.DoesNotExist:
            pass

        # Validaciones del Destinatario (Receiver)
        try:
            receiver_profile = receiver.profile
            if receiver_profile.verification_status != UserProfile.STATUS_VERIFIED:
                raise serializers.ValidationError({
                    "to_username": "El destinatario debe tener su cuenta verificada para recibir fondos."
                })
        except UserProfile.DoesNotExist:
            raise serializers.ValidationError({
                "to_username": "El destinatario no posee un perfil KYC de verificación completo."
            })

        try:
            receiver_autoex = receiver.auto_exclusion
            if receiver_autoex.is_active:
                raise serializers.ValidationError({
                    "to_username": "El destinatario no puede recibir fondos porque su cuenta está autoexcluida."
                })
        except AutoExclusion.DoesNotExist:
            pass

        attrs['receiver_user'] = receiver
        return attrs

