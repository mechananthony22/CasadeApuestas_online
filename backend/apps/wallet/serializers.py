# -*- coding: utf-8 -*-
from decimal import Decimal
from django.contrib.auth.models import User
from rest_framework import serializers

from .models import LedgerEntry


class DepositoSerializer(serializers.Serializer):
    """
    Serializer para la recarga simulada de fichas (depósito).

    Recibe el monto a depositar y opcionalmente una descripción.
    Valida que el monto sea positivo y no exceda los límites
    configurados en las variables de entorno del sistema.
    """

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
    """
    Serializer para el retiro simulado de fichas.

    Recibe el monto a retirar. Valida que sea positivo y
    que el usuario tenga saldo suficiente (la vista lo verifica
    con select_for_update dentro de una transacción atómica).
    """

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
    """
    Serializer de solo lectura para consultar el saldo del usuario.

    Expone el saldo calculado dinámicamente mediante SUM,
    el total depositado, el total retirado y el historial
    de movimientos recientes.
    """

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

    username = serializers.CharField(
        source='user.username',
        read_only=True,
        help_text='Nombre del usuario'
    )


class LedgerEntrySerializer(serializers.ModelSerializer):
    """
    Serializer de solo lectura para listar movimientos del libro contable.
    """

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
    """
    Serializer para la transferencia interna de fichas virtuales entre usuarios.

    Valida que el destinatario exista, que no sea el mismo usuario remitente,
    que ambos usuarios estén verificados y no autoexcluidos, y que el monto sea positivo.
    """

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
        """
        Valida las reglas de negocio para la transferencia interna:
        1. No transferir dinero a la propia cuenta del usuario.
        2. El usuario remitente debe estar verificado y no autoexcluido.
        3. El usuario destinatario debe estar verificado y no autoexcluido.
        """
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

