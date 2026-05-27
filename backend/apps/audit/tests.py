# -*- coding: utf-8 -*-
"""
Suite de Pruebas Unitarias y de Integración para la Fase 8: Auditoría Inmutable (Cadena de Hash).

Cubre:
    1. Interceptores de señales automáticos (post_save/pre_save) para LedgerEntry, Bet y Selection.
    2. Tabla append-only: restricción absoluta de actualizaciones y eliminaciones.
    3. Endpoint forense AuditVerifyView comprobando la integridad criptográfica de la cadena de hashes.
    4. Simulación de intrusión/fraude: alteración de registros directamente en la base de datos (bypass vía SQL)
       y validación de que el verificador de hashes detecta e identifica el fraude.
"""
from decimal import Decimal
from uuid import uuid4
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APITestCase
from wallet.models import LedgerEntry
from betting.models import League, Team, Event, Market, Selection, Bet
from audit.models import AuditLogEntry

class AuditImmutableTestCase(APITestCase):
    """
    Clase de prueba para validar la consistencia, inmutabilidad y detección de fraudes de la cadena de bloques local.
    """

    def setUp(self):
        # Crear usuario apostador verificado
        self.user = User.objects.create_user(username="test_auditor", password="password123")
        from users.models import UserProfile
        self.profile = UserProfile.objects.create(
            user=self.user,
            dni="77777777",
            birth_date=timezone.now().date() - timezone.timedelta(days=365 * 25),
            verification_status=UserProfile.STATUS_VERIFIED
        )

        # Crear administrador para poder llamar al endpoint de verificación
        self.admin_user = User.objects.create_superuser(username="admin_auditor", password="adminpassword", email="admin@audit.pe")

        # Catálogo deportivo mínimo
        self.league = League.objects.create(api_id=39, name="La Liga", country="España")
        self.home_team = Team.objects.create(api_id=1, name="Real Madrid")
        self.away_team = Team.objects.create(api_id=2, name="Barcelona")
        self.event = Event.objects.create(
            api_id=100,
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            starts_at=timezone.now() + timezone.timedelta(days=1),
            status='scheduled'
        )
        self.market = Market.objects.create(event=self.event, name="1X2")
        self.selection = Selection.objects.create(market=self.market, name="Local", odds=Decimal("2.0000"))

    def test_audit_log_created_on_wallet_movement(self):
        """
        1. Toda transacción de doble entrada (LedgerEntry) debe disparar la creación de un AuditLogEntry.
        """
        # Limpiar registros previos de auditoría creados durante el setup
        AuditLogEntry.objects.all().delete
        # Nota: Como borrar por ORM lanza excepción, borramos vía queryset directo para preparar el test
        AuditLogEntry.objects.all()._raw_delete(using='default')

        # Simular una recarga en la billetera
        tx_id = uuid4()
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("150.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx_id,
            description="Recarga de prueba"
        )

        # Verificar que se creó el registro contable y su respectivo log de auditoría
        logs = AuditLogEntry.objects.filter(event_type=AuditLogEntry.EVENT_WALLET_MOVEMENT)
        self.assertGreaterEqual(logs.count(), 1)
        
        log = logs.first()
        self.assertEqual(log.payload['username'], "test_auditor")
        self.assertEqual(log.payload['amount'], "150.0000")
        self.assertEqual(log.payload['direction'], "CREDIT")
        self.assertEqual(log.payload['transaction_id'], str(tx_id))
        self.assertIsNotNone(log.current_hash)

    def test_audit_log_created_on_bet_placement_and_settlement(self):
        """
        2. La creación y el cambio de estado de boletos (Bet) deben registrarse en la bitácora inmutable.
        """
        # Cargar saldo
        tx_id = uuid4()
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("500.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx_id,
            description="Fianza"
        )

        # Limpiar bitácora
        AuditLogEntry.objects.all()._raw_delete(using='default')

        # Colocar apuesta
        bet = Bet.objects.create(
            user=self.user,
            status='accepted',
            type='simple',
            stake=Decimal("100.0000"),
            potential_payout=Decimal("200.0000"),
            idempotency_key=uuid4()
        )

        # 1. Verificar que se auditó la colocación de la apuesta
        logs_placement = AuditLogEntry.objects.filter(event_type=AuditLogEntry.EVENT_BET_STATUS_CHANGE)
        self.assertGreaterEqual(logs_placement.count(), 1)
        
        log_placement = logs_placement.first()
        self.assertEqual(log_placement.payload['bet_id'], bet.id)
        self.assertEqual(log_placement.payload['status'], "accepted")

        # 2. Liquidar la apuesta como perdida
        bet.status = 'lost'
        bet.save()

        # Verificar que se auditó la transición de estado a 'lost'
        logs_settled = AuditLogEntry.objects.filter(event_type=AuditLogEntry.EVENT_BET_STATUS_CHANGE, payload__status='lost')
        self.assertEqual(logs_settled.count(), 1)

    def test_audit_log_created_on_odds_fluctuation(self):
        """
        3. Toda modificación de cuotas (odds) debe registrar la variación en el catálogo.
        """
        # Limpiar bitácora
        AuditLogEntry.objects.all()._raw_delete(using='default')

        # Cambiar cuota de la selección deportiva
        self.selection.odds = Decimal("3.2500")
        self.selection.save()

        # Verificar que se generó la entrada de auditoría correspondiente
        logs = AuditLogEntry.objects.filter(event_type=AuditLogEntry.EVENT_ODDS_CHANGE)
        self.assertEqual(logs.count(), 1)

        log = logs.first()
        self.assertEqual(log.payload['selection_name'], "Local")
        self.assertEqual(log.payload['old_odds'], "2.0000")
        self.assertEqual(log.payload['new_odds'], "3.2500")

    def test_audit_verify_view_integrity_and_tampering_detection(self):
        """
        4. Valida que AuditVerifyView detecte la cadena como íntegra y detecte fraudes si
           algún registro es alterado de forma maliciosa.
        """
        # Crear serie de transacciones válidas para poblar la cadena
        tx_id = uuid4()
        LedgerEntry.objects.create(
            user=self.user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal("100.0000"),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx_id,
            description="Recarga A"
        )
        self.selection.odds = Decimal("1.8000")
        self.selection.save()

        # 1. Autenticar como administrador y verificar conformidad inicial
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('audit-verify')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'verified')
        self.assertGreater(response.data['registros_auditados'], 1)

        # 2. Simular un HACK/FRAUDE: alteración de registros directamente en la base de datos.
        # Como save() bloquea ediciones, realizamos un bypass directo usando QuerySet.update()
        # que compila directo a SQL sin llamar a save().
        logs_actuales = list(AuditLogEntry.objects.all().order_by('id'))
        target_log = logs_actuales[1] # Elegimos el segundo log
        
        # Alteramos el payload maliciosamente para simular que cambiamos el saldo transferido
        altered_payload = dict(target_log.payload)
        altered_payload['amount'] = "99999.0000" # Sobrescribimos el monto para darnos saldo infinito
        
        AuditLogEntry.objects.filter(id=target_log.id).update(payload=altered_payload)

        # 3. Consultar nuevamente el verificador de integridad forense
        response = self.client.get(url)
        # Debe rechazar con 400 Bad Request debido a que las firmas de SHA-256 no coinciden
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['status'], 'compromised')
        self.assertEqual(response.data['registro_comprometido_id'], target_log.id)
        self.assertIn("alterados", response.data['mensaje'])

    def test_audit_log_entry_blocks_manual_updates_and_deletions(self):
        """
        5. Los registros de la tabla de auditoría inmutable no permiten actualizaciones ni borrados por ORM.
        """
        # Crear un registro inicial
        log = AuditLogEntry.objects.create(
            event_type=AuditLogEntry.EVENT_WALLET_MOVEMENT,
            payload={'datos': 'legítimos'}
        )

        # 1. Intentar actualizar (debe lanzar ValidationError)
        with self.assertRaises(ValidationError):
            log.payload = {'datos': 'modificados'}
            log.save()

        # 2. Intentar borrar (debe lanzar ValidationError)
        with self.assertRaises(ValidationError):
            log.delete()
