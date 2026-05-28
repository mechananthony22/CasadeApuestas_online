# -*- coding: utf-8 -*-
# Vistas basadas en Django REST Framework para la aplicación betting
import uuid
from decimal import Decimal
from django.db import transaction
from django.core.cache import cache
from django.contrib.auth.models import User
from rest_framework import viewsets, permissions, status, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from betting.models import Event, Bet, BetSelection
from betting.serializers import EventSerializer, BetSerializer, OddsChangedException
from wallet.models import LedgerEntry

class EventViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from django.utils import timezone
        from datetime import timedelta

        # Auto-transición en caliente para entornos sin Celery Beat activo:
        # 1. Pasar a 'in_play' los partidos programados que ya comenzaron en la hora actual
        Event.objects.filter(
            status='scheduled',
            starts_at__lte=timezone.now()
        ).update(status='in_play')

        # 2. Pasar a 'finished' los partidos 'in_play' que comenzaron hace más de 3 horas
        finished_threshold = timezone.now() - timedelta(hours=3)
        Event.objects.filter(
            status='in_play',
            starts_at__lte=finished_threshold
        ).update(status='finished')

        # Excluir partidos finalizados o anulados del catálogo público
        queryset = Event.objects.exclude(status__in=['finished', 'cancelled'])

        queryset = queryset.select_related(
            'league', 'home_team', 'away_team'
        ).prefetch_related(
            'markets', 'markets__selections'
        ).order_by('starts_at')

        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            if status_filter in ['live', 'in_play']:
                queryset = queryset.filter(status='in_play')
            else:
                queryset = queryset.filter(status=status_filter)

        return queryset


class BetViewSet(viewsets.ModelViewSet):
    serializer_class = BetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Garantiza que el apostador común sólo pueda visualizar sus propios boletos de apuesta.
        """
        return Bet.objects.filter(user=self.request.user).prefetch_related(
            'selections',
            'selections__selection',
            'selections__selection__market',
            'selections__selection__market__event'
        ).order_by('-created_at')

    def create(self, request, *args, **kwargs):
        # 1. Obtener y validar cabecera de idempotencia
        idempotency_header = request.headers.get('Idempotency-Key')
        if not idempotency_header:
            return Response(
                {'error': 'El encabezado HTTP "Idempotency-Key" es obligatorio.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            idempotency_uuid = uuid.UUID(idempotency_header)
        except ValueError:
            return Response(
                {'error': 'El encabezado "Idempotency-Key" debe ser un UUID v4 válido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Consultar caché en Redis para verificar clave duplicada
        cache_key = f"idempotency_{idempotency_header}"
        cached_response = cache.get(cache_key)
        if cached_response:
            return Response(cached_response['data'], status=cached_response['status'])

        # 3. Serializar y validar reglas de negocio síncronas
        # --- CONTROLES DE ANTI-FRAUDE (REGLA IP) ---
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '127.0.0.1')).split(',')[0].strip()
        from fraud.services import FraudDetector
        FraudDetector.log_and_check_ip(request.user, ip)
        # --- FIN CONTROLES DE ANTI-FRAUDE ---

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except OddsChangedException as e:
            return Response(e.detail, status=status.HTTP_409_CONFLICT)
        except serializers.ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

        # 4. Procesamiento transaccional de la apuesta
        stake = serializer.validated_data['stake']
        selections_objs = serializer.context['loaded_selections']
        user = request.user

        try:
            with transaction.atomic():
                # Bloqueo pesimista en base de datos para el usuario para evitar doble gasto
                locked_user = User.objects.select_for_update().get(pk=user.pk)
                
                # Calcular saldo disponible del Ledger contable
                balance = LedgerEntry.get_user_balance(locked_user)
                if balance < stake:
                    return Response(
                        {
                            'error': 'Saldo insuficiente para colocar la apuesta.',
                            'saldo_actual': str(balance),
                            'monto_apuesta': str(stake)
                        },
                        status=status.HTTP_409_CONFLICT
                    )

                # Calcular la cuota multiplicadora total (combinada)
                total_odds = Decimal('1.0000')
                for s in selections_objs:
                    total_odds *= s.odds
                
                potential_payout = (stake * total_odds).quantize(Decimal('0.0001'))
                bet_type = 'simple' if len(selections_objs) == 1 else 'accumulator'

                # Crear objeto Bet principal
                bet_obj = Bet.objects.create(
                    user=locked_user,
                    status='accepted',
                    type=bet_type,
                    stake=stake,
                    potential_payout=potential_payout,
                    idempotency_key=idempotency_uuid
                )

                # Registrar las selecciones intermedias del ticket
                for s in selections_objs:
                    BetSelection.objects.create(
                        bet=bet_obj,
                        selection=s,
                        odds_at_bet=s.odds,
                        status='pending'
                    )

                # Contabilidad en partida doble:
                # - DÉBITO: wallet_usuario (sale saldo del balance disponible)
                # - CRÉDITO: apuestas_pendientes (fondos retenidos en garantía temporal)
                # Vinculamos la transacción inmutable usando la idempotency_key como transaction_id
                LedgerEntry.objects.create(
                    user=locked_user,
                    account=LedgerEntry.Account.WALLET_USUARIO,
                    amount=stake,
                    direction=LedgerEntry.Direction.DEBIT,
                    transaction_id=idempotency_uuid,
                    description=f"Débito por colocación de apuesta #{bet_obj.id}"
                )

                LedgerEntry.objects.create(
                    user=locked_user,
                    account=LedgerEntry.Account.APUESTAS_PENDIENTES,
                    amount=stake,
                    direction=LedgerEntry.Direction.CREDIT,
                    transaction_id=idempotency_uuid,
                    description=f"Retención en custodia por apuesta #{bet_obj.id}"
                )

                # --- ACTUALIZACIÓN DE ROLLOVER DEL BONO ---
                from wallet.models import UserBonus
                try:
                    # Obtenemos el bono activo del usuario bloqueando su registro de forma segura
                    promo_bonus = UserBonus.objects.select_for_update().get(user=locked_user, is_active=True)
                    # Apuestas elegibles con cuota total >= 1.5000
                    if total_odds >= Decimal('1.5000'):
                        promo_bonus.current_turnover += stake
                        if promo_bonus.current_turnover >= promo_bonus.required_turnover:
                            promo_bonus.is_active = False
                        promo_bonus.save()
                except UserBonus.DoesNotExist:
                    pass

        except Exception as e:
            return Response(
                {'error': f"Error interno al colocar la apuesta transaccional: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 5. Serializar salida
        output_serializer = self.get_serializer(bet_obj)
        response_data = output_serializer.data

        # Enviar notificación ligera por Django Channels (Fase 6)
        self.broadcast_bet_placed(user.id, bet_obj.id)

        # --- CONTROLES DE ANTI-FRAUDE ---
        try:
            from fraud.services import FraudDetector
            FraudDetector.check_syndicated_betting(bet_obj)
            FraudDetector.check_bonus_arbitrage(user, bet_obj)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error al verificar reglas de anti-fraude: {str(e)}")
        # --- FIN CONTROLES DE ANTI-FRAUDE ---

        # 6. Registrar en la caché de Redis por 5 minutos (300 segundos) para idempotencia
        cache.set(cache_key, {'status': status.HTTP_201_CREATED, 'data': response_data}, timeout=300)

        # Agregar disclaimer obligatorio de juego responsable (Ley 31557)
        response_data['disclaimer'] = (
            'Juego responsable: El juego de apuestas en exceso puede causar adicción. '
            'Juega con moderación. Plataforma de simulación educativa con moneda virtual.'
        )

        return Response(response_data, status=status.HTTP_201_CREATED)

    def broadcast_bet_placed(self, user_id, bet_id):
        """
        Emite una notificación del ticket aceptado al grupo del usuario en Channels (Fase 6).
        """
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        'type': 'bet_accepted',
                        'bet_id': bet_id,
                        'message': '¡Tu apuesta ha sido aceptada con éxito en la plataforma!'
                    }
                )
        except Exception:
            pass

    @action(detail=True, methods=['post'])
    def cashout(self, request, pk=None):
        import uuid
        from decimal import Decimal
        from django.db import transaction
        from django.utils import timezone
        
        # 1. Obtener y bloquear la apuesta pesimistamente en base de datos
        try:
            with transaction.atomic():
                # select_for_update para evitar condiciones de carrera o cobros dobles
                bet_obj = Bet.objects.select_for_update().get(pk=pk, user=request.user)
                
                # 2. Validaciones iniciales del estado de la apuesta
                if bet_obj.status != 'accepted':
                    return Response(
                        {'error': f"No se puede realizar cash-out en una apuesta en estado: {bet_obj.get_status_display()}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # 3. Validar que ninguno de los eventos asociados a la apuesta haya finalizado o esté suspendido/cancelado
                selections = bet_obj.selections.all().select_related('selection__market__event')
                for s in selections:
                    event = s.selection.market.event
                    if event.status in ['finished', 'cancelled', 'suspended']:
                        return Response(
                            {'error': f"El cash-out no está disponible porque el evento '{event.home_team.name} vs {event.away_team.name}' está en estado '{event.get_status_display()}'."},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    if not s.selection.is_active or not s.selection.market.is_active:
                        return Response(
                            {'error': f"El cash-out no está disponible porque una de las selecciones o mercados ya no está activa."},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                # 4. Calcular odds_original y odds_actual
                odds_original = Decimal('1.0000')
                odds_actual = Decimal('1.0000')
                
                for s in selections:
                    odds_original *= s.odds_at_bet
                    fresh_selection = s.selection
                    if fresh_selection.odds <= Decimal('0.0000'):
                        return Response(
                            {'error': "Error al calcular el cash-out debido a una cuota inválida en el mercado actual."},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    odds_actual *= fresh_selection.odds
                
                # 5. Aplicar fórmula actuarial con factor de casa del 5% (0.95)
                factor_casa = Decimal('0.95')
                cashout_amount = (bet_obj.stake * (odds_original / odds_actual) * factor_casa).quantize(Decimal('0.0001'))
                
                # El cobro mínimo no puede ser menor a 0.01 virtual
                if cashout_amount < Decimal('0.0100'):
                    cashout_amount = Decimal('0.0100')
                
                # 6. Ejecutar la transacción de cash-out y partida doble contable
                tx_id = uuid.uuid4()
                bet_obj.perform_cash_out(cashout_amount=cashout_amount, transaction_id=tx_id)

                # --- CONTROLES DE ANTI-FRAUDE (REGLA DE CASHOUT INMEDIATO) ---
                try:
                    from fraud.services import FraudDetector
                    FraudDetector.check_deposit_cashout_pattern(request.user, bet_obj)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Error al verificar patrón de depósito inmediato y cashout: {str(e)}")
                # --- FIN CONTROLES DE ANTI-FRAUDE ---
                
        except Bet.DoesNotExist:
            return Response(
                {'error': "Apuesta no encontrada o no pertenece al usuario autenticado."},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f"Error interno en el procesamiento del cash-out: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
        # 7. Serializar y retornar respuesta exitosa
        try:
            self.broadcast_cash_out_placed(request.user.id, bet_obj.id, cashout_amount)
        except Exception:
            pass
            
        serializer = self.get_serializer(bet_obj)
        response_data = serializer.data

        # Agregar disclaimer obligatorio de juego responsable al cash-out (Ley 31557)
        response_data['disclaimer'] = (
            'Juego responsable: El juego de apuestas en exceso puede causar adicción. '
            'Juega con moderación. Plataforma de simulación educativa con moneda virtual.'
        )

        return Response(response_data, status=status.HTTP_200_OK)

    def broadcast_cash_out_placed(self, user_id, bet_id, amount):
        """
        Emite una notificación del cash-out aceptado en Channels.
        """
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_id}",
                    {
                        'type': 'cashout_accepted',
                        'bet_id': bet_id,
                        'amount': str(amount),
                        'message': f'¡Cobro anticipado (Cash-out) procesado con éxito por {amount} fichas!'
                    }
                )
        except Exception:
            pass
