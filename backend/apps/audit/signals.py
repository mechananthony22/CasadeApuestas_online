# -*- coding: utf-8 -*-
# Interceptores de señales de Django para registro automático en la cadena de auditoría SHA-256
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from wallet.models import LedgerEntry
from betting.models import Bet, Selection, Event, Market
from audit.models import AuditLogEntry

logger = logging.getLogger(__name__)

@receiver(post_save, sender=LedgerEntry)
def audit_wallet_entry(sender, instance, created, **kwargs):
    """
    Escucha la creación de LedgerEntry y la registra automáticamente en
    la bitácora inmutable de auditoría (Fase 8).
    """
    if created:
        try:
            payload = {
                'ledger_entry_id': instance.id,
                'user_id': instance.user.id if instance.user else None,
                'username': instance.user.username if instance.user else 'casa',
                'account': instance.account,
                'amount': str(instance.amount),
                'direction': instance.direction,
                'transaction_id': str(instance.transaction_id),
                'description': instance.description,
                'created_at': instance.created_at.isoformat() if instance.created_at else timezone.now().isoformat()
            }
            
            # Registrar en la cadena inmutable
            AuditLogEntry.objects.create(
                event_type=AuditLogEntry.EVENT_WALLET_MOVEMENT,
                payload=payload
            )
            logger.info(f"Auditoría: Registro contable #{instance.id} indexado exitosamente.")
        except Exception as e:
            logger.error(f"Error al auditar LedgerEntry #{instance.id}: {str(e)}")


@receiver(post_save, sender=Bet)
def audit_bet_change(sender, instance, created, **kwargs):
    """
    Escucha los cambios de estado y colocación de boletos de apuestas (Bet)
    y los registra en la cadena inmutable (Fase 8).
    """
    try:
        payload = {
            'bet_id': instance.id,
            'user_id': instance.user.id,
            'username': instance.user.username,
            'status': instance.status,
            'type': instance.type,
            'stake': str(instance.stake),
            'potential_payout': str(instance.potential_payout),
            'idempotency_key': str(instance.idempotency_key),
            'created_at': instance.created_at.isoformat() if instance.created_at else timezone.now().isoformat(),
            'settled_at': instance.settled_at.isoformat() if instance.settled_at else None
        }
        
        # Registrar en la cadena inmutable
        AuditLogEntry.objects.create(
            event_type=AuditLogEntry.EVENT_BET_STATUS_CHANGE,
            payload=payload
        )
        accion = "colocada" if created else f"actualizada a estado '{instance.status}'"
        logger.info(f"Auditoría: Apuesta #{instance.id} {accion} e indexada exitosamente.")
    except Exception as e:
        logger.error(f"Error al auditar Bet #{instance.id}: {str(e)}")


@receiver(pre_save, sender=Selection)
def pre_save_selection(sender, instance, **kwargs):
    """
    Guarda las cuotas previas en memoria para detectar variaciones
    en el receptor post_save.
    """
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._old_odds = old_instance.odds
        except sender.DoesNotExist:
            instance._old_odds = None
    else:
        instance._old_odds = None


@receiver(post_save, sender=Selection)
def audit_selection_odds_change(sender, instance, created, **kwargs):
    """
    Detecta fluctuaciones en las cuotas de selecciones deportivas y
    las documenta en la bitácora inmutable de auditoría (Fase 8).
    """
    try:
        old_odds = getattr(instance, '_old_odds', None)
        new_odds = instance.odds

        # Solo registrar si no es nueva creación y si hubo fluctuación en el valor
        if not created and old_odds is not None and old_odds != new_odds:
            payload = {
                'selection_id': instance.id,
                'selection_name': instance.name,
                'market_id': instance.market.id,
                'market_name': instance.market.name,
                'event_id': instance.market.event.id,
                'event_display': f"{instance.market.event.home_team.name} vs {instance.market.event.away_team.name}",
                'old_odds': str(old_odds),
                'new_odds': str(new_odds),
                'changed_at': timezone.now().isoformat()
            }

            AuditLogEntry.objects.create(
                event_type=AuditLogEntry.EVENT_ODDS_CHANGE,
                payload=payload
            )
            logger.info(f"Auditoría: Variación de cuota en selección '{instance.name}' indexada ({old_odds} -> {new_odds}).")
    except Exception as e:
        logger.error(f"Error al auditar cambio de cuota en Selección #{instance.id}: {str(e)}")


@receiver(pre_save, sender=Event)
def pre_save_event(sender, instance, **kwargs):
    """
    Guarda el estado previo del evento para detectar cambios de estado
    (scheduled -> in_play -> finished, etc.).
    """
    if instance.pk:
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
            instance._old_home_score = old_instance.home_score
            instance._old_away_score = old_instance.away_score
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Event)
def audit_event_status_change(sender, instance, created, **kwargs):
    """
    Registra cambios de estado en eventos (scheduled, in_play, finished, suspended, cancelled)
    en la cadena de auditoría para trazabilidad regulatoria completa.
    """
    old_status = getattr(instance, '_old_status', None)

    if created:
        payload = {
            'event_id': instance.id,
            'api_id': instance.api_id,
            'league_id': instance.league.id,
            'league_name': instance.league.name,
            'home_team': instance.home_team.name,
            'away_team': instance.away_team.name,
            'starts_at': instance.starts_at.isoformat() if instance.starts_at else None,
            'action': 'CREATED',
            'initial_status': instance.status,
            'created_at': timezone.now().isoformat()
        }
        event_type = AuditLogEntry.EVENT_STATUS_CHANGE
    elif old_status and old_status != instance.status:
        payload = {
            'event_id': instance.id,
            'api_id': instance.api_id,
            'league_name': instance.league.name,
            'home_team': instance.home_team.name,
            'away_team': instance.away_team.name,
            'action': 'STATUS_CHANGE',
            'old_status': old_status,
            'new_status': instance.status,
            'home_score': instance.home_score,
            'away_score': instance.away_score,
            'changed_at': timezone.now().isoformat()
        }
        event_type = AuditLogEntry.EVENT_STATUS_CHANGE
    elif not created and old_status is None:
        pass
    else:
        return

    try:
        AuditLogEntry.objects.create(
            event_type=event_type,
            payload=payload
        )
        action_desc = payload.get('action', 'UNKNOWN')
        logger.info(f"Auditoría: Evento #{instance.id} [{action_desc}] indexado exitosamente.")
    except Exception as e:
        logger.error(f"Error al auditar Evento #{instance.id}: {str(e)}")


@receiver(post_save, sender=Market)
def audit_market_creation(sender, instance, created, **kwargs):
    """
    Registra la creación de Markets nuevos en la cadena
    de auditoría para trazabilidad completa del catálogo.
    """
    if created:
        try:
            payload = {
                'market_id': instance.id,
                'event_id': instance.event.id,
                'event_display': f"{instance.event.home_team.name} vs {instance.event.away_team.name}",
                'name': instance.name,
                'is_active': instance.is_active,
                'created_at': timezone.now().isoformat()
            }
            AuditLogEntry.objects.create(
                event_type=AuditLogEntry.MARKET_CREATION,
                payload=payload
            )
            logger.info(f"Auditoría: Market #{instance.id} '{instance.name}' creado e indexado.")
        except Exception as e:
            logger.error(f"Error al auditar Market #{instance.id}: {str(e)}")


@receiver(post_save, sender=Selection)
def audit_selection_creation(sender, instance, created, **kwargs):
    """
    Registra la creación de Selections nuevas en la cadena
    de auditoría para trazabilidad completa del catálogo.
    """
    if created:
        try:
            payload = {
                'selection_id': instance.id,
                'market_id': instance.market.id,
                'market_name': instance.market.name,
                'event_id': instance.market.event.id,
                'name': instance.name,
                'odds': str(instance.odds),
                'is_active': instance.is_active,
                'created_at': timezone.now().isoformat()
            }
            AuditLogEntry.objects.create(
                event_type=AuditLogEntry.SELECTION_CREATION,
                payload=payload
            )
            logger.info(f"Auditoría: Selection #{instance.id} '{instance.name}' creada e indexada.")
        except Exception as e:
            logger.error(f"Error al auditar Selection #{instance.id}: {str(e)}")
