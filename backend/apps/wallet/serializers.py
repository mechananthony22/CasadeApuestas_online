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
