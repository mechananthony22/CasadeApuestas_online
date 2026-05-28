# -*- coding: utf-8 -*-
# Vistas basadas en Django REST Framework para el dashboard del operador y reportes regulatorios en FairBet Lab
from decimal import Decimal
import csv
from datetime import timedelta

from django.db import models
from django.db.models import Sum, Count, Case, When, F, Value, DecimalField
from django.utils import timezone
from django.http import HttpResponse
from django.contrib.auth.models import User

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework import status

from betting.models import Bet, BetSelection, Event, Market, Selection
from wallet.models import LedgerEntry


class OperatorDashboardView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        # 1. Cómputo del GGR (Gross Gaming Revenue) en tiempo real
        # Considera únicamente apuestas resueltas/liquidadas: ganadas, perdidas, cashout y canceladas
        totals = Bet.objects.filter(
            status__in=['won', 'lost', 'cashed_out', 'cancelled']
        ).aggregate(
            total_stakes=Sum('stake'),
            total_payouts=Sum(
                Case(
                    When(status='won', then=F('potential_payout')),
                    When(status='cashed_out', then=F('potential_payout')),
                    When(status='cancelled', then=F('stake')),
                    When(status='lost', then=Value(Decimal('0.0000'))),
                    default=Value(Decimal('0.0000')),
                    output_field=DecimalField()
                )
            )
        )

        total_stakes = totals['total_stakes'] or Decimal('0.0000')
        total_payouts = totals['total_payouts'] or Decimal('0.0000')
        ggr = total_stakes - total_payouts

        # 2. Volumen de Apuestas (Métricas agregadas de volumen)
        total_bets_count = Bet.objects.count()
        total_stakes_amount = Bet.objects.aggregate(total=Sum('stake'))['total'] or Decimal('0.0000')

        active_bets_count = Bet.objects.filter(status='accepted').count()
        active_stakes_amount = Bet.objects.filter(status='accepted').aggregate(total=Sum('stake'))['total'] or Decimal('0.0000')

        limit_24h = timezone.now() - timedelta(days=1)
        today_bets_count = Bet.objects.filter(created_at__gte=limit_24h).count()
        today_stakes_amount = Bet.objects.filter(created_at__gte=limit_24h).aggregate(total=Sum('stake'))['total'] or Decimal('0.0000')

        bet_volume = {
            'total_bets_count': total_bets_count,
            'total_stakes_amount': total_stakes_amount,
            'active_bets_count': active_bets_count,
            'active_stakes_amount': active_stakes_amount,
            'today_bets_count': today_bets_count,
            'today_stakes_amount': today_stakes_amount,
        }

        # 3. Usuarios Activos (Actividad combinada por login y transacciones)
        def get_active_users(days):
            limit = timezone.now() - timedelta(days=days)
            return User.objects.filter(
                models.Q(last_login__gte=limit) |
                models.Q(bets__created_at__gte=limit) |
                models.Q(ledger_entries__created_at__gte=limit)
            ).distinct().count()

        active_users = {
            'active_users_24h': get_active_users(1),
            'active_users_7d': get_active_users(7),
            'active_users_30d': get_active_users(30),
            'total_registered_users': User.objects.count(),
        }

        # 4. Exposición Financiera por Evento (Exposure)
        # Analizamos todos los eventos en estado 'scheduled' o 'in_play' para medir el riesgo de la casa
        event_exposure = []
        active_events = Event.objects.filter(
            status__in=['scheduled', 'in_play']
        ).select_related('league', 'home_team', 'away_team').prefetch_related(
            'markets', 'markets__selections'
        )

        for event in active_events:
            event_data = {
                'event_id': event.id,
                'home_team': event.home_team.name,
                'away_team': event.away_team.name,
                'starts_at': event.starts_at,
                'status': event.status,
                'status_display': event.get_status_display(),
                'markets': []
            }

            for market in event.markets.all():
                market_data = {
                    'market_id': market.id,
                    'market_name': market.name,
                    'selections': []
                }

                # Cargar todas las selecciones y las apuestas activas
                selections = market.selections.all()
                market_bets = BetSelection.objects.filter(
                    selection__market=market,
                    bet__status='accepted'
                ).select_related('bet')

                # Total acumulado apostado en este mercado específico
                total_market_stake = sum(bs.bet.stake for bs in market_bets)

                for selection in selections:
                    # Filtrar apuestas colocadas específicamente en esta selección
                    selection_bets = [bs for bs in market_bets if bs.selection_id == selection.id]

                    bets_count = len(selection_bets)
                    total_stake_sel = sum(bs.bet.stake for bs in selection_bets)
                    gross_exp_sel = sum(bs.bet.potential_payout for bs in selection_bets)

                    # Exposición Neta: Payout total si gana la selección menos todos los stakes recolectados del mercado
                    net_exp_sel = gross_exp_sel - total_market_stake

                    market_data['selections'].append({
                        'selection_id': selection.id,
                        'selection_name': selection.name,
                        'odds': selection.odds,
                        'active_bets_count': bets_count,
                        'total_stake': total_stake_sel,
                        'gross_exposure': gross_exp_sel,
                        'net_exposure': net_exp_sel
                    })

                event_data['markets'].append(market_data)

            event_exposure.append(event_data)

        # 5. Respuesta JSON final consolidada
        return Response({
            'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.',
            'ggr': ggr,
            'total_stakes': total_stakes,
            'total_payouts': total_payouts,
            'bet_volume': bet_volume,
            'active_users': active_users,
            'event_exposure': event_exposure
        }, status=status.HTTP_200_OK)


class MinceturReportView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, *args, **kwargs):
        year_param = request.query_params.get('year')
        month_param = request.query_params.get('month')

        try:
            if year_param:
                year = int(year_param)
            else:
                year = timezone.now().year

            if month_param:
                month = int(month_param)
            else:
                month = timezone.now().month
        except ValueError:
            return Response(
                {'error': 'Los parámetros "year" y "month" deben ser números enteros válidos.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Filtrar apuestas que fueron resueltas en el mes indicado
        bets = Bet.objects.filter(
            settled_at__year=year,
            settled_at__month=month
        ).select_related('user', 'user__profile').prefetch_related(
            'selections', 'selections__selection', 'selections__selection__market', 'selections__selection__market__event'
        ).order_by('settled_at')

        # Configurar la respuesta HTTP como un archivo CSV descargable
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        
        # BOM de UTF-8 para compatibilidad perfecta con Excel en Windows
        response.write(u'\ufeff'.encode('utf-8'))

        filename = f"reporte_mincetur_{year}_{month:02d}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)

        # Encabezados de columnas alineados a los estándares de la Ley 31557 peruana
        headers = [
            'ticket_id',
            'dni_jugador',
            'username',
            'fecha_colocacion',
            'fecha_liquidacion',
            'tipo_apuesta',
            'evento_seleccion',
            'cuota',
            'monto_apostado',
            'estado_apuesta',
            'monto_pagado',
            'ggr',
            'moneda'
        ]
        writer.writerow(headers)

        # Escribir los registros correspondientes
        for bet in bets:
            # Obtener el DNI desde el perfil del usuario (KYC obligatorio de la Fase 1)
            dni = bet.user.profile.dni if hasattr(bet.user, 'profile') else 'N/A'

            # Agrupar las selecciones en un formato legible
            sel_details = []
            for bs in bet.selections.all():
                event = bs.selection.market.event
                sel_details.append(
                    f"{event.home_team.name} vs {event.away_team.name} "
                    f"({bs.selection.market.name}: {bs.selection.name})"
                )
            evento_seleccion = " | ".join(sel_details)

            # Calcular la cuota final acumulada
            cuota = Decimal('1.0000')
            if bet.selections.exists():
                for bs in bet.selections.all():
                    cuota *= bs.odds_at_bet
            else:
                cuota = bet.potential_payout / bet.stake if bet.stake > 0 else Decimal('1.0000')

            # Determinar el monto pagado final según el estado de la apuesta
            payout = Decimal('0.0000')
            if bet.status == 'won':
                payout = bet.potential_payout
            elif bet.status == 'cashed_out':
                payout = bet.potential_payout
            elif bet.status == 'cancelled':
                payout = bet.stake

            ggr_ticket = bet.stake - payout

            row = [
                bet.id,
                dni,
                bet.user.username,
                bet.created_at.isoformat(),
                bet.settled_at.isoformat() if bet.settled_at else '',
                bet.get_type_display(),
                evento_seleccion,
                f"{cuota:.4f}",
                f"{bet.stake:.4f}",
                bet.get_status_display(),
                f"{payout:.4f}",
                f"{ggr_ticket:.4f}",
                'Fichas Virtuales'
            ]
            writer.writerow(row)

        return response
