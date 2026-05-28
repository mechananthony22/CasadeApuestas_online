# -*- coding: utf-8 -*-
from celery import shared_task
from django.utils import timezone
from django.db import models
from datetime import timedelta
from fraud.models import SuspiciousActivity, UserIpLog
from fraud.services import FraudDetector
from wallet.models import LedgerEntry
from betting.models import Bet
import logging

logger = logging.getLogger(__name__)


@shared_task
def rescan_fraud_patterns():
    """
    Tarea periódica de Celery para escanear retroactivamente patrones de fraude
    en el historial de movimientos y apuestas. Se ejecuta cada 1 hora.

    Detecta:
    - Depósitos seguidos de cash-out en menos de 15 min (lavado)
    - Apuestas idénticas de múltiples usuarios en ventana de 5 min (sindicalización)
    - IPs compartidas por más de 3 cuentas (multicuenta)
    """
    logger.info("Iniciando escaneo retroactivo de patrones de fraude...")
    try:
        cutoff = timezone.now() - timedelta(hours=1)
        alerts_created = 0

        # REGLA 2: Cash-out inmediato tras depósito (15 min)
        suspicious_deposits = LedgerEntry.objects.filter(
            created_at__gte=cutoff,
            account=LedgerEntry.Account.WALLET_USUARIO,
            direction=LedgerEntry.Direction.CREDIT,
            description__icontains='Recarga'
        ).values_list('user', 'transaction_id').distinct()

        for user_id, tx_id in suspicious_deposits:
            try:
                from django.contrib.auth.models import User
                user = User.objects.get(id=user_id)
                recent_bet = Bet.objects.filter(
                    user=user,
                    created_at__gte=timezone.now() - timedelta(minutes=15),
                    status='accepted'
                ).first()
                if recent_bet:
                    result = FraudDetector.check_deposit_cashout_pattern(user, recent_bet)
                    if result:
                        alerts_created += 1
            except Exception as e:
                logger.error(f"Error al verificar patrón depósito-cashout para usuario {user_id}: {e}")

        # REGLA 3: Apuestas idénticas en grupo (sindicalización)
        cutoff_bets = timezone.now() - timedelta(minutes=5)
        recent_bets = Bet.objects.filter(
            created_at__gte=cutoff_bets,
            status='accepted'
        ).prefetch_related('selections')

        processed_groups = set()
        for bet in recent_bets:
            current_selection_ids = tuple(sorted(bet.selections.values_list('selection_id', flat=True)))
            if len(current_selection_ids) > 1:
                group_key = (current_selection_ids, bet.stake)
                if group_key not in processed_groups:
                    result = FraudDetector.check_syndicated_betting(bet)
                    if result:
                        alerts_created += 1
                    processed_groups.add(group_key)

        # REGLA 1: IPs compartidas por más de 3 usuarios
        from fraud.models import UserIpLog
        from django.contrib.auth.models import User

        suspicious_ips = UserIpLog.objects.filter(
            created_at__gte=cutoff
        ).values('ip_address').annotate(
            count=models.Count('user', distinct=True)
        ).filter(count__gt=3)

        for ip_data in suspicious_ips:
            ip = ip_data['ip_address']
            distinct_users = UserIpLog.objects.filter(ip_address=ip).values_list('user_id', flat=True).distinct()
            associated_usernames = list(User.objects.filter(id__in=distinct_users).values_list('username', flat=True))

            if SuspiciousActivity.objects.filter(
                activity_type=SuspiciousActivity.TYPE_MULTIPLE_ACCOUNTS,
                payload__ip_address=ip
            ).exists():
                continue

            SuspiciousActivity.objects.create(
                user=None,
                activity_type=SuspiciousActivity.TYPE_MULTIPLE_ACCOUNTS,
                description=f"Rescan: IP {ip} utilizada por {len(associated_usernames)} cuentas distintas.",
                payload={'ip_address': ip, 'usuarios': associated_usernames, 'source': 'rescan_task'},
                severity=SuspiciousActivity.SEVERITY_MEDIUM,
                status=SuspiciousActivity.STATUS_PENDING
            )
            alerts_created += 1

        logger.info(f"Escaneo de fraude completado. Alertas creadas: {alerts_created}")
        return f"Escaneo completado. Alertas creadas: {alerts_created}"
    except Exception as e:
        logger.error(f"Error crítico en tarea rescan_fraud_patterns: {e}")
        return f"Error: {str(e)}"