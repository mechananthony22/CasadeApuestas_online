# -*- coding: utf-8 -*-
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework import status
from decimal import Decimal
from datetime import timedelta
from django.db import models
from django.db.models import Sum, Count, Case, When, F, Value, DecimalField
from django.utils import timezone
from django.contrib.auth.models import User
from betting.models import Bet, BetSelection, Event
from wallet.models import LedgerEntry
import csv
import io


class AdminUserMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser


def get_ggr_metrics():
    """
    Calcula las métricas de GGR (Gross Gaming Revenue) del operador. Considera únicamente apuestas resueltas/liquidadas.
    """
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
    return {
        'ggr': ggr,
        'total_stakes': total_stakes,
        'total_payouts': total_payouts
    }


def get_bet_volume_metrics():
    """
    Calcula métricas de volumen de apuestas: total, activas, últimas 24h.
    """
    total_bets_count = Bet.objects.count()
    total_stakes_amount = Bet.objects.aggregate(total=Sum('stake'))['total'] or Decimal('0.0000')

    active_bets_count = Bet.objects.filter(status='accepted').count()
    active_stakes_amount = Bet.objects.filter(status='accepted').aggregate(total=Sum('stake'))['total'] or Decimal('0.0000')

    limit_24h = timezone.now() - timedelta(days=1)
    today_bets_count = Bet.objects.filter(created_at__gte=limit_24h).count()
    today_stakes_amount = Bet.objects.filter(created_at__gte=limit_24h).aggregate(total=Sum('stake'))['total'] or Decimal('0.0000')

    return {
        'total_bets_count': total_bets_count,
        'total_stakes_amount': total_stakes_amount,
        'active_bets_count': active_bets_count,
        'active_stakes_amount': active_stakes_amount,
        'today_bets_count': today_bets_count,
        'today_stakes_amount': today_stakes_amount,
    }


def get_active_users_metrics():
    """
    Calcula métricas de usuarios activos: 24h, 7d, 30d, total.
    """
    def get_active_users(days):
        limit = timezone.now() - timedelta(days=days)
        return User.objects.filter(
            models.Q(last_login__gte=limit) |
            models.Q(bets__created_at__gte=limit) |
            models.Q(ledger_entries__created_at__gte=limit)
        ).distinct().count()

    return {
        'active_users_24h': get_active_users(1),
        'active_users_7d': get_active_users(7),
        'active_users_30d': get_active_users(30),
        'total_registered_users': User.objects.count(),
    }


def get_event_exposure_metrics():
    """
    Calcula la exposición financiera por evento y selección. Muestra cuánto pierde la casa si cada selección gana.
    """
    event_exposure = []
    active_events = Event.objects.filter(
        status__in=['scheduled', 'in_play']
    ).select_related('league', 'home_team', 'away_team').prefetch_related(
        'markets', 'markets__selections'
    ).order_by('starts_at')

    # Deduplicación: usar id como clave única
    seen_event_ids = set()
    events_to_process = []
    for event in active_events:
        if event.id in seen_event_ids:
            continue
        seen_event_ids.add(event.id)
        events_to_process.append(event)

    for event in events_to_process:
        event_data = {
            'event_id': event.id,
            'home_team': event.home_team.name,
            'away_team': event.away_team.name,
            'league_name': event.league.name,
            'starts_at': event.starts_at.isoformat() if event.starts_at else None,
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

            selections = market.selections.all()
            market_bets = BetSelection.objects.filter(
                selection__market=market,
                bet__status='accepted'
            ).select_related('bet')

            total_market_stake = sum(bs.bet.stake for bs in market_bets)

            for selection in selections:
                selection_bets = [bs for bs in market_bets if bs.selection_id == selection.id]
                bets_count = len(selection_bets)
                total_stake_sel = sum(bs.bet.stake for bs in selection_bets)
                gross_exp_sel = sum(bs.bet.potential_payout for bs in selection_bets)
                net_exp_sel = gross_exp_sel - total_market_stake

                market_data['selections'].append({
                    'selection_id': selection.id,
                    'selection_name': selection.name,
                    'odds': str(selection.odds),
                    'active_bets_count': bets_count,
                    'total_stake': str(total_stake_sel),
                    'gross_exposure': str(gross_exp_sel),
                    'net_exposure': str(net_exp_sel)
                })

            event_data['markets'].append(market_data)

        event_exposure.append(event_data)

    return event_exposure


class AdminDashboardView(LoginRequiredMixin, AdminUserMixin, TemplateView):
    """
    Vista HTML para el panel del operador/admin. Muestra métricas en vivo: GGR, volumen de apuestas, usuarios activos, exposure.
    """
    template_name = 'admin/dashboard.html'
    login_url = '/admin/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Panel del Operador'
        context['disclaimer'] = 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.'
        return context


class AdminMinceturView(LoginRequiredMixin, AdminUserMixin, TemplateView):
    """
    Vista HTML para la página de reportes MINCETUR. Permite seleccionar año/mes y descargar el CSV.
    """
    template_name = 'admin/mincetur.html'
    login_url = '/admin/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Reporte MINCETUR'
        context['current_year'] = timezone.now().year
        context['current_month'] = timezone.now().month
        context['years'] = list(range(timezone.now().year - 2, timezone.now().year + 1))
        context['months'] = [
            {'value': 1, 'name': 'Enero'}, {'value': 2, 'name': 'Febrero'},
            {'value': 3, 'name': 'Marzo'}, {'value': 4, 'name': 'Abril'},
            {'value': 5, 'name': 'Mayo'}, {'value': 6, 'name': 'Junio'},
            {'value': 7, 'name': 'Julio'}, {'value': 8, 'name': 'Agosto'},
            {'value': 9, 'name': 'Septiembre'}, {'value': 10, 'name': 'Octubre'},
            {'value': 11, 'name': 'Noviembre'}, {'value': 12, 'name': 'Diciembre'},
        ]
        return context


class AdminLogoutView(TemplateView):
    template_name = 'admin/login.html'

    def get(self, request, *args, **kwargs):
        from django.shortcuts import redirect
        return redirect('admin-login')


@method_decorator(csrf_exempt, name='dispatch')
class AdminLoginView(TemplateView):
    """
    Página de login simple para admins (no usa Django admin, es custom).
    """
    template_name = 'admin/login.html'


def get_active_events_for_catalog():
    """
    Obtiene los eventos activos para el catálogo del admin. Similar a la vista de usuario pero sin necesidad de token JWT.
    """
    from django.utils import timezone
    from datetime import timedelta

    active_events = Event.objects.filter(
        status__in=['scheduled', 'in_play']
    ).exclude(
        status__in=['finished', 'cancelled']
    ).select_related(
        'league', 'home_team', 'away_team'
    ).prefetch_related(
        'markets', 'markets__selections'
    ).order_by('starts_at')[:50]

    events_data = []
    for event in active_events:
        markets_data = []
        for market in event.markets.all():
            selections_data = []
            for sel in market.selections.all():
                selections_data.append({
                    'id': sel.id,
                    'name': sel.name,
                    'odds': str(sel.odds),
                    'is_active': sel.is_active
                })
            markets_data.append({
                'id': market.id,
                'name': market.name,
                'is_active': market.is_active,
                'selections': selections_data
            })

        events_data.append({
            'id': event.id,
            'home_team': {'id': event.home_team.id, 'name': event.home_team.name},
            'away_team': {'id': event.away_team.id, 'name': event.away_team.name},
            'league': {'id': event.league.id, 'name': event.league.name, 'sport': event.league.sport},
            'starts_at': event.starts_at.isoformat() if event.starts_at else None,
            'status': event.status,
            'home_score': event.home_score,
            'away_score': event.away_score,
            'markets': markets_data
        })

    return events_data


@method_decorator(csrf_exempt, name='dispatch')
class AdminMetricsAPIView(APIView):
    """
    API endpoint JSON para métricas del operador (polling desde el dashboard). Devuelve GGR, volumen, usuarios activos, exposure y catálogo de eventos.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        ggr_metrics = get_ggr_metrics()
        bet_volume = get_bet_volume_metrics()
        active_users = get_active_users_metrics()
        event_exposure = get_event_exposure_metrics()
        events_catalog = get_active_events_for_catalog()

        return Response({
            'ggr': str(ggr_metrics['ggr']),
            'total_stakes': str(ggr_metrics['total_stakes']),
            'total_payouts': str(ggr_metrics['total_payouts']),
            'bet_volume': {k: str(v) if isinstance(v, Decimal) else v for k, v in bet_volume.items()},
            'active_users': active_users,
            'event_exposure': event_exposure,
            'events': events_catalog,
            'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)


class AdminMinceturCSVAPIView(APIView):
    """
    API endpoint para descargar reporte MINCETUR en CSV. Filtra por año/mes y exporta todas las apuestas liquidadas.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        year_param = request.query_params.get('year')
        month_param = request.query_params.get('month')

        try:
            year = int(year_param) if year_param else timezone.now().year
            month = int(month_param) if month_param else timezone.now().month
        except ValueError:
            return Response(
                {'error': 'year y month deben ser números enteros'},
                status=status.HTTP_400_BAD_REQUEST
            )

        bets = Bet.objects.filter(
            settled_at__year=year,
            settled_at__month=month
        ).select_related('user', 'user__profile').prefetch_related(
            'selections', 'selections__selection', 'selections__selection__market',
            'selections__selection__market__event'
        ).order_by('settled_at')

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            'ticket_id', 'dni_jugador', 'username', 'fecha_colocacion',
            'fecha_liquidacion', 'tipo_apuesta', 'evento_seleccion',
            'cuota', 'monto_apostado', 'estado_apuesta', 'monto_pagado',
            'ggr', 'moneda'
        ]
        writer.writerow(headers)

        for bet in bets:
            dni = bet.user.profile.dni if hasattr(bet.user, 'profile') else 'N/A'

            sel_details = []
            for bs in bet.selections.all():
                event = bs.selection.market.event
                sel_details.append(
                    f"{event.home_team.name} vs {event.away_team.name} "
                    f"({bs.selection.market.name}: {bs.selection.name})"
                )
            evento_seleccion = " | ".join(sel_details)

            cuota = Decimal('1.0000')
            if bet.selections.exists():
                for bs in bet.selections.all():
                    cuota *= bs.odds_at_bet
            else:
                cuota = bet.potential_payout / bet.stake if bet.stake > 0 else Decimal('1.0000')

            payout = Decimal('0.0000')
            if bet.status == 'won':
                payout = bet.potential_payout
            elif bet.status == 'cashed_out':
                payout = bet.potential_payout
            elif bet.status == 'cancelled':
                payout = bet.stake

            ggr_ticket = bet.stake - payout

            row = [
                bet.id, dni, bet.user.username,
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

        output.seek(0)
        response = Response(output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="reporte_mincetur_{year}_{month:02d}.csv"'
        return response