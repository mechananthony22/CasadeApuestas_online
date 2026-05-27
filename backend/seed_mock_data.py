# -*- coding: utf-8 -*-
import os
import django
import sys
from datetime import datetime, timedelta
from django.utils import timezone
from decimal import Decimal

# Configurar entorno de Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Cargar variables de entorno desde .env
from pathlib import Path
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent / '.env'
    if not env_path.exists():
        env_path = Path(__file__).resolve().parent.parent / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from betting.models import League, Team, Event, Market, Selection

def seed():
    print("Iniciando la población de datos mock para desarrollo local...")
    
    # 1. Crear Ligas
    ligas_data = [
        {"api_id": 140, "name": "La Liga", "country": "España", "logo_url": None},
        {"api_id": 39, "name": "Premier League", "country": "Inglaterra", "logo_url": None},
        {"api_id": 2, "name": "Champions League", "country": "Europa", "logo_url": None},
    ]
    
    ligas = {}
    for l in ligas_data:
        liga_obj, created = League.objects.update_or_create(
            api_id=l["api_id"],
            defaults={
                "name": l["name"],
                "country": l["country"],
                "logo_url": l["logo_url"]
            }
        )
        ligas[l["api_id"]] = liga_obj
        print(f"Liga: {liga_obj.name} - {'Creada' if created else 'Actualizada'}")

    # 2. Crear Equipos
    equipos_data = [
        {"api_id": 541, "name": "Real Madrid", "logo_url": None},
        {"api_id": 529, "name": "Barcelona", "logo_url": None},
        {"api_id": 50, "name": "Manchester City", "logo_url": None},
        {"api_id": 42, "name": "Arsenal", "logo_url": None},
        {"api_id": 40, "name": "Liverpool", "logo_url": None},
        {"api_id": 157, "name": "Bayern Munich", "logo_url": None},
        {"api_id": 496, "name": "Juventus", "logo_url": None},
        {"api_id": 85, "name": "PSG", "logo_url": None},
    ]
    
    equipos = {}
    for t in equipos_data:
        team_obj, created = Team.objects.update_or_create(
            api_id=t["api_id"],
            defaults={
                "name": t["name"],
                "logo_url": t["logo_url"]
            }
        )
        equipos[t["api_id"]] = team_obj
        print(f"Equipo: {team_obj.name} - {'Creado' if created else 'Actualizado'}")

    # 3. Crear Eventos Programados y En Vivo
    ahora = timezone.now()
    eventos_data = [
        {
            "api_id": 1001,
            "league": ligas[140],
            "home_team": equipos[541], # Real Madrid
            "away_team": equipos[529], # Barcelona
            "starts_at": ahora + timedelta(days=2),
            "status": "scheduled",
            "home_score": None,
            "away_score": None,
        },
        {
            "api_id": 1002,
            "league": ligas[39],
            "home_team": equipos[42], # Arsenal
            "away_team": equipos[40], # Liverpool
            "starts_at": ahora + timedelta(hours=4),
            "status": "scheduled",
            "home_score": None,
            "away_score": None,
        },
        {
            "api_id": 1003,
            "league": ligas[2],
            "home_team": equipos[50], # Man City
            "away_team": equipos[157], # Bayern Munich
            "starts_at": ahora - timedelta(minutes=45), # Empezó hace 45 minutos (En Vivo)
            "status": "in_play",
            "home_score": 1,
            "away_score": 0,
        },
        {
            "api_id": 1004,
            "league": ligas[140],
            "home_team": equipos[529], # Barcelona
            "away_team": equipos[85], # PSG
            "starts_at": ahora - timedelta(hours=3), # Ya terminó
            "status": "finished",
            "home_score": 2,
            "away_score": 1,
        }
    ]

    for ev in eventos_data:
        event_obj, created = Event.objects.update_or_create(
            api_id=ev["api_id"],
            defaults={
                "league": ev["league"],
                "home_team": ev["home_team"],
                "away_team": ev["away_team"],
                "starts_at": ev["starts_at"],
                "status": ev["status"],
                "home_score": ev["home_score"],
                "away_score": ev["away_score"],
            }
        )
        print(f"Evento: {event_obj.home_team.name} vs {event_obj.away_team.name} ({event_obj.get_status_display()}) - {'Creado' if created else 'Actualizado'}")

        # Generar mercados y selecciones para este evento
        crear_mercados_para_evento(event_obj)

def crear_mercados_para_evento(event_obj):
    # 1. Mercado 1X2
    market_1x2, _ = Market.objects.get_or_create(event=event_obj, name="1X2")
    selections_1x2 = [("Local", Decimal("1.8500")), ("Empate", Decimal("3.4000")), ("Visitante", Decimal("3.8000"))]
    for name, odd in selections_1x2:
        Selection.objects.update_or_create(
            market=market_1x2,
            name=name,
            defaults={'odds': odd, 'is_active': True}
        )

    # 2. Mercado Over/Under 2.5
    market_ou, _ = Market.objects.get_or_create(event=event_obj, name="Over/Under 2.5")
    selections_ou = [("Over", Decimal("1.7500")), ("Under", Decimal("1.9500"))]
    for name, odd in selections_ou:
        Selection.objects.update_or_create(
            market=market_ou,
            name=name,
            defaults={'odds': odd, 'is_active': True}
        )

    # 3. Mercado BTTS
    market_btts, _ = Market.objects.get_or_create(event=event_obj, name="BTTS")
    selections_btts = [("Sí", Decimal("1.8000")), ("No", Decimal("1.9000"))]
    for name, odd in selections_btts:
        Selection.objects.update_or_create(
            market=market_btts,
            name=name,
            defaults={'odds': odd, 'is_active': True}
        )
    print(f"  -> Mercados y selecciones creados para evento ID {event_obj.api_id}")

if __name__ == "__main__":
    seed()
    print("¡Población completada con éxito!")
