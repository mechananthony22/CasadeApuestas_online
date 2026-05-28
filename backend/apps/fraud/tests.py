# -*- coding: utf-8 -*-
"""
Suite de Pruebas Unitarias y de Integración para la Fase 9: Anti-fraude Básico.

Cubre:
    1. Regla de multicuenta (Misma IP con más de 3 cuentas distintas).
    2. Regla de velocidad financiera (Recarga seguida de Cash-out en menos de 15 minutos).
    3. Regla de amaños/sindicalización (Apuestas idénticas de 3 usuarios distintos en menos de 5 minutos).
    4. Permisos de seguridad y endpoints de auditoría administrativa para resolver alertas.
"""
from decimal import Decimal
from uuid import uuid4
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from wallet.models import LedgerEntry
from betting.models import League, Team, Event, Market, Selection, Bet
from fraud.models import SuspiciousActivity, UserIpLog

class FraudDetectorTestCase(APITestCase):
    """
    Suite de pruebas completa para verificar las heurísticas y el sistema de alertas del motor anti-fraude.
    """

    def setUp(self):
        # Crear usuarios para simular patrones grupales
        self.users = []
        for i in range(5):
            username = f"gamer_fraud_{i}"
            u = User.objects.create_user(username=username, password="password123")
            from users.models import UserProfile
            UserProfile.objects.create(
                user=u,
                dni=f"1111111{i}",
                birth_date=timezone.now().date() - timezone.timedelta(days=365 * 25),
                verification_status=UserProfile.STATUS_VERIFIED
            )
            self.users.append(u)

        # Crear administrador de seguridad
        self.admin_user = User.objects.create_superuser(username="security_officer", password="adminpassword", email="security@fairbet.pe")

        # Catálogo deportivo mínimo para apuestas
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

    def test_rule_1_multiple_accounts_same_ip(self):
        """
        1. Regla Multicuenta: La dirección IP de origen compartida por más de 3 usuarios
           distintos durante depósitos debe gatillar SuspiciousActivity.
        """
        shared_ip = "192.168.12.12"
        url_deposit = reverse('api-wallet-deposit')

        # Realizar depósitos simulados con 3 usuarios diferentes desde la misma IP (no debe disparar alerta aún)
        for i in range(3):
            u = self.users[i]
            self.client.force_authenticate(user=u)
            response = self.client.post(
                url_deposit, 
                {'amount': '100.0000'}, 
                format='json',
                HTTP_X_FORWARDED_FOR=shared_ip
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        alerts_before = SuspiciousActivity.objects.filter(activity_type=SuspiciousActivity.TYPE_MULTIPLE_ACCOUNTS)
        self.assertEqual(alerts_before.count(), 0)

        # Realizar depósito con el 4to usuario desde la misma IP (debe disparar la alerta)
        self.client.force_authenticate(user=self.users[3])
        response = self.client.post(
            url_deposit, 
            {'amount': '100.0000'}, 
            format='json',
            HTTP_X_FORWARDED_FOR=shared_ip
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verificar alerta generada
        alerts_after = SuspiciousActivity.objects.filter(activity_type=SuspiciousActivity.TYPE_MULTIPLE_ACCOUNTS)
        self.assertEqual(alerts_after.count(), 1)
        
        alert = alerts_after.first()
        self.assertEqual(alert.severity, SuspiciousActivity.SEVERITY_MEDIUM)
        self.assertEqual(alert.status, SuspiciousActivity.STATUS_PENDING)
        self.assertIn(shared_ip, alert.description)
        self.assertEqual(len(alert.payload['usuarios']), 4)

    def test_rule_2_deposit_followed_by_immediate_cashout(self):
        """
        2. Regla de Velocidad Financiera: Recargar saldo y realizar cash-out en menos
           de 15 minutos debe disparar una alerta de alta severidad.
        """
        u = self.users[0]
        self.client.force_authenticate(user=u)

        # 1. Realizar recarga
        url_deposit = reverse('api-wallet-deposit')
        self.client.post(url_deposit, {'amount': '200.0000'}, format='json')

        # 2. Colocar una apuesta de 100
        response_bet = self.client.post(
            '/api/v1/betting/bets/',
            {
                "selections": [{"selection_id": self.selection.id, "expected_odds": "2.0000"}],
                "stake": "100.0000"
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )
        self.assertEqual(response_bet.status_code, status.HTTP_201_CREATED)
        bet_id = response_bet.data['id']

        # 3. Solicitar Cash-out inmediato de la apuesta
        url_cashout = f"/api/v1/betting/bets/{bet_id}/cashout/"
        response_cashout = self.client.post(url_cashout, format='json')
        self.assertEqual(response_cashout.status_code, status.HTTP_200_OK)

        # Verificar alerta generada por cash-out apresurado
        alerts = SuspiciousActivity.objects.filter(activity_type=SuspiciousActivity.TYPE_DEPOSIT_CASHOUT)
        self.assertEqual(alerts.count(), 1)
        
        alert = alerts.first()
        self.assertEqual(alert.severity, SuspiciousActivity.SEVERITY_HIGH)
        self.assertEqual(alert.user, u)
        self.assertEqual(alert.payload['bet_id'], bet_id)

    def test_rule_3_syndicated_identical_betting(self):
        """
        3. Regla Amaños/Sindicalización: Apuestas idénticas por el mismo monto hechas por
           3 usuarios diferentes en menos de 5 minutos dispara SuspiciousActivity.
        """
        # Cargar saldo inicial a los 3 primeros usuarios
        for i in range(3):
            tx_id = uuid4()
            LedgerEntry.objects.create(
                user=self.users[i],
                account=LedgerEntry.Account.WALLET_USUARIO,
                amount=Decimal("300.0000"),
                direction=LedgerEntry.Direction.CREDIT,
                transaction_id=tx_id,
                description="Recarga de fianza"
            )

        # 1. Primer usuario realiza apuesta idéntica
        self.client.force_authenticate(user=self.users[0])
        self.client.post(
            '/api/v1/betting/bets/',
            {"selections": [{"selection_id": self.selection.id, "expected_odds": "2.0000"}], "stake": "150.0000"},
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )

        # 2. Segundo usuario realiza apuesta idéntica
        self.client.force_authenticate(user=self.users[1])
        self.client.post(
            '/api/v1/betting/bets/',
            {"selections": [{"selection_id": self.selection.id, "expected_odds": "2.0000"}], "stake": "150.0000"},
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )

        # No debe haber alertas de sindicalización aún con sólo 2 usuarios
        self.assertEqual(SuspiciousActivity.objects.filter(activity_type=SuspiciousActivity.TYPE_IDENTICAL_BET).count(), 0)

        # 3. Tercer usuario realiza apuesta idéntica (dispara alerta)
        self.client.force_authenticate(user=self.users[2])
        self.client.post(
            '/api/v1/betting/bets/',
            {"selections": [{"selection_id": self.selection.id, "expected_odds": "2.0000"}], "stake": "150.0000"},
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )

        # Verificar alerta de patrón de apuestas idénticas
        alerts = SuspiciousActivity.objects.filter(activity_type=SuspiciousActivity.TYPE_IDENTICAL_BET)
        self.assertEqual(alerts.count(), 1)
        
        alert = alerts.first()
        self.assertEqual(alert.severity, SuspiciousActivity.SEVERITY_HIGH)
        self.assertEqual(len(alert.payload['usuarios']), 3)

    def test_admin_alerts_list_and_resolve(self):
        """
        4. Acceso del operador: Visualización de alertas y resolución transaccional de estados.
        """
        # Crear alerta pendiente manual
        alert = SuspiciousActivity.objects.create(
            user=self.users[0],
            activity_type=SuspiciousActivity.TYPE_DEPOSIT_CASHOUT,
            description="Alerta de simulación",
            payload={'test': 'data'},
            severity=SuspiciousActivity.SEVERITY_HIGH,
            status=SuspiciousActivity.STATUS_PENDING
        )

        # 1. Denegar acceso a usuario no administrativo
        self.client.force_authenticate(user=self.users[0])
        response = self.client.get('/api/v1/fraud/alerts/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Permitir acceso y verificar listado para administrador
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/v1/fraud/alerts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        # 3. Resolver la alerta como revisada (REVIEWED)
        url_resolve = f"/api/v1/fraud/alerts/{alert.id}/resolve/"
        response_resolve = self.client.post(url_resolve, {'status': 'REVIEWED'}, format='json')
        self.assertEqual(response_resolve.status_code, status.HTTP_200_OK)
        self.assertEqual(response_resolve.data['status'], 'REVIEWED')
        self.assertEqual(response_resolve.data['resolved_by_username'], 'security_officer')

        # 4. Intentar resolver una alerta ya cerrada (debe fallar con 400)
        response_double = self.client.post(url_resolve, {'status': 'DISMISSED'}, format='json')
        self.assertEqual(response_double.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rule_4_bonus_abuse_hedge_betting(self):
        """
        4. Regla de Abuso de Bono (Apuestas Cruzadas/Hedge Betting):
           Si un usuario con bono de bienvenida activo coloca apuestas en selecciones
           mutuamente excluyentes del mismo mercado/evento deportivo para liberar el bono sin riesgo,
           se debe disparar una alerta anti-fraude.
        """
        from wallet.models import UserBonus
        u = self.users[0]
        self.client.force_authenticate(user=u)

        # 1. Crear bono de bienvenida activo para el usuario
        UserBonus.objects.create(
            user=u,
            bonus_amount=Decimal('100.0000'),
            required_turnover=Decimal('600.0000'),
            is_active=True
        )

        # 2. Cargarle saldo suficiente en su wallet
        LedgerEntry.objects.create(
            user=u,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal('500.0000'),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=uuid4(),
            description="Carga inicial"
        )

        # 3. Crear otra selección en el mismo mercado (ej. Visitante con cuota 2.50)
        selection_away = Selection.objects.create(
            market=self.market,
            name="Visitante",
            odds=Decimal("2.5000")
        )

        # 4. Colocar la primera apuesta a "Local" (debe tener éxito y no disparar alerta de abuso)
        response_bet1 = self.client.post(
            '/api/v1/betting/bets/',
            {
                "selections": [{"selection_id": self.selection.id, "expected_odds": "2.0000"}],
                "stake": "100.0000"
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )
        self.assertEqual(response_bet1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SuspiciousActivity.objects.filter(activity_type=SuspiciousActivity.TYPE_BONUS_ABUSE).count(), 0)

        # 5. Colocar la segunda apuesta a "Visitante" en el mismo evento (debe disparar la alerta)
        response_bet2 = self.client.post(
            '/api/v1/betting/bets/',
            {
                "selections": [{"selection_id": selection_away.id, "expected_odds": "2.5000"}],
                "stake": "100.0000"
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )
        self.assertEqual(response_bet2.status_code, status.HTTP_201_CREATED)

        # 6. Verificar que se haya registrado la alerta de abuso de bono
        alerts = SuspiciousActivity.objects.filter(activity_type=SuspiciousActivity.TYPE_BONUS_ABUSE)
        self.assertEqual(alerts.count(), 1)
        alert = alerts.first()
        self.assertEqual(alert.user, u)
        self.assertEqual(alert.severity, SuspiciousActivity.SEVERITY_HIGH)
        self.assertEqual(alert.payload['market_id'], self.market.id)
        self.assertIn(alert.payload['selection_1'], [self.selection.name, selection_away.name])
        self.assertIn(alert.payload['selection_2'], [self.selection.name, selection_away.name])
