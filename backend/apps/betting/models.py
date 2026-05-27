# -*- coding: utf-8 -*-
# Modelos de base de datos para eventos, mercados, cuotas y apuestas en FairBet Lab
from django.db import models
from django.contrib.auth.models import User

class League(models.Model):
    """
    Representa una liga de fútbol importada de la API externa (API-Football).
    """
    api_id = models.IntegerField(unique=True, help_text="ID oficial de la liga en API-Football")
    name = models.CharField(max_length=100, help_text="Nombre de la liga")
    country = models.CharField(max_length=100, help_text="País de la liga")
    logo_url = models.URLField(max_length=500, null=True, blank=True, help_text="URL del logo de la liga")

    def __str__(self):
        return f"{self.name} ({self.country})"


class Team(models.Model):
    """
    Representa un equipo de fútbol importado de la API externa (API-Football).
    """
    api_id = models.IntegerField(unique=True, help_text="ID oficial del equipo en API-Football")
    name = models.CharField(max_length=100, help_text="Nombre del equipo")
    logo_url = models.URLField(max_length=500, null=True, blank=True, help_text="URL del escudo del equipo")

    def __str__(self):
        return self.name


class Event(models.Model):
    """
    Representa un partido de fútbol (evento deportivo) programado, en vivo o finalizado.
    """
    STATUS_CHOICES = (
        ('scheduled', 'Programado'),
        ('in_play', 'En Vivo'),
        ('finished', 'Finalizado'),
        ('suspended', 'Suspendido'),
        ('cancelled', 'Anulado'),
    )

    api_id = models.IntegerField(unique=True, help_text="ID oficial del partido en API-Football")
    league = models.ForeignKey(League, on_delete=models.PROTECT, related_name='events', help_text="Liga a la que pertenece el evento")
    home_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name='home_events', help_text="Equipo local")
    away_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name='away_events', help_text="Equipo visitante")
    starts_at = models.DateTimeField(help_text="Fecha y hora de inicio del evento")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled', help_text="Estado actual del evento")
    home_score = models.IntegerField(null=True, blank=True, help_text="Goles anotados por el equipo local")
    away_score = models.IntegerField(null=True, blank=True, help_text="Goles anotados por el equipo visitante")
    last_updated = models.DateTimeField(auto_now=True, help_text="Última actualización local del evento")

    def __str__(self):
        return f"{self.home_team} vs {self.away_team} - {self.get_status_display()}"


class Market(models.Model):
    """
    Representa un mercado de apuestas asociado a un evento deportivo (ejemplo: 1X2, Over/Under 2.5, BTTS).
    """
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='markets', help_text="Evento al que pertenece el mercado")
    name = models.CharField(max_length=100, help_text="Nombre del mercado de apuestas (ej. 1X2, Over/Under 2.5, BTTS)")
    is_active = models.BooleanField(default=True, help_text="Indica si el mercado está abierto para recibir apuestas")

    def __str__(self):
        return f"{self.name} - Evento ID: {self.event.api_id}"


class Selection(models.Model):
    """
    Representa una opción o selección dentro de un mercado con su respectiva cuota (odd).
    """
    market = models.ForeignKey(Market, on_delete=models.CASCADE, related_name='selections', help_text="Mercado al que pertenece la selección")
    name = models.CharField(max_length=100, help_text="Nombre de la opción (ej. Gana Local, Empate, Gana Visitante, Over, Under, Yes, No)")
    odds = models.DecimalField(max_digits=10, decimal_places=4, help_text="Valor decimal de la cuota con el margen de la casa aplicado")
    is_active = models.BooleanField(default=True, help_text="Indica si esta selección específica está habilitada para apostar")

    def __str__(self):
        return f"{self.name} @ {self.odds:.4f} ({self.market.name})"


class Bet(models.Model):
    """
    Representa un boleto o ticket de apuesta colocado por un usuario.
    Soporta tanto apuestas simples como combinadas (acumuladas).
    """
    STATUS_CHOICES = (
        ('accepted', 'Aceptada'),
        ('won', 'Ganada'),
        ('lost', 'Perdida'),
        ('cancelled', 'Cancelada / Anulada'),
        ('cashed_out', 'Cobro Anticipado'),
    )

    TYPE_CHOICES = (
        ('simple', 'Simple'),
        ('accumulator', 'Combinada'),
    )

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='bets', help_text="Usuario que realizó la apuesta")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='accepted', help_text="Estado actual del boleto de apuesta")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='simple', help_text="Tipo de apuesta (simple o combinada)")
    stake = models.DecimalField(max_digits=18, decimal_places=4, help_text="Monto de fichas apostado")
    potential_payout = models.DecimalField(max_digits=18, decimal_places=4, help_text="Retorno potencial calculado")
    idempotency_key = models.UUIDField(unique=True, db_index=True, help_text="Clave UUID única para evitar cobros o registros dobles")
    created_at = models.DateTimeField(auto_now_add=True, help_text="Fecha y hora de colocación de la apuesta")
    settled_at = models.DateTimeField(null=True, blank=True, help_text="Fecha y hora en la que se liquidó la apuesta")

    def __str__(self):
        return f"Apuesta #{self.id} - {self.user.username} ({self.get_type_display()}) [{self.get_status_display()}]"

    def settle_as_won(self, payout_amount, transaction_id):
        """
        Liquida la apuesta en estado GANADA de forma transaccional.
        REGLA DE PARTIDA DOBLE:
        - Débito apuestas_pendientes (sale dinero retenido) -> DEBIT, monto=stake
        - Débito casa (la casa aporta la ganancia neta) -> DEBIT, monto=payout_amount - stake
        - Crédito wallet_usuario (recibe el retorno) -> CREDIT, monto=payout_amount
        """
        from wallet.models import LedgerEntry
        from django.utils import timezone

        if self.status != 'accepted':
            raise ValueError(f"No se puede liquidar como ganada una apuesta en estado: {self.status}")

        self.status = 'won'
        self.settled_at = timezone.now()
        # Registrar el payout real
        self.potential_payout = payout_amount
        self.save()

        # Generar partida doble
        # 1. Liberar retención en apuestas_pendientes (DEBIT)
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.APUESTAS_PENDIENTES,
            amount=self.stake,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=transaction_id,
            description=f"Liberación de custodia por apuesta ganadora #{self.id}"
        )

        # 2. Crédito a wallet_usuario con el payout total
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=payout_amount,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=transaction_id,
            description=f"Abono de payout por apuesta ganadora #{self.id}"
        )

        # 3. Ajuste de cuenta de la casa
        if payout_amount > self.stake:
            # Casa paga la diferencia (DEBIT a la casa)
            LedgerEntry.objects.create(
                user=self.user,
                account=LedgerEntry.Account.CASA,
                amount=payout_amount - self.stake,
                direction=LedgerEntry.Direction.DEBIT,
                transaction_id=transaction_id,
                description=f"Pago de ganancia neta por apuesta ganadora #{self.id}"
            )
        elif payout_amount < self.stake:
            # Casa recibe la diferencia (CREDIT a la casa)
            LedgerEntry.objects.create(
                user=self.user,
                account=LedgerEntry.Account.CASA,
                amount=self.stake - payout_amount,
                direction=LedgerEntry.Direction.CREDIT,
                transaction_id=transaction_id,
                description=f"Retención de ganancia de casa por recálculo de apuesta ganadora #{self.id}"
            )

    def settle_as_lost(self, transaction_id):
        """
        Liquida la apuesta en estado PERDIDA de forma transaccional.
        REGLA DE PARTIDA DOBLE:
        - Débito apuestas_pendientes (sale dinero retenido) -> DEBIT, monto=stake
        - Crédito casa (dinero ingresa a la casa) -> CREDIT, monto=stake
        """
        from wallet.models import LedgerEntry
        from django.utils import timezone

        if self.status != 'accepted':
            raise ValueError(f"No se puede liquidar como perdida una apuesta en estado: {self.status}")

        self.status = 'lost'
        self.settled_at = timezone.now()
        self.save()

        # Generar partida doble
        # 1. Liberar retención en apuestas_pendientes (DEBIT)
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.APUESTAS_PENDIENTES,
            amount=self.stake,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=transaction_id,
            description=f"Liberación de custodia por apuesta perdida #{self.id}"
        )

        # 2. Crédito a la cuenta de la casa (CREDIT)
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.CASA,
            amount=self.stake,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=transaction_id,
            description=f"Ingreso a caja por apuesta perdida #{self.id}"
        )

    def settle_as_cancelled(self, transaction_id):
        """
        Liquida la apuesta en estado CANCELADA (Anulada) de forma transaccional.
        Se reembolsa el stake íntegramente al usuario.
        REGLA DE PARTIDA DOBLE:
        - Débito apuestas_pendientes (sale dinero retenido) -> DEBIT, monto=stake
        - Crédito wallet_usuario (se devuelve al usuario) -> CREDIT, monto=stake
        """
        from wallet.models import LedgerEntry
        from django.utils import timezone

        if self.status != 'accepted':
            raise ValueError(f"No se puede anular una apuesta en estado: {self.status}")

        self.status = 'cancelled'
        self.settled_at = timezone.now()
        self.save()

        # Generar partida doble
        # 1. Liberar retención en apuestas_pendientes (DEBIT)
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.APUESTAS_PENDIENTES,
            amount=self.stake,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=transaction_id,
            description=f"Liberación de custodia por apuesta anulada #{self.id}"
        )

        # 2. Crédito a la billetera del usuario (CREDIT)
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=self.stake,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=transaction_id,
            description=f"Reembolso de stake por apuesta anulada #{self.id}"
        )

    def perform_cash_out(self, cashout_amount, transaction_id):
        """
        Ejecuta el cobro anticipado (Cash-out) de forma transaccional.
        REGLA DE PARTIDA DOBLE:
        - Débito apuestas_pendientes (monto = stake) -> DEBIT
        - Crédito wallet_usuario (monto = cashout_amount) -> CREDIT
        - Si cashout_amount > stake:
            Débito casa (monto = cashout_amount - stake) -> DEBIT
        - Si cashout_amount < stake:
            Crédito casa (monto = stake - cashout_amount) -> CREDIT
        """
        from wallet.models import LedgerEntry
        from django.utils import timezone

        if self.status != 'accepted':
            raise ValueError(f"No se puede realizar cash-out en una apuesta en estado: {self.status}")

        self.status = 'cashed_out'
        self.settled_at = timezone.now()
        # Actualizamos el payout potencial con el cobrado real
        self.potential_payout = cashout_amount
        self.save()

        # Generar partida doble
        # 1. Liberar retención en apuestas_pendientes (DEBIT)
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.APUESTAS_PENDIENTES,
            amount=self.stake,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=transaction_id,
            description=f"Liberación de custodia por cash-out de apuesta #{self.id}"
        )

        # 2. Abonar monto de cash-out al usuario (CREDIT)
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=cashout_amount,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=transaction_id,
            description=f"Abono por cobro anticipado (Cash-out) de apuesta #{self.id}"
        )

        # 3. Diferencia saldada con la casa
        if cashout_amount > self.stake:
            # La casa paga la diferencia a favor del usuario (DEBIT a la casa)
            LedgerEntry.objects.create(
                user=self.user,
                account=LedgerEntry.Account.CASA,
                amount=cashout_amount - self.stake,
                direction=LedgerEntry.Direction.DEBIT,
                transaction_id=transaction_id,
                description=f"Pago por ganancia neta en cash-out de apuesta #{self.id}"
            )
        elif cashout_amount < self.stake:
            # La casa retiene la diferencia a su favor (CREDIT a la casa)
            LedgerEntry.objects.create(
                user=self.user,
                account=LedgerEntry.Account.CASA,
                amount=self.stake - cashout_amount,
                direction=LedgerEntry.Direction.CREDIT,
                transaction_id=transaction_id,
                description=f"Ingreso a caja por comisión/pérdida en cash-out de apuesta #{self.id}"
            )



class BetSelection(models.Model):
    """
    Representa la relación intermedia entre un boleto de apuesta y las selecciones individuales
    incluidas en él, capturando históricamente el valor de la cuota al momento exacto de apostar.
    """
    STATUS_CHOICES = (
        ('pending', 'Pendiente'),
        ('won', 'Ganada'),
        ('lost', 'Perdida'),
        ('void', 'Anulada'),
    )

    bet = models.ForeignKey(Bet, on_delete=models.CASCADE, related_name='selections', help_text="Boleto de apuesta al que pertenece esta selección")
    selection = models.ForeignKey(Selection, on_delete=models.PROTECT, help_text="Selección deportiva elegida")
    odds_at_bet = models.DecimalField(max_digits=10, decimal_places=4, help_text="Cuota decimal capturada al momento exacto de apostar")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', help_text="Estado de resolución de esta selección individual")

    def __str__(self):
        return f"Apuesta #{self.bet.id} - Selección: {self.selection.name} @ {self.odds_at_bet:.4f}"

