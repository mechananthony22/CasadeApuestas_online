# -*- coding: utf-8 -*-
# Modelos de base de datos para detección de comportamiento sospechoso y anti-fraude en FairBet Lab
from django.db import models
from django.contrib.auth.models import User

class UserIpLog(models.Model):
    """
    Registra el historial de direcciones IP utilizadas por los usuarios durante transacciones clave (depósitos, apuestas) para detectar multicuenta.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ip_logs',
        verbose_name='Usuario'
    )
    
    ip_address = models.GenericIPAddressField(
        verbose_name='Dirección IP'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Registro'
    )

    class Meta:
        verbose_name = 'Registro de IP de Usuario'
        verbose_name_plural = 'Registros de IP de Usuarios'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - IP: {self.ip_address} el {self.created_at}"


class SuspiciousActivity(models.Model):
    """
    Consolida las alertas de fraude y comportamiento sospechoso detectadas en tiempo real. Sirve como bitácora para la revisión manual y cumplimiento normativo (Ley 31557).
    """
    
    TYPE_MULTIPLE_ACCOUNTS = 'MULTIPLE_ACCOUNTS_SAME_IP'
    TYPE_DEPOSIT_CASHOUT = 'IMMEDIATE_DEPOSIT_CASHOUT'
    TYPE_IDENTICAL_BET = 'IDENTICAL_BET_PATTERN'
    TYPE_BONUS_ABUSE = 'BONUS_ABUSE'
    
    TYPE_CHOICES = [
        (TYPE_MULTIPLE_ACCOUNTS, 'Múltiples Cuentas desde misma IP'),
        (TYPE_DEPOSIT_CASHOUT, 'Recarga seguida de Cash-out Inmediato'),
        (TYPE_IDENTICAL_BET, 'Patrón de Apuestas Idénticas en Grupo'),
        (TYPE_BONUS_ABUSE, 'Abuso de Bono por Apuestas Cruzadas'),
    ]
    
    SEVERITY_LOW = 'LOW'
    SEVERITY_MEDIUM = 'MEDIUM'
    SEVERITY_HIGH = 'HIGH'
    
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, 'Baja'),
        (SEVERITY_MEDIUM, 'Media'),
        (SEVERITY_HIGH, 'Alta'),
    ]
    
    STATUS_PENDING = 'PENDING'
    STATUS_REVIEWED = 'REVIEWED'
    STATUS_DISMISSED = 'DISMISSED'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendiente de Revisión'),
        (STATUS_REVIEWED, 'Revisada'),
        (STATUS_DISMISSED, 'Desestimada'),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='suspicious_activities',
        verbose_name='Usuario Sospechoso'
    )
    
    activity_type = models.CharField(
        max_length=50,
        choices=TYPE_CHOICES,
        verbose_name='Tipo de Actividad'
    )
    
    description = models.TextField(
        verbose_name='Descripción de la Alerta'
    )
    
    payload = models.JSONField(
        verbose_name='Detalles Forenses (JSON)'
    )
    
    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        verbose_name='Severidad de la Alerta'
    )
    
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name='Estado de la Alerta'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Detección'
    )
    
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de Resolución'
    )
    
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_fraud_alerts',
        verbose_name='Resuelta por Operador'
    )

    class Meta:
        verbose_name = 'Alerta de Fraude'
        verbose_name_plural = 'Alertas de Fraude'
        ordering = ['-created_at']

    def __str__(self):
        return f"Alerta {self.get_activity_type_display()} ({self.get_severity_display()}) - Estado: {self.get_status_display()}"
