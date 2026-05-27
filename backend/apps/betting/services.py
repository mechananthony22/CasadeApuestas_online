# -*- coding: utf-8 -*-
# Motor de sincronización de datos deportivos para FairBet Lab (The Odds API)
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from betting.models import League, Team, Event, Market, Selection
from betting.the_odds_api import TheOddsAPIClient, string_to_integer_id

logger = logging.getLogger(__name__)

class SyncEngine:
    """
    Motor local de sincronización que procesa las respuestas de la API externa
    y actualiza la base de datos local aplicando el margen del operador.
    """
    def __init__(self):
        self.client = TheOddsAPIClient()

    def map_status(self, api_status_short):
        """
        Mapea el estado corto de la API a los estados permitidos localmente.
        """
        # Soportar formatos comunes devueltos por la API
        scheduled_statuses = ['NS', 'TBD', 'PST']
        in_play_statuses = ['1H', '2H', 'HT', 'ET', 'P', 'BT', 'LIVE']
        finished_statuses = ['FT', 'AET', 'PEN']
        suspended_statuses = ['SUSP', 'INT']
        
        if api_status_short in scheduled_statuses:
            return 'scheduled'
        elif api_status_short in in_play_statuses:
            return 'in_play'
        elif api_status_short in finished_statuses:
            return 'finished'
        elif api_status_short in suspended_statuses:
            return 'suspended'
        else:
            return 'cancelled'

    def sync_fixtures(self, league_id, season=2026):
        """
        Sincroniza ligas, equipos y partidos programados para una liga específica en BD local.
        """
        return self._sync_fixtures_the_odds_api(league_id, season)

    def _sync_fixtures_the_odds_api(self, league_id, season=2026):
        fixtures_data = self.client.get_fixtures(league_id, season)
        if not fixtures_data:
            logger.warning(f"No se obtuvieron fixtures de The Odds API para la liga {league_id}")
            return 0

        synced_count = 0
        for item in fixtures_data:
            try:
                event_hash = item.get('id')
                if not event_hash:
                    continue
                
                event_api_id = string_to_integer_id(event_hash)
                sport_title = item.get('sport_title', 'Liga Local')
                
                # 1. Crear o actualizar liga
                sport_key = item.get('sport_key', '')
                sport_name = 'Fútbol'
                if 'basketball' in sport_key:
                    sport_name = 'Baloncesto'
                elif 'americanfootball' in sport_key:
                    sport_name = 'Fútbol Americano'
                elif 'baseball' in sport_key:
                    sport_name = 'Béisbol'
                elif 'tennis' in sport_key:
                    sport_name = 'Tenis'
                elif 'icehockey' in sport_key:
                    sport_name = 'Hockey'

                league_obj, _ = League.objects.update_or_create(
                    api_id=league_id,
                    defaults={
                        'name': sport_title,
                        'sport': sport_name,
                        'country': 'Internacional',
                        'logo_url': None
                    }
                )
                
                home_team_name = item.get('home_team')
                away_team_name = item.get('away_team')
                if not home_team_name or not away_team_name:
                    continue
                
                home_team_id = string_to_integer_id(home_team_name)
                away_team_id = string_to_integer_id(away_team_name)
                
                # 2. Crear o actualizar equipos
                home_team_obj, _ = Team.objects.update_or_create(
                    api_id=home_team_id,
                    defaults={
                        'name': home_team_name,
                        'logo_url': None
                    }
                )
                away_team_obj, _ = Team.objects.update_or_create(
                    api_id=away_team_id,
                    defaults={
                        'name': away_team_name,
                        'logo_url': None
                    }
                )
                
                # 3. Crear o actualizar evento deportivo
                commence_time = item.get('commence_time')
                event_obj, _ = Event.objects.update_or_create(
                    api_id=event_api_id,
                    defaults={
                        'league': league_obj,
                        'home_team': home_team_obj,
                        'away_team': away_team_obj,
                        'starts_at': commence_time,
                        'status': 'scheduled',
                        'home_score': None,
                        'away_score': None
                    }
                )
                
                # 4. Sincronizar cuotas para este partido
                self._sync_odds_the_odds_api(event_obj, item.get('bookmakers', []))
                
                synced_count += 1
            except Exception as e:
                logger.error(f"Error al procesar fixture individual de The Odds API: {e}")
                continue
                
        logger.info(f"Sincronizados con éxito {synced_count} partidos desde The Odds API para liga {league_id}")
        return synced_count

    def _sync_odds_the_odds_api(self, event_obj, bookmakers):
        margin_multiplier = Decimal('1.0000') - getattr(settings, 'OPERATOR_MARGIN', Decimal('0.05'))
        if not bookmakers:
            self.generate_mock_odds(event_obj, margin_multiplier)
            return
            
        sport_name = getattr(event_obj.league, 'sport', 'Fútbol')
        
        bookmaker = next((b for b in bookmakers if b.get('key') == 'bet365'), bookmakers[0])
        markets = bookmaker.get('markets', [])
        
        markets_created = set()
        
        for market in markets:
            market_key = market.get('key')
            outcomes = market.get('outcomes', [])
            
            if market_key == "h2h":
                if sport_name == 'Fútbol':
                    local_market_name = "1X2"
                else:
                    local_market_name = "Ganador (Moneyline)"
            elif market_key == "totals":
                if outcomes:
                    point = outcomes[0].get('point', 2.5)
                    local_market_name = f"Over/Under {point}"
                else:
                    local_market_name = "Over/Under 2.5"
            elif market_key == "btts" and sport_name == 'Fútbol':
                local_market_name = "BTTS"
            else:
                continue
                
            market_obj, _ = Market.objects.get_or_create(
                event=event_obj,
                name=local_market_name
            )
            markets_created.add(market_key)
            
            for out in outcomes:
                selection_name = out.get('name')
                price = out.get('price')
                if price is None:
                    continue
                    
                raw_odd = Decimal(str(price))
                odds_with_margin = raw_odd * margin_multiplier
                local_selection_name = None
                
                if "over/under" in local_market_name.lower():
                    if "over" in selection_name.lower():
                        local_selection_name = "Over"
                    elif "under" in selection_name.lower():
                        local_selection_name = "Under"
                elif local_market_name in ["1X2", "Ganador (Moneyline)"]:
                    if selection_name == event_obj.home_team.name:
                        local_selection_name = "Local"
                    elif selection_name == event_obj.away_team.name:
                        local_selection_name = "Visitante"
                    elif selection_name.lower() in ["draw", "empate", "x"] and local_market_name == "1X2":
                        local_selection_name = "Empate"
                elif local_market_name == "BTTS":
                    if selection_name.lower() in ["yes", "sí", "si"]:
                        local_selection_name = "Sí"
                    elif selection_name.lower() in ["no"]:
                        local_selection_name = "No"
                        
                if not local_selection_name:
                    continue
                    
                selection_obj, created = Selection.objects.update_or_create(
                    market=market_obj,
                    name=local_selection_name,
                    defaults={
                        'odds': odds_with_margin.quantize(Decimal('0.0001')),
                        'is_active': True
                    }
                )
                
                if not created:
                    self.broadcast_odds_update(event_obj.id, selection_obj)

        # Si la API no devolvió el mercado h2h (partido en vivo o no disponible),
        # generamos un mock de Moneyline/1X2 para asegurar que siempre haya cuotas ganadoras
        if 'h2h' not in markets_created:
            if sport_name == 'Fútbol':
                winner_market_name = "1X2"
                mock_selections = [("Local", Decimal("2.10")), ("Empate", Decimal("3.40")), ("Visitante", Decimal("3.60"))]
            else:
                winner_market_name = "Ganador (Moneyline)"
                mock_selections = [("Local", Decimal("1.85")), ("Visitante", Decimal("1.95"))]

            if not Market.objects.filter(event=event_obj, name=winner_market_name).exists():
                market_winner, _ = Market.objects.get_or_create(event=event_obj, name=winner_market_name)
                for sel_name, raw_odd in mock_selections:
                    Selection.objects.update_or_create(
                        market=market_winner,
                        name=sel_name,
                        defaults={
                            'odds': (raw_odd * margin_multiplier).quantize(Decimal('0.0001')),
                            'is_active': True
                        }
                    )
                logger.info(f"Mercado fallback '{winner_market_name}' generado para evento {event_obj.id} ({sport_name})")

    def sync_live_scores(self):
        """
        Sincroniza marcadores y estados de partidos en tiempo real.
        """
        return self._sync_live_scores_the_odds_api()

    def _sync_live_scores_the_odds_api(self):
        live_fixtures = self.client.get_live_fixtures()
        if not live_fixtures:
            logger.info("No hay partidos en vivo reportados por The Odds API")
            return 0
            
        synced_count = 0
        for item in live_fixtures:
            try:
                event_hash = item.get('id')
                if not event_hash:
                    continue
                    
                event_api_id = string_to_integer_id(event_hash)
                try:
                    event_obj = Event.objects.get(api_id=event_api_id)
                except Event.DoesNotExist:
                    continue
                    
                old_status = event_obj.status
                old_home_score = event_obj.home_score
                old_away_score = event_obj.away_score
                
                completed = item.get('completed', False)
                scores = item.get('scores') or []
                
                new_home_score = None
                new_away_score = None
                
                for s in scores:
                    name = s.get('name')
                    score_val = s.get('score')
                    if score_val is not None:
                        if name == event_obj.home_team.name:
                            new_home_score = int(score_val)
                        elif name == event_obj.away_team.name:
                            new_away_score = int(score_val)
                            
                if completed:
                    new_status = 'finished'
                else:
                    new_status = 'in_play' if scores else 'scheduled'
                    
                is_goal = False
                if old_home_score is not None and new_home_score is not None and old_home_score != new_home_score:
                    is_goal = True
                if old_away_score is not None and new_away_score is not None and old_away_score != new_away_score:
                    is_goal = True
                    
                event_obj.status = new_status
                event_obj.home_score = new_home_score
                event_obj.away_score = new_away_score
                event_obj.save()
                
                synced_count += 1
                
                if is_goal:
                    self.suspend_markets_for_event(event_obj)
                    
                if (old_status != event_obj.status or 
                    old_home_score != event_obj.home_score or 
                    old_away_score != event_obj.away_score):
                    self.broadcast_event_update(event_obj)
            except Exception as e:
                logger.error(f"Error al sincronizar marcador de The Odds API: {e}")
                continue
                
        return synced_count

    def suspend_markets_for_event(self, event_obj):
        """
        Suspende de forma atómica todos los mercados de un evento deportivo tras un gol u otro
        evento crítico, transmite el evento WebSocket y programa la reactivación.
        """
        # 1. Inhabilitar todos los mercados activos
        updated_count = event_obj.markets.filter(is_active=True).update(is_active=False)
        logger.info(f"Mercados suspendidos automáticamente para evento ID {event_obj.id}. Cantidad: {updated_count}")

        # 2. Transmitir suspensión vía WebSockets
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"event_{event_obj.id}",
                    {
                        'type': 'market_suspended',
                        'event_id': event_obj.id,
                        'duration': getattr(settings, 'LIVE_SUSPENSION_COOLDOWN', 15),
                        'reason': 'goal',
                        'message': 'Mercados suspendidos temporalmente debido a un evento crítico en vivo (GOL).'
                    }
                )
        except Exception as ws_err:
            logger.error(f"Error al transmitir WebSocket de suspensión para evento ID {event_obj.id}: {ws_err}")

        # 3. Programar la reactivación asíncrona mediante Celery con countdown
        from betting.tasks import resume_markets_after_suspension
        cooldown = getattr(settings, 'LIVE_SUSPENSION_COOLDOWN', 15)
        resume_markets_after_suspension.apply_async(args=[event_obj.id], countdown=cooldown)
        logger.info(f"Programada reactivación automática de mercados para evento ID {event_obj.id} en {cooldown} segundos.")

    def sync_odds_for_event(self, event_obj):
        """
        Sincroniza mercados y cuotas para un evento deportivo aplicando el margen del operador.
        """
        if not event_obj.markets.exists():
            margin_multiplier = Decimal('1.0000') - getattr(settings, 'OPERATOR_MARGIN', Decimal('0.05'))
            self.generate_mock_odds(event_obj, margin_multiplier)
        return

    def normalize_selection_name(self, market_name, value):
        """
        Normaliza los nombres de selecciones de cuotas de la API a formatos consistentes en español.
        """
        v_lower = str(value).lower()
        if market_name == "1X2":
            if v_lower in ["home", "1"]:
                return "Local"
            elif v_lower in ["draw", "x"]:
                return "Empate"
            elif v_lower in ["away", "2"]:
                return "Visitante"
        elif market_name == "Over/Under 2.5":
            if "over" in v_lower:
                return "Over"
            elif "under" in v_lower:
                return "Under"
        elif market_name == "BTTS":
            if v_lower in ["yes", "sí", "si"]:
                return "Sí"
            elif v_lower in ["no"]:
                return "No"
        return None

    def generate_mock_odds(self, event_obj, margin_multiplier):
        """
        Genera cuotas ficticias (mock) predeterminadas para desarrollo y testing.
        """
        logger.info(f"Generando cuotas mock para el evento {event_obj.api_id}")
        
        sport_name = getattr(event_obj.league, 'sport', 'Fútbol')
        
        if sport_name == 'Fútbol':
            # 1. Mercado 1X2
            market_1x2, _ = Market.objects.get_or_create(event=event_obj, name="1X2")
            selections_1x2 = [("Local", Decimal("2.10")), ("Empate", Decimal("3.40")), ("Visitante", Decimal("3.60"))]
            for name, raw_odd in selections_1x2:
                Selection.objects.update_or_create(
                    market=market_1x2,
                    name=name,
                    defaults={'odds': (raw_odd * margin_multiplier).quantize(Decimal('0.0001')), 'is_active': True}
                )

            # 2. Mercado Over/Under 2.5
            market_ou, _ = Market.objects.get_or_create(event=event_obj, name="Over/Under 2.5")
            selections_ou = [("Over", Decimal("1.85")), ("Under", Decimal("1.95"))]
            for name, raw_odd in selections_ou:
                Selection.objects.update_or_create(
                    market=market_ou,
                    name=name,
                    defaults={'odds': (raw_odd * margin_multiplier).quantize(Decimal('0.0001')), 'is_active': True}
                )

            # 3. Mercado BTTS
            market_btts, _ = Market.objects.get_or_create(event=event_obj, name="BTTS")
            selections_btts = [("Sí", Decimal("1.75")), ("No", Decimal("2.05"))]
            for name, raw_odd in selections_btts:
                Selection.objects.update_or_create(
                    market=market_btts,
                    name=name,
                    defaults={'odds': (raw_odd * margin_multiplier).quantize(Decimal('0.0001')), 'is_active': True}
                )
        else:
            # 1. Mercado Ganador (Moneyline)
            market_ml, _ = Market.objects.get_or_create(event=event_obj, name="Ganador (Moneyline)")
            selections_ml = [("Local", Decimal("1.85")), ("Visitante", Decimal("1.95"))]
            for name, raw_odd in selections_ml:
                Selection.objects.update_or_create(
                    market=market_ml,
                    name=name,
                    defaults={'odds': (raw_odd * margin_multiplier).quantize(Decimal('0.0001')), 'is_active': True}
                )

            # 2. Mercado Over/Under dinámico por deporte
            totals_line = "8.5"
            if sport_name == 'Baloncesto':
                totals_line = "210.5"
            elif sport_name == 'Fútbol Americano':
                totals_line = "45.5"
                
            market_ou, _ = Market.objects.get_or_create(event=event_obj, name=f"Over/Under {totals_line}")
            selections_ou = [("Over", Decimal("1.90")), ("Under", Decimal("1.90"))]
            for name, raw_odd in selections_ou:
                Selection.objects.update_or_create(
                    market=market_ou,
                    name=name,
                    defaults={'odds': (raw_odd * margin_multiplier).quantize(Decimal('0.0001')), 'is_active': True}
                )

    def broadcast_event_update(self, event_obj):
        """
        Emite una notificación de actualización del partido al grupo del evento en Channels (Fase 6).
        """
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"event_{event_obj.id}",
                    {
                        'type': 'event_update',
                        'event_id': event_obj.id,
                        'status': event_obj.status,
                        'home_score': event_obj.home_score,
                        'away_score': event_obj.away_score
                    }
                )
        except Exception as e:
            logger.debug(f"No se pudo transmitir actualización de evento (Channels no inicializado): {e}")

    def broadcast_odds_update(self, event_id, selection_obj):
        """
        Emite una notificación de re-cotización/cambio de cuota al grupo del evento en Channels (Fase 6).
        """
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"event_{event_id}",
                    {
                        'type': 'odds_changed',
                        'selection_id': selection_obj.id,
                        'selection_name': selection_obj.name,
                        'new_odds': str(selection_obj.odds)
                    }
                )
        except Exception as e:
            logger.debug(f"No se pudo transmitir actualización de cuotas (Channels no inicializado): {e}")
