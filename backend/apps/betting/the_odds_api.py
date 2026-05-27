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
        Mantiene la interfaz compatible con APIFootballClient.
        Debido a que get_fixtures en The Odds API ya retorna las cuotas embebidas en el evento,
        este método puede actuar directamente sobre cuotas pre-cargadas o retornar vacío
        si se requiere actualización bajo demanda.
        """
        # Nota: En The Odds API no se requiere consulta por ID individual para cuotas estándar
        # ya que se actualizan de forma masiva por liga.
        return []
