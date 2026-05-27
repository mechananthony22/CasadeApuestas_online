# -*- coding: utf-8 -*-
# Serializadores DRF para límites de juego responsable en FairBet Lab
from rest_framework import serializers
from responsible.models import ResponsibleGamingLimit

class ResponsibleGamingLimitSerializer(serializers.ModelSerializer):
    """
    Serializador para ver y actualizar límites de juego responsable.
    """
    class Meta:
        model = ResponsibleGamingLimit
        fields = [
            'daily_limit', 'weekly_limit', 'monthly_limit',
            'pending_daily_limit', 'pending_weekly_limit', 'pending_monthly_limit',
            'cooldown_until_daily', 'cooldown_until_weekly', 'cooldown_until_monthly'
        ]
        read_only_fields = [
            'pending_daily_limit', 'pending_weekly_limit', 'pending_monthly_limit',
            'cooldown_until_daily', 'cooldown_until_weekly', 'cooldown_until_monthly'
        ]

    def validate_limit_amount(self, value):
        """Valida que el límite sea mayor a cero si se especifica."""
        if value is not None and value <= 0:
            raise serializers.ValidationError("El límite de depósito debe ser un monto mayor a cero.")
        return value

    def validate_daily_limit(self, value):
        return self.validate_limit_amount(value)

    def validate_weekly_limit(self, value):
        return self.validate_limit_amount(value)

    def validate_monthly_limit(self, value):
        return self.validate_limit_amount(value)
