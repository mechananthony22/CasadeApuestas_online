# -*- coding: utf-8 -*-
# Interceptores de señales de Django para registro automático en la cadena de auditoría SHA-256
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from wallet.models import LedgerEntry
from betting.models import Bet, Selection
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
            
            # Registrar en la cadena inmutable
            AuditLogEntry.objects.create(
                event_type=AuditLogEntry.EVENT_ODDS_CHANGE,
                payload=payload
            )
            logger.info(f"Auditoría: Variación de cuota en selección '{instance.name}' indexada ({old_odds} -> {new_odds}).")
    except Exception as e:
        logger.error(f"Error al auditar cambio de cuota en Selección #{instance.id}: {str(e)}")
