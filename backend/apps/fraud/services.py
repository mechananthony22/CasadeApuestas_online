# -*- coding: utf-8 -*-
# Motor de detección de fraude en tiempo real para FairBet Lab
import logging
from django.utils import timezone
from django.contrib.auth.models import User
from wallet.models import LedgerEntry
from betting.models import Bet
from fraud.models import UserIpLog, SuspiciousActivity

logger = logging.getLogger(__name__)

class FraudDetector:
    """
    Servicio central de análisis forense y detección de fraude en FairBet Lab. Implementa reglas heurísticas en base a la Ley 31557 peruana.
    """

    @classmethod
    def log_and_check_ip(cls, user, ip_address):
        """
        Regla 1: Registra el uso de IP y audita si la dirección IP actual está siendo utilizada por más de 3 cuentas distintas (multicuenta).
        """
        if not ip_address:
            return None

        # 1. Registrar el uso de la IP por este usuario
        UserIpLog.objects.create(user=user, ip_address=ip_address)
        
        # 2. Obtener lista de usuarios distintos asociados a esta IP
        distinct_users = UserIpLog.objects.filter(ip_address=ip_address).values_list('user_id', flat=True).distinct()
        distinct_count = distinct_users.count()
        
        # Si se superan las 3 cuentas distintas, gatillar alerta
        if distinct_count > 3:
            associated_usernames = list(User.objects.filter(id__in=distinct_users).values_list('username', flat=True))
            desc = f"Se detectó un patrón de multicuenta: la dirección IP {ip_address} ha sido utilizada por {distinct_count} cuentas distintas."
            
            alert, created = SuspiciousActivity.objects.get_or_create(
                activity_type=SuspiciousActivity.TYPE_MULTIPLE_ACCOUNTS,
                payload={'ip_address': ip_address, 'usuarios': associated_usernames},
                defaults={
                    'user': user,
                    'description': desc,
                    'severity': SuspiciousActivity.SEVERITY_MEDIUM,
                    'status': SuspiciousActivity.STATUS_PENDING
                }
            )
            if created:
                logger.warning(f"ALERTA ANTI-FRAUDE: IP {ip_address} compartida por {distinct_count} usuarios.")
            return alert
            
        return None

    @classmethod
    def check_deposit_cashout_pattern(cls, user, bet):
        """
        Regla 2: Detecta si el usuario está realizando un Cash-out inmediato dentro de los 15 minutos posteriores a registrar una recarga de saldo (lavado).
        """
        cutoff = timezone.now() - timezone.timedelta(minutes=15)
        
        # Buscar recargas en la billetera virtual en los últimos 15 minutos
        recent_deposits = LedgerEntry.objects.filter(
            user=user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            direction=LedgerEntry.Direction.CREDIT,
            description__icontains='Recarga',
            created_at__gte=cutoff
        )
        
        if recent_deposits.exists():
            deposit_details = [
                {'ledger_id': d.id, 'monto': str(d.amount), 'fecha': d.created_at.isoformat()}
                for d in recent_deposits
            ]
            desc = f"Sospecha de lavado de activos virtual: el usuario {user.username} intentó realizar cash-out en menos de 15 minutos tras una recarga de saldo."
            
            alert = SuspiciousActivity.objects.create(
                user=user,
                activity_type=SuspiciousActivity.TYPE_DEPOSIT_CASHOUT,
                description=desc,
                payload={'bet_id': bet.id, 'stake': str(bet.stake), 'depositos_recientes': deposit_details},
                severity=SuspiciousActivity.SEVERITY_HIGH,
                status=SuspiciousActivity.STATUS_PENDING
            )
            logger.warning(f"ALERTA ANTI-FRAUDE: Cash-out sospechoso por usuario '{user.username}' tras recarga reciente.")
            return alert
            
        return None

    @classmethod
    def check_syndicated_betting(cls, bet):
        """
        Regla 3: Detecta patrones de apuestas idénticas en grupo (sindicalización). Si 3 o más usuarios distintos colocan apuestas por el mismo monto y sobre las mismas selecciones en menos de 5 minutos, se levanta una alerta por amaño.
        """
        cutoff = timezone.now() - timezone.timedelta(minutes=5)
        
        # Obtener las selecciones que componen la apuesta actual
        current_selection_ids = set(bet.selections.values_list('selection_id', flat=True))
        if not current_selection_ids:
            return None

        # Filtrar otras apuestas con idéntico stake en la ventana de 5 minutos
        other_bets = Bet.objects.filter(
            created_at__gte=cutoff,
            stake=bet.stake
        ).exclude(user=bet.user).prefetch_related('selections')
        
        syndicated_users = set()
        for ob in other_bets:
            ob_selection_ids = set(ob.selections.values_list('selection_id', flat=True))
            if ob_selection_ids == current_selection_ids:
                syndicated_users.add(ob.user)

        # Si el grupo total (incluyendo el actual) es >= 3 usuarios distintos
        total_group_count = len(syndicated_users) + 1
        if total_group_count >= 3:
            syndicated_usernames = [bet.user.username] + [u.username for u in syndicated_users]
            desc = f"Apuestas idénticas en grupo detectadas: {total_group_count} usuarios distintos colocaron boletos idénticos con stake {bet.stake} fichas."
            
            alert, created = SuspiciousActivity.objects.get_or_create(
                activity_type=SuspiciousActivity.TYPE_IDENTICAL_BET,
                payload={'stake': str(bet.stake), 'selecciones': list(current_selection_ids), 'usuarios': syndicated_usernames},
                defaults={
                    'user': bet.user,
                    'description': desc,
                    'severity': SuspiciousActivity.SEVERITY_HIGH,
                    'status': SuspiciousActivity.STATUS_PENDING
                }
            )
            if created:
                logger.warning(f"ALERTA ANTI-FRAUDE: Patrón de apuestas coordinadas detectado para usuarios: {syndicated_usernames}.")
            return alert
            
        return None

    @classmethod
    def check_bonus_arbitrage(cls, user, bet):
        """
        Regla 4: Detecta abuso de bonos mediante apuestas cruzadas (hedge betting/arbitraje). Si el usuario tiene un bono de bienvenida activo y realiza apuestas cubriendo resultados mutuamente excluyentes del mismo evento deportivo, se levanta una alerta.
        """
        # 1. Verificar si el usuario tiene un bono activo
        from wallet.models import UserBonus
        try:
            if not hasattr(user, 'promo_bonus') or not user.promo_bonus.is_active:
                return None
        except UserBonus.DoesNotExist:
            return None

        # 2. Obtener las selecciones que componen la apuesta actual
        current_selections = list(bet.selections.all().select_related('selection__market__event'))
        if not current_selections:
            return None

        # 3. Buscar otras apuestas activas ('accepted') del mismo usuario
        other_bets = Bet.objects.filter(
            user=user,
            status='accepted'
        ).exclude(id=bet.id).prefetch_related('selections__selection__market')

        # Para cada selección de la apuesta actual:
        for cs in current_selections:
            current_sel = cs.selection
            current_market = current_sel.market
            current_event = current_market.event

            # Buscar si alguna otra apuesta del mismo usuario cubre otra selección en el mismo mercado
            for ob in other_bets:
                for obs in ob.selections.all():
                    other_sel = obs.selection
                    # Si pertenecen al mismo mercado pero son selecciones diferentes, hay cobertura/arbitraje
                    if other_sel.market_id == current_market.id and other_sel.id != current_sel.id:
                        desc = (
                            f"Posible abuso de bono (apuestas cruzadas) detectado para el usuario {user.username}. "
                            f"Colocó apuestas cubriendo múltiples resultados en el mercado '{current_market.name}' "
                            f"para el evento '{current_event.home_team.name} vs {current_event.away_team.name}'."
                        )
                        
                        alert = SuspiciousActivity.objects.create(
                            user=user,
                            activity_type=SuspiciousActivity.TYPE_BONUS_ABUSE,
                            description=desc,
                            payload={
                                'bet_id_1': bet.id,
                                'bet_id_2': ob.id,
                                'market_id': current_market.id,
                                'market_name': current_market.name,
                                'event_id': current_event.id,
                                'event_name': f"{current_event.home_team.name} vs {current_event.away_team.name}",
                                'selection_1': current_sel.name,
                                'selection_2': other_sel.name
                            },
                            severity=SuspiciousActivity.SEVERITY_HIGH,
                            status=SuspiciousActivity.STATUS_PENDING
                        )
                        logger.warning(
                            f"ALERTA ANTI-FRAUDE: Abuso de bono detectado para el usuario '{user.username}' "
                            f"en el evento '{current_event.home_team.name} vs {current_event.away_team.name}'."
                        )
                        return alert
        return None

