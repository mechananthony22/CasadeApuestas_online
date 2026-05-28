# -*- coding: utf-8 -*-
from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum
from decimal import Decimal


class LedgerEntry(models.Model):
    """
    Registro contable de partida doble para FairBet Lab.

    REGLA DE ORO: NUNCA almacenar el saldo del usuario en una columna.
    El saldo SIEMPRE se calcula como:
        balance = SUM(credits) - SUM(debits)

    Cada transacción financiera CREA MÍNIMO 2 entradas balanceadas:
        - Débito en cuenta A, Crédito en cuenta B
        - La suma algebraica de todas las entradas de una transacción = 0

    Cuentas contables:
        - wallet_usuario: Billetera del usuario (saldo disponible)
        - casa: Caja del operador
        - apuestas_pendientes: Fondos retenidos por apuestas activas
        - bonos: Fondos de bonos promocionales
    """

    # Tipo de cuenta contable
    class Account(models.TextChoices):
        WALLET_USUARIO = 'wallet_usuario', 'Billetera del Usuario'
        CASA = 'casa', 'Caja del Operador'
        APUESTAS_PENDIENTES = 'apuestas_pendientes', 'Fondo en Custodia de Apuestas'
        BONOS = 'bonos', 'Fondo de Bonos'

    # Dirección del movimiento
    class Direction(models.TextChoices):
        DEBIT = 'DEBIT', 'Débito (Salida)'
        CREDIT = 'CREDIT', 'Crédito (Entrada)'

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='ledger_entries',
        null=True,
        blank=True,
        verbose_name='Usuario',
        help_text='Usuario asociado (puede ser nulo para movimientos de la casa)'
    )

    account = models.CharField(
        max_length=30,
        choices=Account.choices,
        verbose_name='Cuenta Contable'
    )

    amount = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        verbose_name='Monto',
        help_text='Monto del movimiento (NUNCA usar float, siempre Decimal)'
    )

    direction = models.CharField(
        max_length=6,
        choices=Direction.choices,
        verbose_name='Dirección',
        help_text='DEBIT = sale dinero, CREDIT = entra dinero'
    )

    transaction_id = models.UUIDField(
        db_index=True,
        verbose_name='ID de Transacción',
        help_text='UUID que agrupa el débito y crédito de una misma operación'
    )

    description = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Descripción',
        help_text='Motivo legible del movimiento (ej: Recarga de fichas, Apuesta #123)'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Creación',
        help_text='Marca de tiempo inmutable del registro contable'
    )

    class Meta:
        verbose_name = 'Movimiento Contable'
        verbose_name_plural = 'Movimientos Contables'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['transaction_id']),
            models.Index(fields=['user', 'account']),
        ]

    def __str__(self):
        return (
            f"[{self.get_direction_display()}] "
            f"{self.account} - {self.amount} "
            f"(Tx: {self.transaction_id})"
        )

    @classmethod
    def get_user_balance(cls, user) -> Decimal:
        """
        Calcula el saldo disponible del usuario en su wallet.

        El saldo se obtiene dinámicamente como:
            SUM(CREDITs) - SUM(DEBITs)  para account='wallet_usuario'

        Esto garantiza que NUNCA hay un saldo almacenado
        que pueda desincronizarse.
        """
        credito = cls.objects.filter(
            user=user,
            account=cls.Account.WALLET_USUARIO,
            direction=cls.Direction.CREDIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        debito = cls.objects.filter(
            user=user,
            account=cls.Account.WALLET_USUARIO,
            direction=cls.Direction.DEBIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        return credito - debito

    @classmethod
    def get_house_balance(cls) -> Decimal:
        """
        Calcula el saldo de la cuenta de la casa.
        Útil para verificar el invariante global del sistema.
        """
        credito = cls.objects.filter(
            account=cls.Account.CASA,
            direction=cls.Direction.CREDIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        debito = cls.objects.filter(
            account=cls.Account.CASA,
            direction=cls.Direction.DEBIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        return credito - debito

    @classmethod
    def get_pending_bets_balance(cls) -> Decimal:
        """
        Calcula el total de fondos retenidos en apuestas pendientes.
        """
        credito = cls.objects.filter(
            account=cls.Account.APUESTAS_PENDIENTES,
            direction=cls.Direction.CREDIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        debito = cls.objects.filter(
            account=cls.Account.APUESTAS_PENDIENTES,
            direction=cls.Direction.DEBIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        return credito - debito

    @classmethod
    def get_system_zero_invariant(cls) -> Decimal:
        """
        Verifica el invariante global del sistema:
        La suma de todas las cuentas (wallet_usuario + casa + apuestas_pendientes + bonos)
        debe ser SIEMPRE igual a 0.0000.

        Este es el principio fundamental de la partida doble:
            Total débitos = Total créditos
        """
        total_debits = cls.objects.filter(
            direction=cls.Direction.DEBIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        total_credits = cls.objects.filter(
            direction=cls.Direction.CREDIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        return total_credits - total_debits


class UserBonus(models.Model):
    """
    Representa un bono de bienvenida u otra promoción otorgada a un usuario.
    Registra el monto del bono, el rollover requerido y el avance acumulado (Ley 31557).
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='promo_bonus',
        verbose_name='Usuario'
    )
    bonus_amount = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        verbose_name='Monto del Bono'
    )
    rollover_multiplier = models.IntegerField(
        default=6,
        verbose_name='Multiplicador de Rollover'
    )
    required_turnover = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        verbose_name='Monto Total Requerido'
    )
    current_turnover = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal('0.0000'),
        verbose_name='Rollover Acumulado'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='¿Bono Activo?'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Adquisición'
    )

    class Meta:
        verbose_name = 'Bono de Usuario'
        verbose_name_plural = 'Bonos de Usuarios'

    def __str__(self):
        return f"Bono de {self.user.username} (Falta apostar: S/ {self.remaining_rollover:.2f})"

    @property
    def remaining_rollover(self) -> Decimal:
        """
        Calcula el monto de rollover restante que debe cumplir el usuario antes de retirar.
        """
        return max(Decimal('0.0000'), self.required_turnover - self.current_turnover)

