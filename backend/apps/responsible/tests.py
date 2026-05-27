# -*- coding: utf-8 -*-
"""
Suite de Pruebas Unitarias y de Integración para la Fase 7: Juego Responsable.

Cubre:
    1. Límites de Depósito: reducción inmediata, cooldown de 24 horas para aumentos/desactivación.
    2. Depósitos bloqueados y controlados acumulativamente en DepositoView.
    3. Autoexclusión temporal y permanente bloqueando depósitos y apuestas de forma segura.
    4. Restauración dinámica de autoexclusiones temporales expiradas.
    5. Tarea periódica de Celery para aplicar límites preventivos con cooldown expirado.
"""
from decimal import Decimal
from uuid import uuid4
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from responsible.models import ResponsibleGamingLimit, AutoExclusion
from responsible.tasks import apply_expired_limits
from users.models import UserProfile
from wallet.models import LedgerEntry
from betting.models import League, Team, Event, Market, Selection

class ResponsibleGamingTestCase(APITestCase):
    """
    Suite completa de pruebas para verificar las reglas de negocio de juego responsable.
    """

    def setUp(self):
        # Crear usuario y su perfil KYC verificado
        self.user = User.objects.create_user(username="test_gamer", password="password123")
        self.profile = UserProfile.objects.create(
            user=self.user,
            dni="77777777",
            birth_date=timezone.now().date() - timezone.timedelta(days=365 * 25), # 25 años
            verification_status=UserProfile.STATUS_VERIFIED
        )
        self.client.force_authenticate(user=self.user)

        # Crear catálogo deportivo mínimo para apuestas
        self.league = League.objects.create(api_id=39, name="La Liga", country="España")
        self.home_team = Team.objects.create(api_id=1, name="Real Madrid")
        self.away_team = Team.objects.create(api_id=2, name="Barcelona")
        self.event = Event.objects.create(
            api_id=100,
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            starts_at=timezone.now() + timezone.timedelta(days=1),
            status='scheduled'
        )
        self.market = Market.objects.create(event=self.event, name="1X2")
        self.selection = Selection.objects.create(market=self.market, name="Local", odds=Decimal("2.0000"))

    def test_instant_limit_reduction(self):
        """
        1. Las reducciones de límites de depósito deben aplicarse al instante.
        """
        # Establecer límite diario inicial
        limit_obj = ResponsibleGamingLimit.objects.create(user=self.user, daily_limit=Decimal("500.0000"))

        url = reverse('responsible-limits')
        
        # Reducir el límite a 200.0000
        response = self.client.post(url, {'daily_limit': 200.0}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verificar que se aplicó inmediatamente en la BD
        limit_obj.refresh_from_db()
        self.assertEqual(limit_obj.daily_limit, Decimal("200.0000"))
        self.assertIsNone(limit_obj.pending_daily_limit)
        self.assertIsNone(limit_obj.cooldown_until_daily)

    def test_cooldown_for_limit_increase(self):
        """
        2. Los aumentos de límites de depósito deben requerir un cooldown de 24 horas.
        """
        # Establecer límite diario inicial
        limit_obj = ResponsibleGamingLimit.objects.create(user=self.user, daily_limit=Decimal("100.0000"))

        url = reverse('responsible-limits')

        # Intentar aumentar el límite a 300.0000
        response = self.client.post(url, {'daily_limit': 300.0}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verificar que el límite activo sigue siendo 100 y el nuevo valor es pendiente
        limit_obj.refresh_from_db()
        self.assertEqual(limit_obj.daily_limit, Decimal("100.0000"))
        self.assertEqual(limit_obj.pending_daily_limit, Decimal("300.0000"))
        self.assertIsNotNone(limit_obj.cooldown_until_daily)

        # Verificar que si simulamos adelantar el tiempo 24 horas, el clean_expired_cooldowns lo consolida
        limit_obj.cooldown_until_daily = timezone.now() - timezone.timedelta(seconds=1)
        limit_obj.save()

        # Al consultar (GET), se debe aplicar de forma transparente
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data['daily_limit']), Decimal("300.0000"))
        self.assertIsNone(response.data['pending_daily_limit'])

    def test_deposit_limits_rejection(self):
        """
        3. Superar límites diarios, semanales o mensuales debe rechazar el depósito.
        """
        # Establecer límite diario de 100.0000
        ResponsibleGamingLimit.objects.create(user=self.user, daily_limit=Decimal("100.0000"))

        # 1. Realizar una recarga de 80 fichas (exitosa)
        url_deposit = reverse('wallet-deposit')
        response = self.client.post(url_deposit, {'amount': '80.0000', 'description': 'Recarga inicial'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 2. Intentar recargar 30 fichas (rechazada por exceder límite diario de 100 ya acumulado en 80)
        response = self.client.post(url_deposit, {'amount': '30.0000', 'description': 'Recarga excesiva'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Depósito rechazado por exceder el límite diario", response.data['error'])
        self.assertEqual(Decimal(response.data['limite_diario']), Decimal("100.0000"))
        self.assertEqual(Decimal(response.data['acumulado_24h']), Decimal("80.0000"))
        self.assertEqual(Decimal(response.data['disponible']), Decimal("20.0000"))

    def test_autoexclusion_blocks_deposit_and_bet(self):
        """
        4. La autoexclusión (temporal o permanente) debe bloquear apuestas y depósitos.
        """
        # Autoexcluirse llamando al endpoint temporalmente (7 días)
        url_exclude = reverse('users-self-exclude')
        response = self.client.post(url_exclude, {'dias': 7}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Autoexcluido", response.data['estado'])

        # Verificar que la cuenta está inactiva y no permite depósitos
        url_deposit = reverse('wallet-deposit')
        response = self.client.post(url_deposit, {'amount': '50.0000'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Verificar que no permite apuestas
        # Cargar saldo manualmente (por si acaso simular entrada de libro)
        tx_id = uuid4()
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("100.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx_id,
            description="Carga forzada"
        )

        response = self.client.post(
            '/api/v1/betting/bets/',
            {
                "selections": [{"selection_id": self.selection.id, "expected_odds": "2.0000"}],
                "stake": "50.0000"
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("autoexclusión activa", str(response.data))

    def test_dynamic_recovery_expired_autoexclusion(self):
        """
        5. Una autoexclusión vencida debe recuperarse dinámicamente al consultar perfil o depositar/apostar.
        """
        # Configurar autoexclusión ya vencida en la base de datos
        AutoExclusion.objects.create(
            user=self.user,
            excluded_until=timezone.now() - timezone.timedelta(days=1)
        )
        self.profile.verification_status = UserProfile.STATUS_SELF_EXCLUDED
        self.profile.save()

        # Consultar perfil (users-me) debe restaurar la verificación
        url_me = reverse('users-me')
        response = self.client.get(url_me)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['verification_status'], "verified")

        # El perfil debe estar verificado de nuevo
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.verification_status, UserProfile.STATUS_VERIFIED)

    def test_celery_task_apply_expired_limits(self):
        """
        6. La tarea de Celery debe buscar perfiles con cooldowns expirados y aplicarlos.
        """
        # Crear límite con cooldown ya vencido para aumento
        limit_obj = ResponsibleGamingLimit.objects.create(
            user=self.user,
            daily_limit=Decimal("50.0000"),
            pending_daily_limit=Decimal("250.0000"),
            cooldown_until_daily=timezone.now() - timezone.timedelta(seconds=1)
        )

        # Ejecutar tarea Celery directamente
        processed_count = apply_expired_limits()
        self.assertEqual(processed_count, 1)

        # Verificar que se aplicó el cambio
        limit_obj.refresh_from_db()
        self.assertEqual(limit_obj.daily_limit, Decimal("250.0000"))
        self.assertIsNone(limit_obj.pending_daily_limit)
        self.assertIsNone(limit_obj.cooldown_until_daily)
