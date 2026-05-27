# -*- coding: utf-8 -*-
# Modelos de base de datos para límites de depósitos y autoexclusión de juego responsable en FairBet Lab
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal

class ResponsibleGamingLimit(models.Model):
    """
    Representa los límites de recargas virtuales configurados por el usuario
    para fomentar el juego responsable (Reglamento Ley 31557).
    Soporta cooldowns de 24 horas para incrementos o desactivación.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='responsible_limit',
        verbose_name='Usuario'
    )
    
    # Límites activos actualmente (diario, semanal, mensual)
    daily_limit = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Límite Diario Activo'
    )
    weekly_limit = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Límite Semanal Activo'
    )
    monthly_limit = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Límite Mensual Activo'
    )
    
    # Límites pendientes (a la espera de que expire el cooldown de 24h)
    pending_daily_limit = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Límite Diario Pendiente'
    )
    pending_weekly_limit = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Límite Semanal Pendiente'
    )
    pending_monthly_limit = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Límite Mensual Pendiente'
    )
    
    # Marcas de tiempo de cooldown (cuándo expira el período de 24h)
    cooldown_until_daily = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Cooldown Diario Hasta'
    )
    cooldown_until_weekly = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Cooldown Semanal Hasta'
    )
    cooldown_until_monthly = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Cooldown Mensual Hasta'
    )
    
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')

    class Meta:
        verbose_name = 'Límite de Juego Responsable'
        verbose_name_plural = 'Límites de Juego Responsable'

    def __str__(self):
        return f"Límites de {self.user.username}"

    def clean_expired_cooldowns(self):
        """
        Aplica de forma transparente cualquier límite pendiente cuyo cooldown de 24h
        haya expirado en el momento de la llamada.
        """
        now = timezone.now()
        updated = False

        if self.cooldown_until_daily and self.cooldown_until_daily <= now:
            self.daily_limit = self.pending_daily_limit
            self.pending_daily_limit = None
            self.cooldown_until_daily = None
            updated = True
            
        if self.cooldown_until_weekly and self.cooldown_until_weekly <= now:
            self.weekly_limit = self.pending_weekly_limit
            self.pending_weekly_limit = None
            self.cooldown_until_weekly = None
            updated = True
            
        if self.cooldown_until_monthly and self.cooldown_until_monthly <= now:
            self.monthly_limit = self.pending_monthly_limit
            self.pending_monthly_limit = None
            self.cooldown_until_monthly = None
            updated = True

        if updated:
            self.save()


class AutoExclusion(models.Model):
    """
    Representa una autoexclusión temporal o permanente activa para un usuario.
    Regulado por la Ley 31557 peruana.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='auto_exclusion',
        verbose_name='Usuario'
    )
    
    # Fecha hasta la cual la cuenta está suspendida.
    # Si es null, la autoexclusión es permanente/indefinida.
    excluded_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Excluido Hasta'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Creación')

    class Meta:
        verbose_name = 'Autoexclusión'
        verbose_name_plural = 'Autoexclusiones'

    def __str__(self):
        tipo = f"Temporal hasta {self.excluded_until}" if self.excluded_until else "Permanente / Indefinida"
        return f"Autoexclusión de {self.user.username} ({tipo})"

    @property
    def is_active(self):
        """
        Verifica si la autoexclusión sigue vigente.
        """
        if self.excluded_until is None:
            return True
        return self.excluded_until > timezone.now()
