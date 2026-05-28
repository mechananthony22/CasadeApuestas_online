# -*- coding: utf-8 -*-
import os
import logging
import hashlib
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def string_to_integer_id(string_id: str) -> int:
    """
    Genera un ID entero de 32 bits firmado estable y determinista a partir de una cadena.
    Asegura compatibilidad con el tipo de campo IntegerField en Django (máx 2147483647).
    """
    if not string_id:
        return 0
    h = hashlib.sha256(string_id.encode('utf-8')).hexdigest()
    # Tomar los primeros 8 caracteres hexadecimales y enmascarar para asegurar un entero de 31 bits positivo
    return int(h[:8], 16) & 0x7FFFFFFF


class TheOddsAPIClient:
    """
    Cliente HTTP para consumir The Odds API V4 (https://the-odds-api.com/).
    Soporta la sincronización de partidos, cuotas y marcadores en tiempo real.
    """
    def __init__(self):
        self.api_key = getattr(settings, 'THE_ODDS_API_KEY', '')
        self.api_url = getattr(settings, 'THE_ODDS_API_URL', 'https://api.the-odds-api.com/v4')
        self.sports_mapping = getattr(settings, 'THE_ODDS_API_SPORTS', {})

    def get_fixtures(self, league_id, season=2026):
        """
        Obtiene los partidos programados y sus cuotas asociadas para una liga específica.
        Dado que The Odds API retorna eventos y cuotas en la misma consulta, este endpoint
        cumple un rol híbrido en nuestro motor de sincronización.
        """
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
        """
        Obtiene marcadores en tiempo real recorriendo todos los sports configurados.
        Combina los resultados de cada liga para emular el feed general en vivo.
        """
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
        """
        Retorna cuotas bajo demanda para un fixture individual.
        En The Odds API las cuotas se actualizan de forma masiva por liga en get_fixtures,
        por lo que este método retorna vacío para evitar peticiones redundantes.
        """
        return []


class OddsCache:
    """
    Capa de caché Redis para proteger The Odds API de saturación y desperdicio de credits.

    PROBLEMA QUE RESUELVE:
    Cada Celery task que consulta The Odds API consume credits del tier gratuito (500/mes).
    Si una API key está mala (401) o saturada (429), cada retry desperdicia credits.
    Además, sync_live_scores	itera sobre 10 ligas cada 30 segundos, consumiendo
    10 credits por ciclo × 120 ciclos/hora = 1,200 credits/hora solo en scores.

    SOLUCIÓN:
    Esta clase implementa una capa de caché Redis que:
    1. Guarda los datos de la API en Redis con TTL largo (ej: 2h para fixtures)
    2. Si la API falla (401, 429, timeout), guarda el error con TTL corto (5 min)
    3. Cuando SyncEngine necesita datos, primero consulta la caché:
       - Si hay datos válidos → retorna inmediatamente (0 credits gastados)
       - Si hay error cacheado → retorna [] sin hacer request (protege credits)
       - Si no hay nada → hace el request a la API y guarda en caché

    ESTRUCTURA DE CACHÉ EN REDIS:
        odds:fixtures:{league_id}   → Lista de eventos de una liga (TTL: 2h)
        odds:live_scores           → Marcadores en vivo de todas las ligas (TTL: 30s)
        odds:event:{event_id}       → Cuotas de un evento específico (TTL: 10s)
        odds:error:fixtures:{league_id} → Error 401/429 de fixtures por liga (TTL: 5min)
        odds:error:live_scores      → Error de scores global (TTL: 5min)

    USO:
        from betting.the_odds_api import OddsCache

        cache = OddsCache()

        # Para fixtures de una liga
        def api_call():
            return client.get_fixtures(league_id)

        data = cache.get_fixtures(league_id, api_call)

        # Para scores en vivo
        def api_call_scores():
            return client.get_live_fixtures()

        scores = cache.get_live_scores(api_call_scores)
    """

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
        """
        Retorna fixtures de una liga desde caché. Si no existen o expiraron, llama a api_fetch_fn.

        FLUJO:
        1. Check error cacheado (si hay error 401/429 reciente para esta liga → return [])
        2. Check data cache (si hay datos válidos → return cached_data)
        3. [CACHE MISS] Llamar api_fetch_fn() que hace el request HTTP real
        4. Si falla → guardar error en caché por 5 min, return []
        5. Si success → guardar datos en caché por ODDS_CACHE_TTL_FIXTURES (2h), return datos

        Args:
            league_id: ID de la liga local (ej: 39 = EPL)
            api_fetch_fn: Función lambda/sin argumentos que hace el request HTTP real.
                          Debe retornar [] si falló (para no romper el flujo del caller).

        Returns:
            list: Datos de fixtures o [] si hay error cacheado o falla.
        """
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
        """
        Retorna scores en vivo desde caché. Si expiraron, llama a api_fetch_fn.

        FLUJO similar a get_fixtures pero para scores de TODAS las ligas combinados.
        El error se guarda GLOBAL (no por liga) ya que si la API falla, normalmente
        falla para todas las ligas juntas.

        Returns:
            list: Lista de eventos con scores o [] si hay error.
        """
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
        """
        Retorna cuotas de un evento específico desde caché.

        Args:
            event_id: ID del evento en la BD local
            league_id: ID de la liga (para segregar errores por liga)
            api_fetch_fn: Función lambda sin argumentos que retorna las cuotas.

        Returns:
            dict: Datos de cuotas del evento o {} si hay error/no hay datos.
        """
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
        """
        Limpia el caché de fixtures.

        Args:
            league_id: Si es None, limpia TODOS los fixtures y errores.
                       Si se especifica, limpia solo esa liga.
        """
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
        """
        Limpia TODA la caché de odds (fixtures + scores + errores).
        Útil cuando se quiere forzar un refresh completo de todos los datos
        o cuando la API key ha sido renovada.
        """
        from django.core.cache import cache
        from django.conf import settings

        sports_mapping = getattr(settings, 'THE_ODDS_API_SPORTS', {})

        for lg_id in sports_mapping.keys():
            cache.delete(self._key_fixtures(lg_id))
            cache.delete(self._key_error('fixtures', lg_id))

        cache.delete(self._key_scores())
        cache.delete(self._key_error('scores'))

        logger.warning("[CACHE INVALIDATE] TODO el cache de odds (forces refresh)")
