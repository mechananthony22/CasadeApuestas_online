# -*- coding: utf-8 -*-
# Suite de Pruebas Unitarias y de Integración para la Fase 10: Dashboard del Operador y Reporte MINCETUR
from decimal import Decimal
from uuid import uuid4
import csv
import io

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import UserProfile
from betting.models import League, Team, Event, Market, Selection, Bet, BetSelection
from wallet.models import LedgerEntry


class OperatorDashboardTestCase(APITestCase):
    """
    Suite de pruebas completa para validar las métricas en vivo del operador,
    la exposición de riesgo financiero de eventos y la generación del reporte regulatoria MINCETUR (CSV).
    """

    def setUp(self):
        # 1. Crear usuarios de prueba (Admin y Regular)
        self.regular_user = User.objects.create_user(username="gamer1", password="password123")
        self.profile1 = UserProfile.objects.create(
            user=self.regular_user,
            dni="20202020",
            birth_date=timezone.now().date() - timezone.timedelta(days=365 * 22),
            verification_status=UserProfile.STATUS_VERIFIED
        )

        self.operator_user = User.objects.create_superuser(username="operador1", password="adminpassword", email="operator@fairbet.pe")
        self.profile2 = UserProfile.objects.create(
            user=self.operator_user,
            dni="30303030",
            birth_date=timezone.now().date() - timezone.timedelta(days=365 * 35),
            verification_status=UserProfile.STATUS_VERIFIED
        )

        # 2. Configurar liga, equipos y eventos deportivos
        self.league = League.objects.create(api_id=39, name="La Liga", country="España")
        self.team_home = Team.objects.create(api_id=1, name="Real Madrid")
        self.team_away = Team.objects.create(api_id=2, name="Barcelona")
        
        # Evento Activo 1 (in_play)
        self.event_live = Event.objects.create(
            api_id=101,
            league=self.league,
            home_team=self.team_home,
            away_team=self.team_away,
            starts_at=timezone.now() - timezone.timedelta(minutes=30),
            status='in_play'
        )
        self.market_live = Market.objects.create(event=self.event_live, name="1X2")
        self.sel_home = Selection.objects.create(market=self.market_live, name="Local", odds=Decimal("2.0000"))
        self.sel_draw = Selection.objects.create(market=self.market_live, name="Empate", odds=Decimal("3.0000"))
        self.sel_away = Selection.objects.create(market=self.market_live, name="Visitante", odds=Decimal("4.0000"))

        # Evento Activo 2 (scheduled)
        self.event_sched = Event.objects.create(
            api_id=102,
            league=self.league,
            home_team=self.team_home,
            away_team=self.team_away,
            starts_at=timezone.now() + timezone.timedelta(hours=2),
            status='scheduled'
        )
        self.market_sched = Market.objects.create(event=self.event_sched, name="1X2")
        self.sel_sched_home = Selection.objects.create(market=self.market_sched, name="Local", odds=Decimal("1.8000"))

        # 3. Registrar fondos iniciales mediante Ledger para poder colocar apuestas o realizar liquidaciones correctas
        # Cargar saldo de 1000 al usuario
        LedgerEntry.objects.create(
            user=self.regular_user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("1000.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=uuid4(),
            description="Recarga inicial para pruebas"
        )
        # Contrapartida de casa
        LedgerEntry.objects.create(
            user=self.regular_user,
            account=LedgerEntry.Account.CASA,
            amount=Decimal("1000.0000"),
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=uuid4(),
            description="Carga de recarga inicial a casa"
        )

        # 4. URLs de los Endpoints
        self.url_metrics = reverse('operator-dashboard-metrics')
        self.url_report = reverse('operator-mincetur-report')

    def test_dashboard_access_control(self):
        """
        Verifica que solo los usuarios administradores (staff) puedan acceder a los endpoints.
        """
        # A. Sin autenticación -> 401 Unauthorized (o 403 según configuración predeterminada de DRF)
        response = self.client.get(self.url_metrics)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        response = self.client.get(self.url_report)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        # B. Autenticado como usuario regular -> 403 Forbidden
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(self.url_metrics)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(self.url_report)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # C. Autenticado como operador (staff) -> 200 OK
        self.client.force_authenticate(user=self.operator_user)
        response = self.client.get(self.url_metrics)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(self.url_report)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_ggr_and_volume_calculation(self):
        """
        Verifica la exactitud del cálculo de GGR (Gross Gaming Revenue = stakes - payouts)
        y del volumen de apuestas acumulado.
        """
        self.client.force_authenticate(user=self.operator_user)

        # Crear apuestas en distintos estados
        # Bet 1: Ganada (payout = stake * odds = 100 * 2 = 200)
        # GGR de Bet 1: 100 - 200 = -100
        b1 = Bet.objects.create(
            user=self.regular_user,
            status='won',
            type='simple',
            stake=Decimal("100.0000"),
            potential_payout=Decimal("200.0000"),
            idempotency_key=uuid4()
        )
        BetSelection.objects.create(bet=b1, selection=self.sel_home, odds_at_bet=Decimal("2.0000"), status='won')

        # Bet 2: Perdida (payout = 0)
        # GGR de Bet 2: 150 - 0 = +150
        b2 = Bet.objects.create(
            user=self.regular_user,
            status='lost',
            type='simple',
            stake=Decimal("150.0000"),
            potential_payout=Decimal("300.0000"),
            idempotency_key=uuid4()
        )
        BetSelection.objects.create(bet=b2, selection=self.sel_draw, odds_at_bet=Decimal("3.0000"), status='lost')

        # Bet 3: Cobro Anticipado (payout = 95)
        # GGR de Bet 3: 100 - 95 = +5
        b3 = Bet.objects.create(
            user=self.regular_user,
            status='cashed_out',
            type='simple',
            stake=Decimal("100.0000"),
            potential_payout=Decimal("95.0000"),
            idempotency_key=uuid4()
        )
        BetSelection.objects.create(bet=b3, selection=self.sel_away, odds_at_bet=Decimal("4.0000"), status='pending')

        # Bet 4: Cancelada / Reembolsada (payout = 50)
        # GGR de Bet 4: 50 - 50 = 0
        b4 = Bet.objects.create(
            user=self.regular_user,
            status='cancelled',
            type='simple',
            stake=Decimal("50.0000"),
            potential_payout=Decimal("50.0000"),
            idempotency_key=uuid4()
        )
        BetSelection.objects.create(bet=b4, selection=self.sel_home, odds_at_bet=Decimal("2.0000"), status='void')

        # Bet 5: Abierta / Aceptada (No debe impactar GGR por estar abierta)
        # GGR de Bet 5: No se suma
        b5 = Bet.objects.create(
            user=self.regular_user,
            status='accepted',
            type='simple',
            stake=Decimal("80.0000"),
            potential_payout=Decimal("160.0000"),
            idempotency_key=uuid4()
        )
        BetSelection.objects.create(bet=b5, selection=self.sel_home, odds_at_bet=Decimal("2.0000"), status='pending')

        # GGR esperado: 100 - 200 + 150 + 100 - 95 + 50 - 50 = -100 + 150 + 5 = 55.00
        # Volumen esperado: total apuestas = 5, stakes totales = 100 + 150 + 100 + 50 + 80 = 480.00
        # Apuestas pendientes: count = 1, amount = 80.00

        response = self.client.get(self.url_metrics)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.data
        self.assertEqual(Decimal(data['ggr']), Decimal("55.0000"))
        self.assertEqual(Decimal(data['total_stakes']), Decimal("400.0000"))  # Won (100) + Lost (150) + Cashed (100) + Cancelled (50) = 400
        self.assertEqual(Decimal(data['total_payouts']), Decimal("345.0000")) # Won (200) + Lost (0) + Cashed (95) + Cancel (50) = 345
        
        # Volumen de Apuestas
        vol = data['bet_volume']
        self.assertEqual(vol['total_bets_count'], 5)
        self.assertEqual(Decimal(vol['total_stakes_amount']), Decimal("480.0000"))
        self.assertEqual(vol['active_bets_count'], 1)
        self.assertEqual(Decimal(vol['active_stakes_amount']), Decimal("80.0000"))

    def test_event_exposure_calculation(self):
        """
        Verifica el cálculo de la exposición financiera neta (`net_exposure`) por cada selección del mercado.
        """
        self.client.force_authenticate(user=self.operator_user)

        # Crear apuestas activas en distintas selecciones del mismo mercado
        # Apostado a Local: 100 con cuota 2.0 (payout potencial = 200)
        b1 = Bet.objects.create(
            user=self.regular_user,
            status='accepted',
            type='simple',
            stake=Decimal("100.0000"),
            potential_payout=Decimal("200.0000"),
            idempotency_key=uuid4()
        )
        BetSelection.objects.create(bet=b1, selection=self.sel_home, odds_at_bet=Decimal("2.0000"), status='pending')

        # Apostado a Empate: 50 con cuota 3.0 (payout potencial = 150)
        b2 = Bet.objects.create(
            user=self.regular_user,
            status='accepted',
            type='simple',
            stake=Decimal("50.0000"),
            potential_payout=Decimal("150.0000"),
            idempotency_key=uuid4()
        )
        BetSelection.objects.create(bet=b2, selection=self.sel_draw, odds_at_bet=Decimal("3.0000"), status='pending')

        response = self.client.get(self.url_metrics)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Buscar el evento en vivo en la exposición
        event_exp = next(e for e in response.data['event_exposure'] if e['event_id'] == self.event_live.id)
        market_exp = event_exp['markets'][0]
        self.assertEqual(market_exp['market_name'], "1X2")

        # Verificar selección Local
        sel_home_data = next(s for s in market_exp['selections'] if s['selection_id'] == self.sel_home.id)
        self.assertEqual(sel_home_data['active_bets_count'], 1)
        self.assertEqual(Decimal(sel_home_data['total_stake']), Decimal("100.0000"))
        self.assertEqual(Decimal(sel_home_data['gross_exposure']), Decimal("200.0000"))
        self.assertEqual(Decimal(sel_home_data['net_exposure']), Decimal("50.0000"))

        # Verificar selección Empate
        sel_draw_data = next(s for s in market_exp['selections'] if s['selection_id'] == self.sel_draw.id)
        self.assertEqual(sel_draw_data['active_bets_count'], 1)
        self.assertEqual(Decimal(sel_draw_data['total_stake']), Decimal("50.0000"))
        self.assertEqual(Decimal(sel_draw_data['gross_exposure']), Decimal("150.0000"))
        self.assertEqual(Decimal(sel_draw_data['net_exposure']), Decimal("0.0000"))

        # Verificar selección Visitante (sin apuestas)
        sel_away_data = next(s for s in market_exp['selections'] if s['selection_id'] == self.sel_away.id)
        self.assertEqual(sel_away_data['active_bets_count'], 0)
        self.assertEqual(Decimal(sel_away_data['total_stake']), Decimal("0.0000"))
        self.assertEqual(Decimal(sel_away_data['gross_exposure']), Decimal("0.0000"))
        self.assertEqual(Decimal(sel_away_data['net_exposure']), Decimal("-150.0000"))

    def test_mincetur_report_csv_generation(self):
        """
        Verifica que el reporte mensual exportable estilo MINCETUR se genere con el formato CSV, encabezados regulatorios y contenido correcto.
        """
        self.client.force_authenticate(user=self.operator_user)

        # Crear apuesta liquidada en un mes específico (ej: Mayo de 2026)
        b1 = Bet.objects.create(
            user=self.regular_user,
            status='won',
            type='simple',
            stake=Decimal("120.0000"),
            potential_payout=Decimal("240.0000"),
            idempotency_key=uuid4()
        )
        BetSelection.objects.create(bet=b1, selection=self.sel_home, odds_at_bet=Decimal("2.0000"), status='won')

        # Forzar fechas en base de datos para simular liquidación exacta en mayo de 2026
        target_settled = timezone.datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.get_current_timezone())
        target_created = target_settled - timezone.timedelta(hours=2)
        Bet.objects.filter(pk=b1.pk).update(created_at=target_created, settled_at=target_settled)

        # Bet 2: Liquidada en junio (no debe aparecer en el reporte de mayo)
        b2 = Bet.objects.create(
            user=self.regular_user,
            status='lost',
            type='simple',
            stake=Decimal("150.0000"),
            potential_payout=Decimal("300.0000"),
            idempotency_key=uuid4()
        )
        BetSelection.objects.create(bet=b2, selection=self.sel_sched_home, odds_at_bet=Decimal("1.8000"), status='lost')
        june_settled = timezone.datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.get_current_timezone())
        Bet.objects.filter(pk=b2.pk).update(created_at=june_settled - timezone.timedelta(hours=1), settled_at=june_settled)

        # Solicitar el reporte de Mayo de 2026
        response = self.client.get(self.url_report, {'year': 2026, 'month': 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="reporte_mincetur_2026_05.csv"', response['Content-Disposition'])

        # Decodificar el CSV para validar contenido
        csv_content = response.content.decode('utf-8')
        
        # Eliminar el BOM si existe para procesarlo de forma limpia
        if csv_content.startswith('\ufeff'):
            csv_content = csv_content[1:]
            
        csv_file = io.StringIO(csv_content)
        reader = csv.reader(csv_file)
        
        rows = list(reader)
        
        # A. Validar cabeceras
        headers = rows[0]
        expected_headers = [
            'ticket_id', 'dni_jugador', 'username', 'fecha_colocacion', 'fecha_liquidacion',
            'tipo_apuesta', 'evento_seleccion', 'cuota', 'monto_apostado', 'estado_apuesta',
            'monto_pagado', 'ggr', 'moneda'
        ]
        self.assertEqual(headers, expected_headers)

        # B. Validar cantidad de registros de apuestas (sólo la de Mayo)
        data_rows = rows[1:]
        self.assertEqual(len(data_rows), 1)

        # C. Validar campos específicos del ticket liquidado
        ticket_row = data_rows[0]
        self.assertEqual(int(ticket_row[0]), b1.id)
        self.assertEqual(ticket_row[1], self.profile1.dni)
        self.assertEqual(ticket_row[2], self.regular_user.username)
        self.assertEqual(ticket_row[5], b1.get_type_display()) # Simple
        self.assertIn("Real Madrid vs Barcelona", ticket_row[6]) # Detalle evento
        self.assertEqual(Decimal(ticket_row[7]), Decimal("2.0000")) # Cuota
        self.assertEqual(Decimal(ticket_row[8]), Decimal("120.0000")) # Stake
        self.assertEqual(ticket_row[9], b1.get_status_display()) # Ganada
        self.assertEqual(Decimal(ticket_row[10]), Decimal("240.0000")) # Payout
        self.assertEqual(Decimal(ticket_row[11]), Decimal("-120.0000")) # GGR = stake - payout = 120 - 240 = -120
        self.assertEqual(ticket_row[12], 'Fichas Virtuales')
