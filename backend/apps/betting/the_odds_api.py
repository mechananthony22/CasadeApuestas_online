# -*- coding: utf-8 -*-
import os
import logging
import hashlib
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def string_to_integer_id(string_id: str) -> int:
    if not string_id:
        return 0
    h = hashlib.sha256(string_id.encode('utf-8')).hexdigest()
    # Tomar los primeros 8 caracteres hexadecimales y enmascarar para asegurar un entero de 31 bits positivo
    return int(h[:8], 16) & 0x7FFFFFFF


class TheOddsAPIClient:
    def __init__(self):
        self.api_key = getattr(settings, 'THE_ODDS_API_KEY', '')
        self.api_url = getattr(settings, 'THE_ODDS_API_URL', 'https://api.the-odds-api.com/v4')
        self.sports_mapping = getattr(settings, 'THE_ODDS_API_SPORTS', {})

    def get_fixtures(self, league_id, season=2026):
        sport_key = self.sports_mapping.get(league_id)
        if not sport_key:
            logger.warning(f"La liga con ID {league_id} no está mapeada en THE_ODDS_API_SPORTS")
            return []

        url = f"{self.api_url}/sports/{sport_key}/odds"
        params = {
            'apiKey': self.api_key,
            'regions': 'eu', # Usar región europea por defecto (donde está bet365, pinnacle, unibet, etc.)
            'markets': 'h2h,totals', # Traer moneyline (1X2) y Over/Under
            'oddsFormat': 'decimal',
            'dateFormat': 'iso'
        }

        try:
            logger.info(f"Consumiendo odds de The Odds API para sport_key {sport_key}")
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data
        except Exception as e:
            logger.error(f"Error al consumir fixtures de The Odds API: {e}")
            return []

    def get_live_fixtures(self):
        all_live_events = []
        # Recorrer todos los sports que tenemos mapeados
        for league_id, sport_key in self.sports_mapping.items():
            url = f"{self.api_url}/sports/{sport_key}/scores"
            params = {
                'apiKey': self.api_key,
                'daysFrom': 3 # Traer partidos de los últimos 3 días (incluye en juego y recientemente finalizados)
            }
            try:
                logger.info(f"Consumiendo marcadores de The Odds API para sport_key {sport_key}")
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                events = response.json()
                
                # Inyectar el league_id local dentro de cada evento para facilitar el mapeo posterior
                for ev in events:
                    ev['_league_id'] = league_id
                    all_live_events.append(ev)
            except Exception as e:
                logger.error(f"Error al consumir marcadores para {sport_key} desde The Odds API: {e}")
                continue
                
        return all_live_events

    def get_odds(self, fixture_id):
        return []


class OddsCache:
    @staticmethod
    def _key_fixtures(league_id):
        """Key Redis para fixtures de una liga específica."""
        return f"odds:fixtures:{league_id}"

    @staticmethod
    def _key_scores():
        """Key Redis global para scores en vivo."""
        return f"odds:live_scores"

    @staticmethod
    def _key_odds(event_id):
        """Key Redis para cuotas de un evento específico."""
        return f"odds:event:{event_id}"

    @staticmethod
    def _key_error(action, league_id=None):
        """
        Key Redis para errores de API.
        Args:
            action: 'fixtures', 'scores', 'odds'
            league_id: ID de liga (para errores por liga) o None (para error global)
        """
        if league_id is not None:
            return f"odds:error:{action}:{league_id}"
        return f"odds:error:{action}"

    def get_fixtures(self, league_id, api_fetch_fn):
        from django.core.cache import cache
        from django.conf import settings

        error_key = self._key_error('fixtures', league_id)
        cached_error = cache.get(error_key)
        if cached_error is not None:
            logger.info(
                f"[CACHE ERROR] fixtures league {league_id}: {cached_error} "
                f"(válido por {settings.ODDS_CACHE_TTL_API_ERROR}s, no se hace request)"
            )
            return []

        cache_key = self._key_fixtures(league_id)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"[CACHE HIT] fixtures league {league_id}")
            return cached_data

        logger.info(f"[CACHE MISS] fixtures league {league_id} → Llamando a API")
        try:
            data = api_fetch_fn()
            if data:
                cache.set(cache_key, data, timeout=settings.ODDS_CACHE_TTL_FIXTURES)
                logger.info(f"[CACHE SET] fixtures league {league_id} guardado ({len(data)} eventos)")
            return data if data else []
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"[API ERROR] fixtures league {league_id}: {error_msg}")
            cache.set(error_key, error_msg, timeout=settings.ODDS_CACHE_TTL_API_ERROR)
            return []

    def get_live_scores(self, api_fetch_fn):
        from django.core.cache import cache
        from django.conf import settings

        error_key = self._key_error('scores')
        if cache.get(error_key) is not None:
            logger.info(f"[CACHE ERROR] live_scores (válido por {settings.ODDS_CACHE_TTL_API_ERROR}s)")
            return []

        cache_key = self._key_scores()
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"[CACHE HIT] live_scores")
            return cached_data

        logger.info(f"[CACHE MISS] live_scores → Llamando a API")
        try:
            data = api_fetch_fn()
            if data:
                cache.set(cache_key, data, timeout=settings.ODDS_CACHE_TTL_LIVE_SCORES)
                logger.info(f"[CACHE SET] live_scores guardado ({len(data)} eventos)")
            return data if data else []
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"[API ERROR] live_scores: {error_msg}")
            cache.set(error_key, error_msg, timeout=settings.ODDS_CACHE_TTL_API_ERROR)
            return []

    def get_odds(self, event_id, league_id, api_fetch_fn):
        from django.core.cache import cache
        from django.conf import settings

        error_key = self._key_error('odds', league_id)
        if cache.get(error_key) is not None:
            logger.info(f"[CACHE ERROR] odds event {event_id} league {league_id}")
            return {}

        cache_key = self._key_odds(event_id)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            logger.debug(f"[CACHE HIT] odds event {event_id}")
            return cached_data

        logger.info(f"[CACHE MISS] odds event {event_id} → Llamando a API")
        try:
            data = api_fetch_fn()
            if data:
                cache.set(cache_key, data, timeout=settings.ODDS_CACHE_TTL_ODDS)
            return data if data else {}
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"[API ERROR] odds event {event_id}: {error_msg}")
            cache.set(error_key, error_msg, timeout=settings.ODDS_CACHE_TTL_API_ERROR)
            return {}

    def invalidate_fixtures(self, league_id=None):
        from django.core.cache import cache
        from django.conf import settings

        if league_id is not None:
            cache.delete(self._key_fixtures(league_id))
            cache.delete(self._key_error('fixtures', league_id))
            logger.info(f"[CACHE INVALIDATE] fixtures league {league_id}")
        else:
            sports_mapping = getattr(settings, 'THE_ODDS_API_SPORTS', {})
            for lg_id in sports_mapping.keys():
                cache.delete(self._key_fixtures(lg_id))
                cache.delete(self._key_error('fixtures', lg_id))
            logger.info("[CACHE INVALIDATE] fixtures TODAS las ligas")

    def invalidate_live_scores(self):
        """Limpia el caché global de scores en vivo."""
        from django.core.cache import cache

        cache.delete(self._key_scores())
        cache.delete(self._key_error('scores'))
        logger.info("[CACHE INVALIDATE] live_scores")

    def invalidate_all(self):
        from django.core.cache import cache
        from django.conf import settings

        sports_mapping = getattr(settings, 'THE_ODDS_API_SPORTS', {})

        for lg_id in sports_mapping.keys():
            cache.delete(self._key_fixtures(lg_id))
            cache.delete(self._key_error('fixtures', lg_id))

        cache.delete(self._key_scores())
        cache.delete(self._key_error('scores'))

        logger.warning("[CACHE INVALIDATE] TODO el cache de odds (forces refresh)")
