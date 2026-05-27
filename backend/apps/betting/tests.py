# -*- coding: utf-8 -*-
# Pruebas unitarias y de integración para la aplicación betting (Fase 3)
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from betting.models import League, Team, Event, Market, Selection, Bet, BetSelection
from betting.services import SyncEngine

class BettingModelsTestCase(TestCase):
    """
    Pruebas unitarias para validar el comportamiento de los modelos de base de datos.
    """
    def setUp(self):
        # Crear liga y equipos de prueba
        self.league = League.objects.create(
            api_id=1,
            name="Mundial 2026",
            country="Internacional",
            logo_url="https://ejemplo.com/copamundo.png"
        )
        self.home_team = Team.objects.create(
            api_id=10,
            name="Perú",
            logo_url="https://ejemplo.com/peru.png"
        )
        self.away_team = Team.objects.create(
            api_id=20,
            name="Argentina",
            logo_url="https://ejemplo.com/argentina.png"
        )

    def test_creacion_evento_deportivo(self):
        """
        Verifica que un partido se cree correctamente con sus relaciones y estados predeterminados.
        """
        starts_at = timezone.now() + timezone.timedelta(days=1)
        event = Event.objects.create(
            api_id=868686,
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            starts_at=starts_at,
            status='scheduled'
        )

        self.assertEqual(event.api_id, 868686)
        self.assertEqual(event.league, self.league)
        self.assertEqual(event.home_team, self.home_team)
        self.assertEqual(event.away_team, self.away_team)
        self.assertEqual(event.status, 'scheduled')
        self.assertIsNone(event.home_score)
        self.assertIsNone(event.away_score)
        self.assertIn("Perú vs Argentina", str(event))

    def test_creacion_mercado_y_seleccion_con_margen(self):
        """
        Verifica que se puedan asociar mercados y selecciones con precisión Decimal.
        """
        starts_at = timezone.now() + timezone.timedelta(days=1)
        event = Event.objects.create(
            api_id=868686,
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            starts_at=starts_at,
            status='scheduled'
        )

        # Crear mercado
        market = Market.objects.create(
            event=event,
            name="1X2"
        )

        # Crear selecciones con precisión exacta de 4 decimales
        selection_home = Selection.objects.create(
            market=market,
            name="Local",
            odds=Decimal("1.9950")  # Ejemplo: 2.10 original con 5% de margen (2.10 * 0.95)
        )

        self.assertEqual(market.event, event)
        self.assertEqual(market.name, "1X2")
        self.assertTrue(market.is_active)
        
        self.assertEqual(selection_home.market, market)
        self.assertEqual(selection_home.name, "Local")
        self.assertEqual(selection_home.odds, Decimal("1.9950"))
        self.assertTrue(selection_home.is_active)
        self.assertIn("Local @ 1.9950", str(selection_home))


class SyncEngineTestCase(TestCase):
    """
    Pruebas de integración para validar el funcionamiento del motor de sincronización SyncEngine.
    """
    def setUp(self):
        self.engine = SyncEngine()

    @patch('betting.services.APIFootballClient.get_fixtures')
    def test_sincronizacion_fixtures_exitosa(self, mock_get_fixtures):
        """
        Verifica que el SyncEngine lea el JSON de la API y pueble las tablas locales.
        """
        # Configurar mock response de API-Football
        mock_get_fixtures.return_value = [
            {
                "fixture": {
                    "id": 868686,
                    "date": "2026-06-12T15:00:00-05:00",
                    "status": { "long": "Not Started", "short": "NS" }
                },
                "league": { "id": 1, "name": "World Cup", "logo": "https://copamundo.png", "country": "World" },
                "teams": {
                    "home": { "id": 10, "name": "Peru", "logo": "https://peru.png" },
                    "away": { "id": 20, "name": "Argentina", "logo": "https://argentina.png" }
                },
                "goals": { "home": None, "away": None }
            }
        ]

        # Correr sincronización
        count = self.engine.sync_fixtures(league_id=1, season=2026)

        self.assertEqual(count, 1)
        self.assertTrue(League.objects.filter(api_id=1).exists())
        self.assertTrue(Team.objects.filter(api_id=10).exists())
        self.assertTrue(Team.objects.filter(api_id=20).exists())
        self.assertTrue(Event.objects.filter(api_id=868686).exists())

        event = Event.objects.get(api_id=868686)
        self.assertEqual(event.status, 'scheduled')
        self.assertEqual(event.league.name, "World Cup")
        self.assertEqual(event.home_team.name, "Peru")

    @patch('betting.services.APIFootballClient.get_live_fixtures')
    def test_sincronizacion_marcadores_en_vivo(self, mock_get_live_fixtures):
        """
        Verifica que se actualicen marcadores y se envíen notificaciones en tiempo real.
        """
        # Preparar evento previo en BD local
        league = League.objects.create(api_id=39, name="Premier League", country="England")
        home = Team.objects.create(api_id=10, name="Peru")
        away = Team.objects.create(api_id=20, name="Argentina")
        event = Event.objects.create(
            api_id=868686,
            league=league,
            home_team=home,
            away_team=away,
            starts_at=timezone.now(),
            status='scheduled',
            home_score=0,
            away_score=0
        )

        # Mock de partido en vivo con gol de Perú y estado In Play
        mock_get_live_fixtures.return_value = [
            {
                "fixture": {
                    "id": 868686,
                    "status": { "long": "First Half", "short": "1H" }
                },
                "league": { "id": 39 },
                "goals": { "home": 1, "away": 0 }
            }
        ]

        # Correr sincronización de marcadores
        count = self.engine.sync_live_scores()

        self.assertEqual(count, 1)
        event.refresh_from_db()
        self.assertEqual(event.status, 'in_play')
        self.assertEqual(event.home_score, 1)
        self.assertEqual(event.away_score, 0)

    @patch('betting.services.APIFootballClient.get_odds')
    def test_sincronizacion_odds_con_margen(self, mock_get_odds):
        """
        Verifica que la sincronización de cuotas aplique correctamente el 5% de margen local.
        """
        # Registrar evento previo local
        league = League.objects.create(api_id=1, name="World Cup", country="World")
        home = Team.objects.create(api_id=10, name="Peru")
        away = Team.objects.create(api_id=20, name="Argentina")
        event = Event.objects.create(
            api_id=868686,
            league=league,
            home_team=home,
            away_team=away,
            starts_at=timezone.now(),
            status='scheduled'
        )

        # Mock de cuotas devueltas por API-Football (Bet365 ID 8)
        mock_get_odds.return_value = [
            {
                "bookmakers": [
                    {
                        "id": 8, "name": "Bet365",
                        "bets": [
                            {
                                "id": 1, "name": "Match Winner",
                                "values": [
                                    { "value": "Home", "odd": "2.00" },
                                    { "value": "Draw", "odd": "3.50" },
                                    { "value": "Away", "odd": "3.00" }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        # Ejecutar sincronización de cuotas para el evento
        self.engine.sync_odds_for_event(event)

        # Verificar creación de mercado local
        self.assertTrue(Market.objects.filter(event=event, name="1X2").exists())
        market = Market.objects.get(event=event, name="1X2")

        # Verificar que se aplicó el margen del 5% (multiplicador 0.95)
        # 2.00 * 0.95 = 1.9000
        # 3.50 * 0.95 = 3.3250
        # 3.00 * 0.95 = 2.8500
        selection_home = Selection.objects.get(market=market, name="Local")
        selection_draw = Selection.objects.get(market=market, name="Empate")
        selection_away = Selection.objects.get(market=market, name="Visitante")

        self.assertEqual(selection_home.odds, Decimal("1.9000"))
        self.assertEqual(selection_draw.odds, Decimal("3.3250"))
        self.assertEqual(selection_away.odds, Decimal("2.8500"))


class BettingAPITestCase(APITestCase):
    """
    Pruebas de endpoints REST para consultar eventos y mercados.
    """
    def setUp(self):
        # Crear usuario de prueba
        self.user = User.objects.create_user(username="testuser", password="testpassword")
        
        # Crear datos básicos de catálogo
        self.league = League.objects.create(api_id=1, name="World Cup", country="World")
        self.home = Team.objects.create(api_id=10, name="Peru")
        self.away = Team.objects.create(api_id=20, name="Argentina")
        
        # Evento Programado
        self.event_scheduled = Event.objects.create(
            api_id=868686,
            league=self.league,
            home_team=self.home,
            away_team=self.away,
            starts_at=timezone.now() + timezone.timedelta(days=1),
            status='scheduled'
        )
        
        # Evento en Vivo
        self.event_live = Event.objects.create(
            api_id=999999,
            league=self.league,
            home_team=self.home,
            away_team=self.away,
            starts_at=timezone.now(),
            status='in_play',
            home_score=0,
            away_score=0
        )

        # Asociar mercados y cuotas de prueba
        market = Market.objects.create(event=self.event_scheduled, name="1X2")
        Selection.objects.create(market=market, name="Local", odds=Decimal("1.9000"))
        Selection.objects.create(market=market, name="Empate", odds=Decimal("3.3250"))
        Selection.objects.create(market=market, name="Visitante", odds=Decimal("2.8500"))

    def test_obtener_eventos_sin_autenticacion(self):
        """
        Verifica que el catálogo requiera autenticación de forma predeterminada (código 403).
        """
        response = self.client.get('/api/v1/betting/events/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_obtener_lista_eventos_autenticado(self):
        """
        Verifica que un usuario autenticado pueda listar todos los partidos correctamente.
        """
        self.client.login(username="testuser", password="testpassword")
        response = self.client.get('/api/v1/betting/events/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Deben retornar los 2 eventos creados
        self.assertEqual(len(response.data), 2)
        
        # Validar estructura anidada del primer evento
        first_event = response.data[0]
        self.assertIn('home_team', first_event)
        self.assertIn('away_team', first_event)
        self.assertIn('markets', first_event)

    def test_obtener_detalle_evento_con_mercados(self):
        """
        Verifica la serialización correcta de los mercados y cuotas anidadas al ver un evento específico.
        """
        self.client.login(username="testuser", password="testpassword")
        response = self.client.get(f'/api/v1/betting/events/{self.event_scheduled.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['api_id'], 868686)
        
        # Validar mercados anidados
        markets = response.data['markets']
        self.assertEqual(len(markets), 1)
        self.assertEqual(markets[0]['name'], "1X2")
        
        # Validar selecciones anidadas
        selections = markets[0]['selections']
        self.assertEqual(len(selections), 3)
        self.assertEqual(selections[0]['name'], "Local")
        self.assertEqual(selections[0]['odds'], "1.9000") # En JSON se serializa como string decimal

    def test_filtrar_eventos_por_estado_vivo(self):
        """
        Verifica el funcionamiento de los filtros de consulta ?status=live para eventos en tiempo real.
        """
        self.client.login(username="testuser", password="testpassword")
        response = self.client.get('/api/v1/betting/events/?status=live')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Solo debe devolver el evento en vivo
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['api_id'], 999999)


from betting.tasks import sync_fixtures, sync_live_scores, update_odds
from betting.services import APIFootballClient

class CeleryTasksTestCase(TestCase):
    """
    Pruebas unitarias para validar la ejecución correcta de las tareas de Celery.
    """
    @patch('betting.tasks.SyncEngine.sync_fixtures')
    def test_sync_fixtures_task(self, mock_sync):
        mock_sync.return_value = 5
        res = sync_fixtures()
        self.assertIn("10 partidos", res)
        self.assertEqual(mock_sync.call_count, 2)

    @patch('betting.tasks.SyncEngine.sync_live_scores')
    def test_sync_live_scores_task(self, mock_sync):
        mock_sync.return_value = 3
        res = sync_live_scores()
        self.assertIn("3", res)
        mock_sync.assert_called_once()

    @patch('betting.tasks.SyncEngine.sync_odds_for_event')
    def test_update_odds_task(self, mock_sync):
        # Crear evento activo local
        league = League.objects.create(api_id=39, name="Premier League", country="England")
        home = Team.objects.create(api_id=10, name="Peru")
        away = Team.objects.create(api_id=20, name="Argentina")
        Event.objects.create(
            api_id=868686,
            league=league,
            home_team=home,
            away_team=away,
            starts_at=timezone.now(),
            status='in_play'
        )

        res = update_odds()
        self.assertIn("1 partidos activos", res)
        mock_sync.assert_called_once()

    @patch('betting.tasks.SyncEngine.sync_fixtures')
    def test_sync_fixtures_exception(self, mock_sync):
        mock_sync.side_effect = Exception("Celery Error")
        res = sync_fixtures()
        self.assertIn("Error", res)

    @patch('betting.tasks.SyncEngine.sync_live_scores')
    def test_sync_live_scores_exception(self, mock_sync):
        mock_sync.side_effect = Exception("Celery Error")
        res = sync_live_scores()
        self.assertIn("Error", res)

    @patch('betting.tasks.SyncEngine.sync_odds_for_event')
    def test_update_odds_exception(self, mock_sync):
        # Crear evento activo local
        league = League.objects.create(api_id=39, name="Premier League", country="England")
        home = Team.objects.create(api_id=10, name="Peru")
        away = Team.objects.create(api_id=20, name="Argentina")
        Event.objects.create(
            api_id=868686,
            league=league,
            home_team=home,
            away_team=away,
            starts_at=timezone.now(),
            status='in_play'
        )
        mock_sync.side_effect = Exception("Celery Error")
        res = update_odds()
        self.assertIn("Error", res)


class APIClientExceptionTestCase(TestCase):
    """
    Pruebas para validar el control de excepciones del cliente HTTP de API-Football.
    """
    @patch('requests.get')
    def test_client_network_errors(self, mock_get):
        mock_get.side_effect = Exception("Error de Red Simulado")
        client = APIFootballClient()
        
        self.assertEqual(client.get_fixtures(39, 2026), [])
        self.assertEqual(client.get_live_fixtures(), [])
        self.assertEqual(client.get_odds(868686), [])


from rest_framework.test import APITransactionTestCase
from users.models import UserProfile
from wallet.models import LedgerEntry
from uuid import uuid4
import threading
import concurrent.futures

class BetPlacementAPITestCase(APITestCase):
    """
    Pruebas de la API para la colocación de apuestas síncronas, validación de KYC,
    estrategia de idempotencia y control de re-cotización de cuotas.
    """
    def setUp(self):
        # Crear usuario y perfil KYC verificado
        self.user = User.objects.create_user(username="apostador1", password="password123")
        self.profile = UserProfile.objects.create(
            user=self.user,
            dni="77777777",
            birth_date=timezone.now().date() - timezone.timedelta(days=365*25),  # 25 años
            verification_status=UserProfile.STATUS_VERIFIED
        )

        # Cargar saldo de 500 fichas virtuales en el Ledger contable (partida doble)
        tx_id = uuid4()
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("500.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx_id,
            description="Recarga de bienvenida"
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=Decimal("500.0000"),
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx_id,
            description="Débito casa por bienvenida"
        )

        # Crear datos de catálogo
        self.league = League.objects.create(api_id=39, name="Premier League", country="England")
        self.home = Team.objects.create(api_id=10, name="Manchester United")
        self.away = Team.objects.create(api_id=20, name="Liverpool")
        
        self.event = Event.objects.create(
            api_id=123456,
            league=self.league,
            home_team=self.home,
            away_team=self.away,
            starts_at=timezone.now() + timezone.timedelta(days=1),
            status='scheduled'
        )

        self.market = Market.objects.create(event=self.event, name="1X2")
        self.selection_home = Selection.objects.create(market=self.market, name="Local", odds=Decimal("2.1000"))
        self.selection_away = Selection.objects.create(market=self.market, name="Visitante", odds=Decimal("3.2000"))

    def test_colocacion_apuesta_simple_exitosa(self):
        """
        Verifica que se coloque una apuesta simple con éxito, debitando saldo en partida doble.
        """
        self.client.login(username="apostador1", password="password123")
        idempotency_key = str(uuid4())
        
        payload = {
            "selections": [
                {
                    "selection_id": self.selection_home.id,
                    "expected_odds": "2.1000"
                }
            ],
            "stake": "100.0000"
        }

        response = self.client.post(
            '/api/v1/betting/bets/',
            data=payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'accepted')
        self.assertEqual(response.data['type'], 'simple')
        self.assertEqual(response.data['potential_payout'], '210.0000')

        # Verificar saldo del usuario (debe haber bajado de 500 a 400)
        self.assertEqual(LedgerEntry.get_user_balance(self.user), Decimal("400.0000"))
        # Verificar retención en apuestas pendientes (debe haber subido a 100)
        self.assertEqual(LedgerEntry.get_pending_bets_balance(), Decimal("100.0000"))

    def test_rechazo_apuesta_sin_cabecera_idempotencia(self):
        """
        Verifica que se rechace la petición si falta la cabecera de idempotencia.
        """
        self.client.login(username="apostador1", password="password123")
        payload = {
            "selections": [{"selection_id": self.selection_home.id, "expected_odds": "2.1000"}],
            "stake": "50.0000"
        }

        response = self.client.post('/api/v1/betting/bets/', data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Idempotency-Key", response.data['error'])

    def test_estrategia_idempotencia_respuesta_cacheada(self):
        """
        Garantiza que reintentar con la misma idempotencia devuelva el resultado idéntico cacheado.
        """
        self.client.login(username="apostador1", password="password123")
        idempotency_key = str(uuid4())
        
        payload = {
            "selections": [{"selection_id": self.selection_home.id, "expected_odds": "2.1000"}],
            "stake": "100.0000"
        }

        # Primer Intento
        resp1 = self.client.post(
            '/api/v1/betting/bets/',
            data=payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        bet_id = resp1.data['id']

        # Segundo Intento con la misma clave
        resp2 = self.client.post(
            '/api/v1/betting/bets/',
            data=payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key
        )
        
        # Deben ser idénticos
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp2.data['id'], bet_id)

        # Verificar que NO se crearon dos registros Bet ni dos débitos contables
        self.assertEqual(Bet.objects.filter(user=self.user).count(), 1)
        self.assertEqual(LedgerEntry.get_user_balance(self.user), Decimal("400.0000"))

    def test_politica_re_cotizacion_odds_cambiaron(self):
        """
        Verifica que si la cuota cambió en el servidor se retorne 409 Conflict con las cuotas reales.
        """
        self.client.login(username="apostador1", password="password123")
        idempotency_key = str(uuid4())
        
        # El usuario espera 2.5000, pero en la BD local es 2.1000
        payload = {
            "selections": [{"selection_id": self.selection_home.id, "expected_odds": "2.5000"}],
            "stake": "100.0000"
        }

        response = self.client.post(
            '/api/v1/betting/bets/',
            data=payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'odds_changed')
        
        cambio = response.data['cambios'][0]
        self.assertEqual(cambio['selection_id'], self.selection_home.id)
        self.assertEqual(cambio['expected_odds'], '2.5000')
        self.assertEqual(cambio['actual_odds'], '2.1000')

    def test_bloqueo_juego_responsable_kyc_no_verificado(self):
        """
        Verifica que se impida apostar a usuarios pendientes de verificación.
        """
        self.profile.verification_status = UserProfile.STATUS_PENDING
        self.profile.save()

        self.client.login(username="apostador1", password="password123")
        idempotency_key = str(uuid4())
        
        payload = {
            "selections": [{"selection_id": self.selection_home.id, "expected_odds": "2.1000"}],
            "stake": "50.0000"
        }

        response = self.client.post(
            '/api/v1/betting/bets/',
            data=payload,
            format='json',
            HTTP_IDEMPOTENCY_KEY=idempotency_key
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Pendiente de Verificación", response.data['non_field_errors'][0])


class ConcurrencyBettingTestCase(APITransactionTestCase):
    """
    Prueba de integración de concurrencia real mediante hilos para verificar
    que no exista condición de carrera ni doble gasto de saldo.
    """
    def setUp(self):
        # Crear usuario y perfil verificado
        self.user = User.objects.create_user(username="concurrente", password="password123")
        UserProfile.objects.create(
            user=self.user,
            dni="88888888",
            birth_date=timezone.now().date() - timezone.timedelta(days=365*30),
            verification_status=UserProfile.STATUS_VERIFIED
        )

        # Cargar saldo inicial exacto de 100 fichas en el Ledger
        tx_id = uuid4()
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("100.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx_id,
            description="Recarga de 100"
        )

        # Catálogo
        self.league = League.objects.create(api_id=39, name="PL", country="England")
        self.home = Team.objects.create(api_id=10, name="ManU")
        self.away = Team.objects.create(api_id=20, name="Liv")
        self.event = Event.objects.create(
            api_id=555,
            league=self.league,
            home_team=self.home,
            away_team=self.away,
            starts_at=timezone.now() + timezone.timedelta(days=1),
            status='scheduled'
        )
        self.market = Market.objects.create(event=self.event, name="1X2")
        self.selection = Selection.objects.create(market=self.market, name="Local", odds=Decimal("2.0000"))

    @patch('fraud.services.FraudDetector.log_and_check_ip')
    def test_prevencion_doble_gasto_concurrencia_hilos(self, mock_log_ip):
        """
        Simula 3 peticiones concurrentes de apuesta de 80 fichas cada una, teniendo solo 100 de saldo.
        Verifica que select_for_update bloquee las filas y deje pasar sólo una apuesta (las otras 2 deben fallar con 409).
        """
        self.client.login(username="concurrente", password="password123")

        # Payload para apostar 80 fichas (3 apuestas simultáneas = 240, superando el saldo de 100)
        payload = {
            "selections": [{"selection_id": self.selection.id, "expected_odds": "2.0000"}],
            "stake": "80.0000"
        }

        # Ejecutar peticiones concurrentes usando ThreadPoolExecutor
        resultados_status = []

        def colocar_apuesta_concurrente():
            # Creamos un cliente DRF separado por cada hilo para simular peticiones simultáneas reales
            from rest_framework.test import APIClient
            client = APIClient()
            client.force_authenticate(user=self.user)
            
            # Generar clave de idempotencia única por request para que no se cancelen por caché de idempotencia
            key = str(uuid4())
            
            try:
                resp = client.post(
                    '/api/v1/betting/bets/',
                    data=payload,
                    format='json',
                    HTTP_IDEMPOTENCY_KEY=key
                )
                if resp.status_code == 500:
                    print("ERROR 500 DETAILS:", resp.content.decode('utf-8'))
                return resp.status_code
            except Exception as e:
                print("EXCEPTION IN TEST CLIENT:", str(e))
                return 500

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(colocar_apuesta_concurrente) for _ in range(3)]
            for fut in concurrent.futures.as_completed(futures):
                resultados_status.append(fut.result())

        # Verificar resultados
        # 1. Debe haber exactamente una petición exitosa (201 Created)
        self.assertEqual(resultados_status.count(201), 1)
        
        # 2. Las otras 2 deben haber sido rechazadas (409 en PostgreSQL por saldo, 500 en SQLite por bloqueo de base de datos)
        from django.db import connection
        if connection.vendor == 'sqlite':
            self.assertEqual(resultados_status.count(500) + resultados_status.count(409), 2)
        else:
            self.assertEqual(resultados_status.count(409), 2)

        # 3. El saldo final debe ser exactamente 20.0000 fichas (100 inicial - 80 debitado)
        self.assertEqual(LedgerEntry.get_user_balance(self.user), Decimal("20.0000"))
        
        # 4. En la base de datos debe existir exactamente 1 apuesta aceptada
        self.assertEqual(Bet.objects.filter(user=self.user).count(), 1)


class SettleAndCashoutTestCase(APITestCase):
    """
    Suite de pruebas para validar los flujos de liquidación de apuestas (Celery)
    y cobro anticipado (Cash-out).
    """
    def setUp(self):
        # Crear usuario y perfil KYC verificado
        self.user = User.objects.create_user(username="testuser", password="password123")
        self.profile = UserProfile.objects.create(
            user=self.user,
            dni="77777770",
            birth_date=timezone.now().date() - timezone.timedelta(days=365*25),
            verification_status=UserProfile.STATUS_VERIFIED
        )

        # Cargar saldo de 1000 fichas virtuales en el Ledger contable (partida doble)
        self.tx_id = uuid4()
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("1000.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=self.tx_id,
            description="Carga inicial para pruebas de liquidación"
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=Decimal("1000.0000"),
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=self.tx_id,
            description="Débito casa por carga inicial"
        )

        # Crear datos de catálogo
        self.league = League.objects.create(api_id=39, name="PL", country="England")
        self.home = Team.objects.create(api_id=10, name="ManU")
        self.away = Team.objects.create(api_id=20, name="Liv")
        
        self.event = Event.objects.create(
            api_id=987654,
            league=self.league,
            home_team=self.home,
            away_team=self.away,
            starts_at=timezone.now() + timezone.timedelta(days=1),
            status='scheduled'
        )

        self.market_1x2 = Market.objects.create(event=self.event, name="1X2")
        self.sel_home = Selection.objects.create(market=self.market_1x2, name="Local", odds=Decimal("2.0000"))
        self.sel_draw = Selection.objects.create(market=self.market_1x2, name="Empate", odds=Decimal("3.0000"))

        self.market_ou = Market.objects.create(event=self.event, name="Over/Under 2.5")
        self.sel_over = Selection.objects.create(market=self.market_ou, name="Over", odds=Decimal("1.5000"))

    def test_liquidacion_apuesta_simple_ganadora(self):
        """
        Prueba la liquidación automática de una apuesta simple ganadora por Celery,
        validando el saldo final en partida doble del Ledger.
        """
        # 1. Colocar apuesta
        self.client.login(username="testuser", password="password123")
        idempotency_key = str(uuid4())
        payload = {
            "selections": [{"selection_id": self.sel_home.id, "expected_odds": "2.0000"}],
            "stake": "100.0000"
        }
        resp = self.client.post('/api/v1/betting/bets/', data=payload, format='json', HTTP_IDEMPOTENCY_KEY=idempotency_key)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        
        bet_id = resp.data['id']
        
        # El saldo debe haber caído a 900
        self.assertEqual(LedgerEntry.get_user_balance(self.user), Decimal("900.0000"))
        
        # 2. Simular que el evento finaliza con victoria local
        self.event.status = 'finished'
        self.event.home_score = 2
        self.event.away_score = 1
        self.event.save()
        
        # 3. Correr la tarea de Celery
        from betting.tasks import settle_finished_matches
        res = settle_finished_matches()
        self.assertIn("Liquidación completada", res)
        
        # 4. Validar estado de la apuesta
        bet = Bet.objects.get(pk=bet_id)
        self.assertEqual(bet.status, 'won')
        self.assertEqual(bet.selections.first().status, 'won')
        
        # 5. Validar impacto financiero en partida doble
        # Saldo nuevo: 900 + (100 * 2.0) = 1100
        self.assertEqual(LedgerEntry.get_user_balance(self.user), Decimal("1100.0000"))
        
        # Invariante global de la partida doble debe ser exactamente 0.0000
        self.assertEqual(LedgerEntry.get_system_zero_invariant(), Decimal("0.0000"))

    def test_liquidacion_apuesta_simple_perdedora(self):
        """
        Prueba la liquidación automática de una apuesta simple perdedora por Celery,
        validando el saldo final y el ingreso de caja de la casa.
        """
        # 1. Colocar apuesta
        self.client.login(username="testuser", password="password123")
        idempotency_key = str(uuid4())
        payload = {
            "selections": [{"selection_id": self.sel_home.id, "expected_odds": "2.0000"}],
            "stake": "100.0000"
        }
        resp = self.client.post('/api/v1/betting/bets/', data=payload, format='json', HTTP_IDEMPOTENCY_KEY=idempotency_key)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        
        bet_id = resp.data['id']
        
        # 2. Simular que el evento finaliza con empate (Local pierde)
        self.event.status = 'finished'
        self.event.home_score = 1
        self.event.away_score = 1
        self.event.save()
        
        # 3. Correr la tarea de Celery
        from betting.tasks import settle_finished_matches
        settle_finished_matches()
        
        # 4. Validar estado de la apuesta
        bet = Bet.objects.get(pk=bet_id)
        self.assertEqual(bet.status, 'lost')
        self.assertEqual(bet.selections.first().status, 'lost')
        
        # 5. Validar impacto financiero
        # Saldo nuevo del usuario: se queda en 900
        self.assertEqual(LedgerEntry.get_user_balance(self.user), Decimal("900.0000"))
        
        # Fondos de apuestas pendientes deben liberarse (0)
        self.assertEqual(LedgerEntry.get_pending_bets_balance(), Decimal("0.0000"))
        
        # Invariante global de la partida doble debe ser exactamente 0.0000
        self.assertEqual(LedgerEntry.get_system_zero_invariant(), Decimal("0.0000"))

    def test_liquidacion_apuesta_combinada_recalculo_anulacion(self):
        """
        Prueba la liquidación de una combinada donde una selección se anula (void)
        y la otra se gana. Valida el recálculo correcto de la cuota combinada final (x1.0 para la anulada).
        """
        # Crear segundo evento
        event2 = Event.objects.create(
            api_id=987655,
            league=self.league,
            home_team=self.home,
            away_team=self.away,
            starts_at=timezone.now() + timezone.timedelta(days=1),
            status='scheduled'
        )
        market2 = Market.objects.create(event=event2, name="BTTS")
        sel_btts_yes = Selection.objects.create(market=market2, name="Sí", odds=Decimal("1.5000"))
        
        # 1. Colocar apuesta combinada (selections: Local @2.0 y BTTS Sí @1.5, cuota combinada = 3.0)
        self.client.login(username="testuser", password="password123")
        idempotency_key = str(uuid4())
        payload = {
            "selections": [
                {"selection_id": self.sel_home.id, "expected_odds": "2.0000"},
                {"selection_id": sel_btts_yes.id, "expected_odds": "1.5000"}
            ],
            "stake": "100.0000"
        }
        resp = self.client.post('/api/v1/betting/bets/', data=payload, format='json', HTTP_IDEMPOTENCY_KEY=idempotency_key)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        
        bet_id = resp.data['id']
        
        # 2. Simular que el evento 1 finaliza ganando el local
        self.event.status = 'finished'
        self.event.home_score = 3
        self.event.away_score = 0
        self.event.save()
        
        # 3. Simular que el evento 2 se ANULA
        event2.status = 'cancelled'
        event2.save()
        
        # 4. Correr la tarea de Celery
        from betting.tasks import settle_finished_matches
        settle_finished_matches()
        
        # 5. Validar estado de la apuesta y recálculo de cuotas
        # Bet debe ser ganadora ('won') pero con cuota reducida de 2.0 * 1.0 = 2.0 (payout = 200)
        bet = Bet.objects.get(pk=bet_id)
        self.assertEqual(bet.status, 'won')
        self.assertEqual(bet.selections.get(selection=self.sel_home).status, 'won')
        self.assertEqual(bet.selections.get(selection=sel_btts_yes).status, 'void')
        
        # Payout real debe ser 200.0000
        self.assertEqual(bet.potential_payout, Decimal("200.0000"))
        
        # Saldo nuevo: 900 + 200 = 1100
        self.assertEqual(LedgerEntry.get_user_balance(self.user), Decimal("1100.0000"))
        
        # Invariante global de la partida doble debe ser exactamente 0.0000
        self.assertEqual(LedgerEntry.get_system_zero_invariant(), Decimal("0.0000"))

    def test_cashout_exitoso_ganancia(self):
        """
        Prueba la ejecución exitosa de un cash-out en una posición de ganancia
        (cuotas bajaron a favor del usuario), cobrando síncronamente y verificando saldo.
        """
        # 1. Colocar apuesta simple a cuota 2.0 con stake de 100
        self.client.login(username="testuser", password="password123")
        idempotency_key = str(uuid4())
        payload = {
            "selections": [{"selection_id": self.sel_home.id, "expected_odds": "2.0000"}],
            "stake": "100.0000"
        }
        resp = self.client.post('/api/v1/betting/bets/', data=payload, format='json', HTTP_IDEMPOTENCY_KEY=idempotency_key)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        
        bet_id = resp.data['id']
        
        # 2. Modificar cuota actual en la base de datos a 1.5000 (probabilidad aumentó, cuota bajó)
        self.sel_home.odds = Decimal("1.5000")
        self.sel_home.save()
        
        # 3. Solicitar cash-out
        # Fórmula: cashout = stake * (odds_original / odds_actual) * 0.95
        # cashout = 100 * (2.0000 / 1.5000) * 0.95 = 100 * 1.33333 * 0.95 = 126.6667
        resp_cash = self.client.post(f'/api/v1/betting/bets/{bet_id}/cashout/')
        self.assertEqual(resp_cash.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_cash.data['status'], 'cashed_out')
        
        # El potencial payout devuelto debe ser exactamente el valor del cashout calculado
        self.assertEqual(Decimal(resp_cash.data['potential_payout']), Decimal("126.6667"))
        
        # 4. Validar saldo final: 900 + 126.6667 = 1026.6667
        self.assertEqual(LedgerEntry.get_user_balance(self.user), Decimal("1026.6667"))
        
        # Verificar que la casa pagó la ganancia neta de 26.6667 fichas
        # LedgerEntry global sum = 0
        self.assertEqual(LedgerEntry.get_system_zero_invariant(), Decimal("0.0000"))

    def test_cashout_bloqueado_si_partido_iniciado_o_finalizado(self):
        """
        Valida que se impida el cobro anticipado de un ticket si alguno de los partidos ya finalizó.
        """
        # 1. Colocar apuesta
        self.client.login(username="testuser", password="password123")
        idempotency_key = str(uuid4())
        payload = {
            "selections": [{"selection_id": self.sel_home.id, "expected_odds": "2.0000"}],
            "stake": "100.0000"
        }
        resp = self.client.post('/api/v1/betting/bets/', data=payload, format='json', HTTP_IDEMPOTENCY_KEY=idempotency_key)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        
        bet_id = resp.data['id']
        
        # 2. Cambiar estado del evento a finalizado
        self.event.status = 'finished'
        self.event.save()
        
        # 3. Intentar cash-out
        resp_cash = self.client.post(f'/api/v1/betting/bets/{bet_id}/cashout/')
        self.assertEqual(resp_cash.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("El cash-out no está disponible", resp_cash.data['error'])

    def test_cashout_doble_gasto_bloqueado(self):
        """
        Valida que no se pueda cobrar un cash-out dos veces para el mismo boleto de apuesta.
        """
        # 1. Colocar apuesta
        self.client.login(username="testuser", password="password123")
        idempotency_key = str(uuid4())
        payload = {
            "selections": [{"selection_id": self.sel_home.id, "expected_odds": "2.0000"}],
            "stake": "100.0000"
        }
        resp = self.client.post('/api/v1/betting/bets/', data=payload, format='json', HTTP_IDEMPOTENCY_KEY=idempotency_key)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        
        bet_id = resp.data['id']
        
        # 2. Primer cash-out (debe ser exitoso)
        resp_cash1 = self.client.post(f'/api/v1/betting/bets/{bet_id}/cashout/')
        self.assertEqual(resp_cash1.status_code, status.HTTP_200_OK)
        
        # 3. Segundo cash-out (debe ser rechazado)
        resp_cash2 = self.client.post(f'/api/v1/betting/bets/{bet_id}/cashout/')
        self.assertEqual(resp_cash2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No se puede realizar cash-out en una apuesta en estado: Cobro Anticipado", resp_cash2.data['error'])


from channels.testing import WebsocketCommunicator
from config.asgi import application

class WebSocketRealTimeTestCase(APITestCase):
    """
    Suite de pruebas para verificar el funcionamiento en tiempo real
    de los canales WebSockets (EventConsumer y UserNotificationConsumer).
    """
    def setUp(self):
        # Crear usuario y perfil KYC verificado
        self.user = User.objects.create_user(username="wsuser", password="password123")
        self.profile = UserProfile.objects.create(
            user=self.user,
            dni="77777779",
            birth_date=timezone.now().date() - timezone.timedelta(days=365*25),
            verification_status=UserProfile.STATUS_VERIFIED
        )

        # Cargar saldo de 500 fichas
        tx_id = uuid4()
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("500.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx_id,
            description="Carga inicial para pruebas WS"
        )

        # Crear datos de catálogo
        self.league = League.objects.create(api_id=39, name="PL", country="England")
        self.home = Team.objects.create(api_id=10, name="ManU")
        self.away = Team.objects.create(api_id=20, name="Liv")
        
        self.event = Event.objects.create(
            api_id=777888,
            league=self.league,
            home_team=self.home,
            away_team=self.away,
            starts_at=timezone.now() + timezone.timedelta(days=1),
            status='scheduled'
        )

        self.market = Market.objects.create(event=self.event, name="1X2")
        self.sel_home = Selection.objects.create(market=self.market, name="Local", odds=Decimal("2.0000"))

    async def test_conexion_publica_event_consumer_exitosa(self):
        """
        Verifica que cualquier cliente pueda conectarse al canal público del evento
        y recibir actualizaciones en vivo de goles y re-cotización.
        """
        communicator = WebsocketCommunicator(application, f"ws/events/{self.event.api_id}/")
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Simular envío de evento en vivo ( odds_changed )
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        
        await channel_layer.group_send(
            f"event_{self.event.api_id}",
            {
                "type": "odds_changed",
                "selection_id": self.sel_home.id,
                "selection_name": self.sel_home.name,
                "new_odds": "2.5000"
            }
        )
        
        # Esperar y verificar respuesta
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'odds_changed')
        self.assertEqual(response['new_odds'], '2.5000')
        self.assertEqual(response['selection_name'], 'Local')
        
        await communicator.disconnect()

    async def test_conexion_privada_user_notification_consumer_anonimo_rechazada(self):
        """
        Valida que un usuario anónimo (no autenticado) sea rechazado de inmediato
        al intentar conectarse al canal privado de notificaciones.
        """
        communicator = WebsocketCommunicator(application, "ws/notifications/")
        connected, subprotocol = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_conexion_privada_user_notification_consumer_autenticado_exitosa(self):
        """
        Valida que un usuario debidamente autenticado pueda conectarse con éxito
        y recibir notificaciones privadas de transacciones.
        """
        communicator = WebsocketCommunicator(application, "ws/notifications/")
        communicator.scope['user'] = self.user
        
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)
        
        # Simular el envío de una notificación contable privada
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        
        await channel_layer.group_send(
            f"user_{self.user.id}",
            {
                "type": "bet_settled",
                "bet_id": 12,
                "status": "won",
                "payout": "300.0000",
                "message": "¡Tu apuesta #12 ha sido ganadora!"
            }
        )
        
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'bet_settled')
        self.assertEqual(response['bet_id'], 12)
        self.assertEqual(response['status'], 'won')
        self.assertEqual(response['payout'], '300.0000')
        
        await communicator.disconnect()


class LiveAndCombinadasTestCase(APITestCase):
    """
    Suite de pruebas unitarias e integración para la Fase 11: Apuestas Combinadas e In-Play.
    """
    def setUp(self):
        from uuid import uuid4
        # Crear usuario y perfil KYC verificado
        self.user = User.objects.create_user(username="live_gamer", password="password123")
        from users.models import UserProfile
        self.profile = UserProfile.objects.create(
            user=self.user,
            dni="44445555",
            birth_date=timezone.now().date() - timezone.timedelta(days=365 * 21),
            verification_status=UserProfile.STATUS_VERIFIED
        )
        
        # Cargar saldo inicial
        from wallet.models import LedgerEntry
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("500.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=uuid4(),
            description="Fichas iniciales"
        )

        # Catálogo deportivo de ligas y equipos
        self.league = League.objects.create(api_id=39, name="La Liga", country="España")
        self.team_home = Team.objects.create(api_id=1, name="Real Madrid")
        self.team_away = Team.objects.create(api_id=2, name="Barcelona")
        
        # Evento 1
        self.event1 = Event.objects.create(
            api_id=901,
            league=self.league,
            home_team=self.team_home,
            away_team=self.team_away,
            starts_at=timezone.now() + timezone.timedelta(hours=2),
            status='scheduled'
        )
        self.market1 = Market.objects.create(event=self.event1, name="1X2")
        self.sel1_home = Selection.objects.create(market=self.market1, name="Local", odds=Decimal("2.0000"))
        
        # Evento 2
        self.event2 = Event.objects.create(
            api_id=902,
            league=self.league,
            home_team=self.team_home,
            away_team=self.team_away,
            starts_at=timezone.now() + timezone.timedelta(hours=4),
            status='scheduled'
        )
        self.market2 = Market.objects.create(event=self.event2, name="1X2")
        self.sel2_draw = Selection.objects.create(market=self.market2, name="Empate", odds=Decimal("3.0000"))

        from django.urls import reverse
        self.url_bets = reverse('bet-list')

    def test_apuestas_combinadas_success_and_settlement(self):
        """
        Valida que se coloquen correctamente apuestas combinadas y que
        Celery las liquide adecuadamente cuando todas las selecciones ganan.
        """
        from uuid import uuid4
        from wallet.models import LedgerEntry
        self.client.force_authenticate(user=self.user)
        idemp = uuid4()
        
        # Colocar combinada con 2 selecciones de eventos distintos
        payload = {
            'stake': '100.0000',
            'selections': [
                {'selection_id': self.sel1_home.id, 'expected_odds': '2.0000'},
                {'selection_id': self.sel2_draw.id, 'expected_odds': '3.0000'},
            ]
        }
        
        response = self.client.post(self.url_bets, payload, format='json', HTTP_IDEMPOTENCY_KEY=str(idemp))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        bet = Bet.objects.get(pk=response.data['id'])
        self.assertEqual(bet.type, 'accumulator')
        self.assertEqual(bet.potential_payout, Decimal("600.0000")) # stake (100) * odds1 (2) * odds2 (3) = 600
        
        # Verificar Ledger (DEBIT a wallet, CREDIT a apuestas_pendientes)
        balance = LedgerEntry.get_user_balance(self.user)
        self.assertEqual(balance, Decimal("400.0000"))
        
        # Simular que los partidos terminan y resuelven las selecciones como ganadoras
        self.event1.status = 'finished'
        self.event1.home_score = 2
        self.event1.away_score = 1
        self.event1.save()
        
        self.event2.status = 'finished'
        self.event2.home_score = 1
        self.event2.away_score = 1
        self.event2.save()
        
        # Ejecutar liquidación Celery
        from betting.tasks import settle_finished_matches
        settle_finished_matches()
        
        # Validar estado del boleto final
        bet.refresh_from_db()
        self.assertEqual(bet.status, 'won')
        
        # Saldo del usuario debe ser balance_previo (400) + payout (600) = 1000
        balance_after = LedgerEntry.get_user_balance(self.user)
        self.assertEqual(balance_after, Decimal("1000.0000"))

    def test_apuestas_combinadas_one_lost_settles_as_lost(self):
        """
        Valida que si una de las selecciones del acumulador se pierde,
        todo el ticket acumulador resuelva como perdido.
        """
        from uuid import uuid4
        from wallet.models import LedgerEntry
        self.client.force_authenticate(user=self.user)
        idemp = uuid4()
        
        payload = {
            'stake': '100.0000',
            'selections': [
                {'selection_id': self.sel1_home.id, 'expected_odds': '2.0000'},
                {'selection_id': self.sel2_draw.id, 'expected_odds': '3.0000'},
            ]
        }
        
        response = self.client.post(self.url_bets, payload, format='json', HTTP_IDEMPOTENCY_KEY=str(idemp))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        bet = Bet.objects.get(pk=response.data['id'])
        
        # Simular que partido 1 gana (Local 2-1), pero partido 2 pierde (Gana Local 2-0 en lugar de empate)
        self.event1.status = 'finished'
        self.event1.home_score = 2
        self.event1.away_score = 1
        self.event1.save()
        
        self.event2.status = 'finished'
        self.event2.home_score = 2
        self.event2.away_score = 0
        self.event2.save()
        
        from betting.tasks import settle_finished_matches
        settle_finished_matches()
        
        # Validar estado del boleto
        bet.refresh_from_db()
        self.assertEqual(bet.status, 'lost')
        
        # El saldo sigue en 400.00 (el stake se perdió por completo)
        self.assertEqual(LedgerEntry.get_user_balance(self.user), Decimal("400.0000"))

    def test_in_play_betting_enabled(self):
        """
        Verifica que se puedan colocar apuestas síncronas exitosamente si el evento está en vivo ('in_play').
        """
        from uuid import uuid4
        self.client.force_authenticate(user=self.user)
        idemp = uuid4()
        
        # Modificar evento a in_play
        self.event1.status = 'in_play'
        self.event1.starts_at = timezone.now() - timezone.timedelta(minutes=15)
        self.event1.save()
        
        payload = {
            'stake': '50.0000',
            'selections': [
                {'selection_id': self.sel1_home.id, 'expected_odds': '2.0000'},
            ]
        }
        
        response = self.client.post(self.url_bets, payload, format='json', HTTP_IDEMPOTENCY_KEY=str(idemp))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        bet = Bet.objects.get(pk=response.data['id'])
        self.assertEqual(bet.status, 'accepted')

    def test_automatic_market_suspension_on_goal(self):
        """
        Verifica que cuando ocurra un gol (cambio de marcador), los mercados del partido
        se suspendan automáticamente y cualquier intento de apuesta sea bloqueado.
        """
        from uuid import uuid4
        # Cambiar a in_play
        self.event1.status = 'in_play'
        self.event1.home_score = 0
        self.event1.away_score = 0
        self.event1.save()
        
        # Mockear get_live_fixtures para simular un gol en vivo (home_score cambia de 0 a 1)
        mock_response = [
            {
                'fixture': {'id': self.event1.api_id, 'status': {'short': '1H', 'long': 'First Half', 'elapsed': 10}, 'date': self.event1.starts_at.isoformat()},
                'league': {'id': 39},
                'goals': {'home': 1, 'away': 0}
            }
        ]
        
        with patch('betting.services.APIFootballClient.get_live_fixtures', return_value=mock_response):
            sync = SyncEngine()
            synced = sync.sync_live_scores()
            self.assertEqual(synced, 1)
            
        # Comprobar que el marcador se actualizó en DB
        self.event1.refresh_from_db()
        self.assertEqual(self.event1.home_score, 1)
        
        # Comprobar que los mercados de este evento se inhabilitaron
        market = Market.objects.get(pk=self.market1.id)
        self.assertFalse(market.is_active)
        
        # Intentar colocar una apuesta síncrona sobre el mercado suspendido -> Debe fallar
        self.client.force_authenticate(user=self.user)
        idemp = uuid4()
        
        payload = {
            'stake': '50.0000',
            'selections': [
                {'selection_id': self.sel1_home.id, 'expected_odds': '2.0000'},
            ]
        }
        
        response = self.client.post(self.url_bets, payload, format='json', HTTP_IDEMPOTENCY_KEY=str(idemp))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("suspendido", str(response.data))

    def test_celery_task_reactivation(self):
        """
        Verifica que la ejecución de la tarea de reactivación Celery resume_markets_after_suspension
        vuelva a habilitar de forma segura los mercados inactivos.
        """
        # Suspender mercados
        self.market1.is_active = False
        self.market1.save()
        
        from betting.tasks import resume_markets_after_suspension
        res = resume_markets_after_suspension(self.event1.id)
        self.assertIn("reactivados", res)
        
        self.market1.refresh_from_db()
        self.assertTrue(self.market1.is_active)


class TheOddsAPITestCase(APITestCase):
    """
    Suite de pruebas de integración para el nuevo proveedor The Odds API.
    Valida la sincronización de eventos, hashing determinista de IDs, cuotas y marcadores.
    """
    def setUp(self):
        from betting.models import League, Team, Event, Market, Selection
        self.league_id = 140 # La Liga
        
    @patch('betting.the_odds_api.TheOddsAPIClient.get_fixtures')
    def test_sync_fixtures_the_odds_api(self, mock_get_fixtures):
        """
        Prueba la sincronización de eventos y cuotas a través de The Odds API
        empleando el enmascarado determinista de IDs tipo string.
        """
        # Configurar mock response de The Odds API
        mock_get_fixtures.return_value = [
            {
                "id": "mock_event_hash_12345",
                "sport_key": "soccer_spain_la_liga",
                "sport_title": "La Liga",
                "commence_time": "2026-05-28T20:00:00Z",
                "home_team": "Real Madrid",
                "away_team": "Barcelona",
                "bookmakers": [
                    {
                        "key": "bet365",
                        "title": "Bet365",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Real Madrid", "price": 2.10},
                                    {"name": "Barcelona", "price": 3.60},
                                    {"name": "Draw", "price": 3.40}
                                ]
                            },
                            {
                                "key": "totals",
                                "outcomes": [
                                    {"name": "Over", "price": 1.85, "point": 2.5},
                                    {"name": "Under", "price": 1.95, "point": 2.5}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

        # Configurar settings del proveedor activo
        with self.settings(SPORTS_API_PROVIDER='the_odds_api'):
            from betting.services import SyncEngine, string_to_integer_id
            sync = SyncEngine()
            count = sync.sync_fixtures(self.league_id)
            
            # 1. Debe haber sincronizado 1 partido
            self.assertEqual(count, 1)
            
            # 2. El ID del partido en DB debe ser el hash entero determinista
            expected_id = string_to_integer_id("mock_event_hash_12345")
            event = Event.objects.get(api_id=expected_id)
            self.assertEqual(event.home_team.name, "Real Madrid")
            self.assertEqual(event.away_team.name, "Barcelona")
            
            # 3. Comprobar creación de mercados y cuotas con margen (por defecto 5%)
            # Cuota de Real Madrid = 2.10 * 0.95 = 1.9950
            sel_home = Selection.objects.get(market__event=event, name="Local")
            self.assertEqual(sel_home.odds, Decimal("1.9950"))
            
            sel_draw = Selection.objects.get(market__event=event, name="Empate")
            self.assertEqual(sel_draw.odds, Decimal("3.2300")) # 3.40 * 0.95 = 3.2300

    @patch('betting.the_odds_api.TheOddsAPIClient.get_live_fixtures')
    def test_sync_live_scores_the_odds_api_goal_suspension(self, mock_get_live_fixtures):
        """
        Prueba que la sincronización de marcadores en vivo de The Odds API
        actualice la base de datos y dispare la suspensión de mercados ante un gol.
        """
        from betting.services import string_to_integer_id
        # Pre-crear liga, equipos y partido en BD
        event_hash = "live_event_hash_abc"
        event_id = string_to_integer_id(event_hash)
        
        league = League.objects.create(api_id=self.league_id, name="La Liga", country="España")
        home = Team.objects.create(api_id=string_to_integer_id("Real Madrid"), name="Real Madrid")
        away = Team.objects.create(api_id=string_to_integer_id("Barcelona"), name="Barcelona")
        
        event = Event.objects.create(
            api_id=event_id,
            league=league,
            home_team=home,
            away_team=away,
            starts_at=timezone.now(),
            status='in_play',
            home_score=0,
            away_score=0
        )
        
        market = Market.objects.create(event=event, name="1X2", is_active=True)
        
        # Mock de marcador en vivo (gol de Real Madrid 1-0)
        mock_get_live_fixtures.return_value = [
            {
                "id": event_hash,
                "sport_key": "soccer_spain_la_liga",
                "sport_title": "La Liga",
                "commence_time": event.starts_at.isoformat(),
                "home_team": "Real Madrid",
                "away_team": "Barcelona",
                "completed": False,
                "scores": [
                    {"name": "Real Madrid", "score": "1"},
                    {"name": "Barcelona", "score": "0"}
                ],
                "_league_id": self.league_id
            }
        ]
        
        with self.settings(SPORTS_API_PROVIDER='the_odds_api'):
            from betting.services import SyncEngine
            sync = SyncEngine()
            count = sync.sync_live_scores()
            self.assertEqual(count, 1)
            
            event.refresh_from_db()
            self.assertEqual(event.home_score, 1)
            self.assertEqual(event.status, 'in_play')
            
            # Los mercados deben haberse suspendido automáticamente por el gol
            market.refresh_from_db()
            self.assertFalse(market.is_active)






