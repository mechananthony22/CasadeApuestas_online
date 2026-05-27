# -*- coding: utf-8 -*-
# Tareas periódicas de Celery para la sincronización de eventos y cuotas
import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from betting.models import Event
from betting.services import SyncEngine

logger = logging.getLogger(__name__)

@shared_task
def sync_fixtures():
    """
    Tarea periódica de Celery para sincronizar eventos deportivos y ligas futuras.
    Se ejecuta por defecto cada 2 horas.
    """
    logger.info("Iniciando sincronización periódica de fixtures deportivos...")
    try:
        engine = SyncEngine()
        # Obtener ligas configuradas (ej: [39, 140])
        leagues = list(getattr(settings, 'THE_ODDS_API_SPORTS', {39: None, 140: None}).keys())
        season = timezone.now().year if timezone.now().month > 6 else timezone.now().year - 1
        
        total_synced = 0
        for league_id in leagues:
            logger.info(f"Sincronizando partidos de liga {league_id} para la temporada {season}")
            count = engine.sync_fixtures(league_id, season=season)
            total_synced += count
            
        logger.info(f"Sincronización de fixtures completada. Total partidos procesados: {total_synced}")
        return f"Éxito: {total_synced} partidos sincronizados."
    except Exception as e:
        logger.error(f"Error crítico en la tarea sync_fixtures: {e}")
        return f"Error: {str(e)}"


@shared_task
def sync_live_scores():
    """
    Tarea periódica de Celery para sincronizar marcadores de partidos en vivo.
    Se ejecuta de manera agresiva cada 30 segundos.
    """
    logger.debug("Iniciando sincronización rápida de marcadores en vivo...")
    try:
        engine = SyncEngine()
        count = engine.sync_live_scores()
        logger.debug(f"Sincronización de marcadores en vivo completada. Eventos actualizados: {count}")
        return f"Marcadores actualizados: {count}"
    except Exception as e:
        logger.error(f"Error crítico en la tarea sync_live_scores: {e}")
        return f"Error: {str(e)}"


@shared_task
def update_odds():
    """
    Tarea periódica de Celery para actualizar cuotas y cuotas en vivo.
    Se ejecuta cada 10 segundos buscando eventos activos/en juego.
    """
    logger.debug("Iniciando actualización periódica de cuotas...")
    try:
        engine = SyncEngine()
        
        # Filtrar solo eventos locales activos ("En Vivo" o programados que inicien pronto)
        # Esto reduce el consumo innecesario de peticiones HTTP a la API externa
        active_events = Event.objects.filter(status='in_play')
        
        if not active_events.exists():
            logger.debug("No hay partidos en juego para actualizar cuotas de forma prioritaria.")
            return "Sin partidos en juego."
            
        total_odds_updated = 0
        for event in active_events:
            logger.info(f"Actualizando cuotas en vivo para evento ID {event.api_id}")
            engine.sync_odds_for_event(event)
            total_odds_updated += 1
            
        return f"Cuotas actualizadas para {total_odds_updated} partidos activos."
    except Exception as e:
        logger.error(f"Error crítico en la tarea update_odds: {e}")
        return f"Error: {str(e)}"


@shared_task
def settle_finished_matches():
    """
    Tarea periódica de Celery para liquidar las apuestas cuyos eventos hayan finalizado o hayan sido cancelados.
    Calcula los resultados de cada selección, actualiza el estado de las apuestas
    y genera los asientos contables en partida doble.
    """
    import uuid
    from decimal import Decimal
    from django.db import transaction
    from betting.models import Bet, BetSelection

    logger.info("Iniciando liquidación de apuestas para partidos finalizados/anulados...")
    try:
        # 1. Resolver selecciones individuales en eventos 'finished' o 'cancelled'
        pending_selections = BetSelection.objects.filter(
            status='pending',
            selection__market__event__status__in=['finished', 'cancelled']
        ).select_related('selection__market__event')

        resolved_count = 0
        for bs in pending_selections:
            event = bs.selection.market.event
            
            if event.status == 'cancelled':
                bs.status = 'void'
                bs.save()
                resolved_count += 1
                logger.info(f"Selección #{bs.id} (Apuesta #{bs.bet.id}) marcada como ANULADA debido a cancelación del partido.")
            
            elif event.status == 'finished':
                home_score = event.home_score
                away_score = event.away_score
                
                if home_score is None or away_score is None:
                    logger.warning(f"El evento #{event.id} ({event.home_team.name} vs {event.away_team.name}) está finalizado pero no tiene goles registrados. Omitiendo selección #{bs.id}.")
                    continue
                
                market_name = bs.selection.market.name
                selection_name = bs.selection.name
                
                won = False
                if market_name == "1X2":
                    if selection_name == "Local" and home_score > away_score:
                        won = True
                    elif selection_name == "Empate" and home_score == away_score:
                        won = True
                    elif selection_name == "Visitante" and home_score < away_score:
                        won = True
                elif market_name == "Over/Under 2.5":
                    total_goals = home_score + away_score
                    if selection_name == "Over" and total_goals > 2.5:
                        won = True
                    elif selection_name == "Under" and total_goals < 2.5:
                        won = True
                elif market_name == "BTTS":
                    if selection_name == "Sí" and home_score > 0 and away_score > 0:
                        won = True
                    elif selection_name == "No" and (home_score == 0 or away_score == 0):
                        won = True
                
                bs.status = 'won' if won else 'lost'
                bs.save()
                resolved_count += 1
                logger.info(f"Selección #{bs.id} (Apuesta #{bs.bet.id}) resuelta como {bs.get_status_display().upper()}. Marcador: {home_score}-{away_score}.")

        # 2. Buscar y liquidar boletos de apuestas (Bet) en estado 'accepted'
        accepted_bets = Bet.objects.filter(status='accepted')
        settled_count = 0

        for bet in accepted_bets:
            # Bloqueo transaccional para cada boleto
            try:
                did_settle = False
                with transaction.atomic():
                    # select_for_update para evitar conflictos de concurrencia/cashout
                    locked_bet = Bet.objects.select_for_update().get(pk=bet.pk)
                    
                    # Si ya no está en accepted (por ejemplo, cobrado por cashout mientras procesaba), omitir
                    if locked_bet.status != 'accepted':
                        continue
                        
                    selections = locked_bet.selections.all()
                    
                    # Si alguna selección aún está pendiente, no podemos liquidar el boleto completo
                    if selections.filter(status='pending').exists():
                        continue
                        
                    # Verificar si hay alguna selección perdida
                    has_lost = selections.filter(status='lost').exists()
                    tx_id = uuid.uuid4()
                    
                    if has_lost:
                        # Apuesta perdida
                        locked_bet.settle_as_lost(transaction_id=tx_id)
                        settled_count += 1
                        logger.info(f"Apuesta #{locked_bet.id} de {locked_bet.user.username} liquidada como PERDIDA. Tx: {tx_id}")
                        did_settle = True
                    else:
                        # Todas están resueltas y ninguna perdida (todas ganadas o anuladas)
                        # Comprobar si todas son void
                        all_void = not selections.exclude(status='void').exists()
                        
                        if all_void:
                            # Reembolso completo por anulación total
                            locked_bet.settle_as_cancelled(transaction_id=tx_id)
                            settled_count += 1
                            logger.info(f"Apuesta #{locked_bet.id} de {locked_bet.user.username} liquidada como CANCELADA (reembolso total). Tx: {tx_id}")
                            did_settle = True
                        else:
                            # Apuesta ganadora! Calcular payout dinámico
                            payout_multiplier = Decimal('1.0000')
                            for s in selections:
                                if s.status == 'won':
                                    payout_multiplier *= s.odds_at_bet
                                elif s.status == 'void':
                                    payout_multiplier *= Decimal('1.0000')
                                    
                            payout_amount = (locked_bet.stake * payout_multiplier).quantize(Decimal('0.0001'))
                            locked_bet.settle_as_won(payout_amount, transaction_id=tx_id)
                            settled_count += 1
                            logger.info(f"Apuesta #{locked_bet.id} de {locked_bet.user.username} liquidada como GANADA con payout {payout_amount}. Tx: {tx_id}")
                            did_settle = True

                # Emitir notificación por Channels después de que la transacción se haya confirmado con éxito
                if did_settle:
                    try:
                        from channels.layers import get_channel_layer
                        from asgiref.sync import async_to_sync
                        channel_layer = get_channel_layer()
                        if channel_layer:
                            async_to_sync(channel_layer.group_send)(
                                f"user_{locked_bet.user.id}",
                                {
                                    "type": "bet_settled",
                                    "bet_id": locked_bet.id,
                                    "status": locked_bet.status,
                                    "payout": str(locked_bet.potential_payout) if locked_bet.status == 'won' else "0.0000",
                                    "message": f"Tu apuesta #{locked_bet.id} ha sido resuelta como {locked_bet.get_status_display().upper()}."
                                }
                            )
                    except Exception as ws_err:
                        logger.error(f"Error al transmitir WebSocket de liquidación para apuesta #{locked_bet.id}: {ws_err}")

            except Exception as e:
                logger.error(f"Error al liquidar apuesta #{bet.id} de forma transaccional: {e}")
                continue

        return f"Liquidación completada. Selecciones resueltas: {resolved_count}. Apuestas liquidadas: {settled_count}."
    
    except Exception as e:
        logger.error(f"Error crítico en la tarea settle_finished_matches: {e}")
        return f"Error: {str(e)}"


@shared_task
def resume_markets_after_suspension(event_id):
    """
    Reanuda la actividad de los mercados de un evento deportivo tras la suspensión automática
    y transmite la reanudación vía WebSockets a los clientes conectados.
    """
    from betting.models import Market
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    logger.info(f"Iniciando reactivación automática de mercados para evento ID {event_id}...")
    try:
        # Activar mercados de forma atómica en BD
        updated_count = Market.objects.filter(event_id=event_id).update(is_active=True)
        logger.info(f"Reactivación completada en BD para evento ID {event_id}. Mercados reactivados: {updated_count}")

        # Enviar notificación de reanudación por WebSocket
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"event_{event_id}",
                {
                    'type': 'market_resumed',
                    'event_id': event_id,
                    'message': 'Los mercados se han reanudado y vuelven a recibir apuestas.'
                }
            )
        return f"Mercados reactivados para evento {event_id}. Cantidad: {updated_count}"
    except Exception as e:
        logger.error(f"Error al reactivar mercados para evento ID {event_id}: {e}")
        return f"Error: {str(e)}"

