# -*- coding: utf-8 -*-
"""
Modelos de base de datos para la gestión de usuarios, KYC y seguridad de cuentas.

Este módulo define el perfil extendido del usuario de Django (UserProfile)
que almacena la información regulatoria requerida por la Ley 31557 y el
reglamento DS 005-2023-MINCETUR: DNI peruano validado, fecha de nacimiento
verificada y el estado de verificación de la cuenta.
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    """
    Perfil extendido del usuario con datos de KYC (Conoce a Tu Cliente).

    Este modelo extiende al modelo User nativo de Django con los datos
    regulatorios obligatorios para operar en la plataforma educativa FairBet Lab.

    Estados del ciclo de vida de la cuenta:
        - pending_verification: Cuenta creada pero DNI aún no validado.
        - verified: DNI y mayoría de edad confirmados. Puede apostar.
        - blocked: Cuenta bloqueada por el administrador del sistema.
        - self_excluded: El propio usuario solicitó la exclusión temporal o indefinida.
    """

    # Estados posibles de verificación de la cuenta (Requisito Ley 31557 Art. 8)
    STATUS_PENDING = 'pending_verification'
    STATUS_VERIFIED = 'verified'
    STATUS_BLOCKED = 'blocked'
    STATUS_SELF_EXCLUDED = 'self_excluded'

    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pendiente de Verificación'),
        (STATUS_VERIFIED, 'Verificado'),
        (STATUS_BLOCKED, 'Bloqueado por Administrador'),
        (STATUS_SELF_EXCLUDED, 'Autoexcluido por el Usuario'),
    )

    # Relación uno a uno con el modelo User nativo de Django
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Usuario'
    )

    # DNI peruano: campo de texto de 8 dígitos, único por sistema
    dni = models.CharField(
        max_length=8,
        unique=True,
        verbose_name='DNI Peruano',
        help_text='Documento Nacional de Identidad peruano de 8 dígitos'
    )

    # Fecha de nacimiento para validar mayoría de edad (≥ 18 años)
    birth_date = models.DateField(
        verbose_name='Fecha de Nacimiento',
        help_text='Se requiere tener mínimo 18 años para operar en la plataforma'
    )

    # Estado actual de verificación de la cuenta
    verification_status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name='Estado de Verificación'
    )

    # Campos de trazabilidad temporal (inmutables)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')

    class Meta:
        verbose_name = 'Perfil de Usuario'
        verbose_name_plural = 'Perfiles de Usuario'

    def __str__(self):
        return f'Perfil de {self.user.username} [{self.get_verification_status_display()}]'

    @property
    def is_adult(self):
        """
        Verifica si el usuario tiene 18 años o más.

        Calcula la edad exacta comparando la fecha de nacimiento con
        la fecha actual (en zona horaria de Lima, Perú).

        Returns:
            bool: True si el usuario tiene ≥ 18 años, False en caso contrario.
        """
        hoy = timezone.now().date()
        edad = (
            hoy.year - self.birth_date.year
            - ((hoy.month, hoy.day) < (self.birth_date.month, self.birth_date.day))
        )
        return edad >= 18

    @property
    def is_verified(self):
        """Retorna True si la cuenta está en estado 'verificado' y puede apostar."""
        return self.verification_status == self.STATUS_VERIFIED

    @property
    def is_able_to_bet(self):
        """
        Verifica si el usuario tiene permiso de realizar apuestas.

        El usuario puede apostar únicamente si:
        1. Su estado de verificación es 'verified'.
        2. NO está autoexcluido.
        3. NO está bloqueado por el administrador.

        Returns:
            bool: True si puede apostar, False si está restringido.
        """
        return self.verification_status == self.STATUS_VERIFIED
