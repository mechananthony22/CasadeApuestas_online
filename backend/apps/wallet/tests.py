# -*- coding: utf-8 -*-
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.contrib.auth.models import User
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse

from hypothesis import given, strategies as st, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant

from rest_framework import status
from rest_framework.test import APITestCase

from .models import LedgerEntry


# ============================================================
# Constantes de prueba
# ============================================================
SALDO_INICIAL = Decimal('1000.0000')
MONTO_PRUEBA = Decimal('100.0000')
MONTO_PEQUEÑO = Decimal('0.0001')


# ============================================================
# Tests del modelo LedgerEntry
# ============================================================

class TestModeloLedgerEntry(TestCase):
    """Tests unitarios del modelo LedgerEntry y sus métodos de clase."""

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='wallet_test',
            email='wallet@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418591',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )

    def test_get_user_balance_retorna_cero_sin_movimientos(self):
        """Un usuario sin movimientos debe tener saldo 0.0000."""
        balance = LedgerEntry.get_user_balance(self.usuario)
        self.assertEqual(balance, Decimal('0.0000'))

    def test_deposito_incrementa_balance_correctamente(self):
        """Un depósito de 1000 debe resultar en balance = 1000."""
        from uuid import uuid4
        tx = uuid4()

        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
        )

        balance = LedgerEntry.get_user_balance(self.usuario)
        self.assertEqual(balance, MONTO_PRUEBA)

    def test_retiro_decrementa_balance_correctamente(self):
        """Después de depositar y retirar, el balance debe ser la diferencia."""
        from uuid import uuid4

        deposito_tx = uuid4()
        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=SALDO_INICIAL,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=deposito_tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=SALDO_INICIAL,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=deposito_tx,
        )

        retiro_tx = uuid4()
        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=retiro_tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=retiro_tx,
        )

        balance = LedgerEntry.get_user_balance(self.usuario)
        self.assertEqual(balance, SALDO_INICIAL - MONTO_PRUEBA)

    def test_transaction_id_agrupa_entries_correctamente(self):
        """El UUID de transacción debe ser el mismo para débito y crédito."""
        from uuid import uuid4
        tx = uuid4()

        entry1 = LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
        )
        entry2 = LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
        )

        self.assertEqual(entry1.transaction_id, entry2.transaction_id)


# ============================================================
# INVARIANTE 1: Suma por transacción = 0
# ============================================================

class TestInvarianteSumaCero(TestCase):
    """
    INVARIANTE OBLIGATORIO #1:
    Para cada transacción (mismo transaction_id),
    la suma algebraica de todos sus movimientos debe ser 0.
    """

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='invariante_test',
            email='invariante@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418592',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )

    def test_transaccion_deposito_suma_cero(self):
        """Un depósito: CREDIT wallet + DEBIT casa = 0."""
        from uuid import uuid4
        tx = uuid4()

        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
        )

        credits = LedgerEntry.objects.filter(
            transaction_id=tx,
            direction=LedgerEntry.Direction.CREDIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        debits = LedgerEntry.objects.filter(
            transaction_id=tx,
            direction=LedgerEntry.Direction.DEBIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        self.assertEqual(credits - debits, Decimal('0.0000'))

    def test_transaccion_retiro_suma_cero(self):
        """Un retiro: DEBIT wallet + CREDIT casa = 0."""
        from uuid import uuid4
        tx = uuid4()

        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=MONTO_PRUEBA,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
        )

        credits = LedgerEntry.objects.filter(
            transaction_id=tx,
            direction=LedgerEntry.Direction.CREDIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        debits = LedgerEntry.objects.filter(
            transaction_id=tx,
            direction=LedgerEntry.Direction.DEBIT
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        self.assertEqual(credits - debits, Decimal('0.0000'))


# ============================================================
# INVARIANTE 2: Ningún usuario tiene saldo negativo
# ============================================================

class TestInvarianteSaldoNoNegativo(TestCase):
    """
    INVARIANTE OBLIGATORIO #2:
    Ningún usuario puede tener saldo negativo en wallet_usuario.
    """

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='saldo_test',
            email='saldo@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418593',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )

    def test_usuario_sin_fondos_tiene_saldo_cero(self):
        """Un usuario sin depósitos debe tener saldo 0, no negativo."""
        balance = LedgerEntry.get_user_balance(self.usuario)
        self.assertGreaterEqual(balance, Decimal('0.0000'))


# ============================================================
# INVARIANTE 3: Saldo total del sistema = constante
# ============================================================

class TestInvarianteSistemaConstante(TestCase):
    """
    INVARIANTE OBLIGATORIO #3:
    La suma de todas las cuentas del sistema SIEMPRE debe ser 0.
    """

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='sistema_test',
            email='sistema@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418594',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )

    def test_sistema_vacio_suma_cero(self):
        """Sin movimientos, el sistema debe sumar 0."""
        total = LedgerEntry.get_system_zero_invariant()
        self.assertEqual(total, Decimal('0.0000'))

    def test_deposito_mantiene_invariante_sistema(self):
        """Después de un depósito, la suma del sistema sigue siendo 0."""
        from uuid import uuid4
        tx = uuid4()

        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal('500.0000'),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=Decimal('500.0000'),
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
        )

        total = LedgerEntry.get_system_zero_invariant()
        self.assertEqual(total, Decimal('0.0000'))


# ============================================================
# Property-Based Testing con Hypothesis
# ============================================================
from hypothesis.extra.django import TestCase as HypothesisTestCase


class TestHypothesisInvariantes(HypothesisTestCase):
    """
    Tests basados en propiedades usando Hypothesis.
    Genera secuencias aleatorias de transacciones y verifica
    que los invariantes se mantengan SIEMPRE.
    """

    def setUp(self):
        User.objects.filter(username='hypothesis_test').delete()
        self.usuario = User.objects.create_user(
            username='hypothesis_test',
            email='hypothesis@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418595',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )

    @given(
        st.lists(
            st.decimals(
                min_value=Decimal('0.01'),
                max_value=Decimal('10000.00'),
                places=4
            ),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=20)
    def test_invariante_suma_cero_con_depositos_aleatorios(self, montos):
        """Para cualquier conjunto de depósitos, la suma del sistema = 0."""
        from uuid import uuid4

        for monto in montos:
            tx = uuid4()
            LedgerEntry.objects.create(
                user=self.usuario,
                account=LedgerEntry.Account.WALLET_USUARIO,
                amount=monto,
                direction=LedgerEntry.Direction.CREDIT,
                transaction_id=tx,
            )
            LedgerEntry.objects.create(
                user=None,
                account=LedgerEntry.Account.CASA,
                amount=monto,
                direction=LedgerEntry.Direction.DEBIT,
                transaction_id=tx,
            )

        total = LedgerEntry.get_system_zero_invariant()
        self.assertEqual(
            total,
            Decimal('0.0000'),
            f"El invariante del sistema se rompió después de {len(montos)} transacciones"
        )

    @given(
        st.decimals(
            min_value=Decimal('0.01'),
            max_value=Decimal('500.00'),
            places=4
        )
    )
    @settings(max_examples=20)
    def test_saldo_usuario_nunca_negativo(self, monto_deposito):
        """El saldo del usuario nunca debe ser negativo."""
        from uuid import uuid4

        tx = uuid4()
        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=monto_deposito,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=monto_deposito,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
        )

        balance = LedgerEntry.get_user_balance(self.usuario)
        self.assertGreaterEqual(
            balance,
            Decimal('0.0000'),
            f"El saldo del usuario es negativo: {balance}"
        )


# ============================================================
# Stateful Testing: Simulación de múltiples operaciones
# ============================================================

class TestStatefulWallet(RuleBasedStateMachine):
    """
    Máquina de estados para probar secuencias de operaciones
    de depósito y retiro, verificando invariantes en cada paso.
    """

    def __init__(self):
        super().__init__()
        self.usuario = User.objects.create_user(
            username=f'stateful_{id(self)}',
            email=f'stateful_{id(self)}@fairbet.pe',
            password='Password123!'
        )
        self.saldo_esperado = Decimal('0.0000')

    @rule(
        monto=st.decimals(
            min_value=Decimal('0.01'),
            max_value=Decimal('1000.00'),
            places=4
        )
    )
    def deposito(self, monto):
        from uuid import uuid4
        tx = uuid4()

        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=monto,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=monto,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
        )

        self.saldo_esperado += monto

    @rule(
        monto=st.decimals(
            min_value=Decimal('0.01'),
            max_value=Decimal('500.00'),
            places=4
        )
    )
    def retiro(self, monto):
        if self.saldo_esperado >= monto:
            from uuid import uuid4
            tx = uuid4()

            LedgerEntry.objects.create(
                user=self.usuario,
                account=LedgerEntry.Account.WALLET_USUARIO,
                amount=monto,
                direction=LedgerEntry.Direction.DEBIT,
                transaction_id=tx,
            )
            LedgerEntry.objects.create(
                user=None,
                account=LedgerEntry.Account.CASA,
                amount=monto,
                direction=LedgerEntry.Direction.CREDIT,
                transaction_id=tx,
            )

            self.saldo_esperado -= monto

    @invariant()
    def saldo_coincide_con_esperado(self):
        balance = LedgerEntry.get_user_balance(self.usuario)
        assert balance == self.saldo_esperado, (
            f"Saldo real {balance} != saldo esperado {self.saldo_esperado}"
        )

    @invariant()
    def sistema_suma_cero(self):
        total = LedgerEntry.get_system_zero_invariant()
        assert total == Decimal('0.0000'), (
            f"El invariante del sistema se rompió: {total}"
        )

    @invariant()
    def saldo_no_negativo(self):
        balance = LedgerEntry.get_user_balance(self.usuario)
        assert balance >= Decimal('0.0000'), (
            f"El saldo del usuario es negativo: {balance}"
        )


# ============================================================
# Tests de Endpoints de la API (HTTP)
# ============================================================

class TestDepositoEndpoint(APITestCase):
    """Tests de integración para POST /api/v1/wallet/deposit/."""

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='deposito_test',
            email='deposito@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418596',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )
        from wallet.models import UserBonus
        UserBonus.objects.create(
            user=self.usuario,
            bonus_amount=Decimal('0.0000'),
            required_turnover=Decimal('0.0000'),
            is_active=False
        )
        self.client.force_authenticate(user=self.usuario)
        self.url = reverse('api-wallet-deposit')

    def test_deposito_exitoso_retorna_201(self):
        """Un depósito válido debe retornar HTTP 201."""
        respuesta = self.client.post(self.url, {'amount': '500.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertIn('nuevo_balance', respuesta.data)

    def test_deposito_incrementa_balance(self):
        """Después de un depósito, el balance debe ser igual al monto."""
        self.client.post(self.url, {'amount': '500.0000'}, format='json')
        respuesta = self.client.get(reverse('api-wallet-balance'))
        self.assertEqual(respuesta.data['balance'], '500.0000')

    def test_deposito_monto_cero_retorna_400(self):
        """Un depósito con monto 0 debe retornar HTTP 400."""
        respuesta = self.client.post(self.url, {'amount': '0.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deposito_monto_negativo_retorna_400(self):
        """Un depósito con monto negativo debe retornar HTTP 400."""
        respuesta = self.client.post(self.url, {'amount': '-100.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deposito_sin_autenticacion_retorna_403(self):
        """Un usuario no autenticado debe recibir HTTP 403."""
        self.client.force_authenticate(user=None)
        respuesta = self.client.post(self.url, {'amount': '100.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)


class TestRetiroEndpoint(APITestCase):
    """Tests de integración para POST /api/v1/wallet/withdraw/."""

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='withdraw_test',
            email='withdraw@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418597',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )
        self.client.force_authenticate(user=self.usuario)
        self.url = reverse('api-wallet-withdraw')

        # Depositar saldo inicial para las pruebas de retiro
        from uuid import uuid4
        tx = uuid4()
        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=SALDO_INICIAL,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=SALDO_INICIAL,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
        )

    def test_retiro_exitoso_retorna_200(self):
        """Un retiro válido debe retornar HTTP 200."""
        respuesta = self.client.post(self.url, {'amount': '100.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_retiro_saldo_insuficiente_retorna_409(self):
        """Un retiro mayor al saldo debe retornar HTTP 409 Conflict."""
        respuesta = self.client.post(
            self.url, {'amount': '999999.0000'}, format='json'
        )
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)

    def test_retiro_decrementa_balance(self):
        """Después de un retiro, el balance debe disminuir."""
        self.client.post(self.url, {'amount': '100.0000'}, format='json')
        respuesta = self.client.get(reverse('api-wallet-balance'))
        self.assertEqual(respuesta.data['balance'], '900.0000')

    def test_retiro_monto_cero_retorna_400(self):
        """Un retiro con monto 0 debe retornar HTTP 400."""
        respuesta = self.client.post(self.url, {'amount': '0.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)


class TestBalanceEndpoint(APITestCase):
    """Tests de integración para GET /api/v1/wallet/balance/."""

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='balance_test',
            email='balance@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418598',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )
        self.client.force_authenticate(user=self.usuario)
        self.url = reverse('api-wallet-balance')

    def test_balance_retorna_200(self):
        """La consulta de balance debe retornar HTTP 200."""
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_balance_inicial_es_cero(self):
        """El balance inicial de un usuario nuevo debe ser 0.0000."""
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.data['balance'], '0.0000')

    def test_balance_incluye_username(self):
        """La respuesta de balance debe incluir el nombre del usuario."""
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.data['username'], 'balance_test')


# ============================================================
# Tests de Concurrencia
# ============================================================

class TestConcurrenciaRetiro(TestCase):
    """
    Tests de concurrencia para verificar que select_for_update
    previene el doble gasto.

    Simula múltiples retiros simultáneos con saldo justo para 1 sola operación.
    """

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='concurrencia_test',
            email='concurrencia@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418599',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )

        from uuid import uuid4
        tx = uuid4()
        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=SALDO_INICIAL,
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=SALDO_INICIAL,
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
        )

    def test_saldo_final_nunca_negativo_con_multiples_retiros(self):
        """
        Realiza múltiples retiros secuencialmente pero con saldo justo.
        Verifica que el saldo nunca sea negativo.
        """
        from uuid import uuid4
        import threading

        resultados = []
        barrier = threading.Barrier(5)

        def intentar_retiro():
            from django.db import transaction
            monto = Decimal('300.0000')
            tx = uuid4()

            try:
                with transaction.atomic():
                    user = User.objects.select_for_update().get(pk=self.usuario.pk)
                    balance = LedgerEntry.get_user_balance(user)

                    if balance >= monto:
                        LedgerEntry.objects.create(
                            user=user,
                            account=LedgerEntry.Account.WALLET_USUARIO,
                            amount=monto,
                            direction=LedgerEntry.Direction.DEBIT,
                            transaction_id=tx,
                        )
                        LedgerEntry.objects.create(
                            user=None,
                            account=LedgerEntry.Account.CASA,
                            amount=monto,
                            direction=LedgerEntry.Direction.CREDIT,
                            transaction_id=tx,
                        )
                        resultados.append('exitoso')
                    else:
                        resultados.append('fallo_saldo')
            except Exception:
                resultados.append('error')

        hilos = []
        for _ in range(5):
            t = threading.Thread(target=intentar_retiro)
            hilos.append(t)
            t.start()

        for t in hilos:
            t.join()

        balance_final = LedgerEntry.get_user_balance(self.usuario)
        self.assertGreaterEqual(balance_final, Decimal('0.0000'))


# ============================================================
# Tests de Transferencia Interna
# ============================================================

class TestTransferenciaEndpoint(APITestCase):
    """Tests de integración para POST /api/v1/wallet/transfer/."""

    def setUp(self):
        self.sender = User.objects.create_user(
            username='sender_user',
            email='sender@fairbet.pe',
            password='Password123!'
        )
        self.receiver = User.objects.create_user(
            username='receiver_user',
            email='receiver@fairbet.pe',
            password='Password123!'
        )

        from users.models import UserProfile
        from datetime import date
        self.sender_profile = UserProfile.objects.create(
            user=self.sender,
            dni='12345671',
            birth_date=date(1995, 1, 1),
            verification_status=UserProfile.STATUS_VERIFIED
        )
        self.receiver_profile = UserProfile.objects.create(
            user=self.receiver,
            dni='12345672',
            birth_date=date(1995, 1, 1),
            verification_status=UserProfile.STATUS_VERIFIED
        )

        self.client.force_authenticate(user=self.sender)
        self.url = reverse('api-wallet-transfer')

        # Depositar saldo inicial al sender
        from uuid import uuid4
        tx = uuid4()
        LedgerEntry.objects.create(
            user=self.sender,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal('500.0000'),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=tx,
            description='Deposito inicial'
        )
        LedgerEntry.objects.create(
            user=None,
            account=LedgerEntry.Account.CASA,
            amount=Decimal('500.0000'),
            direction=LedgerEntry.Direction.DEBIT,
            transaction_id=tx,
            description='Financiamiento de prueba'
        )

    def test_transferencia_exitosa(self):
        """Una transferencia válida debe decrementar el sender y sumar al receiver."""
        from uuid import uuid4
        headers = {'HTTP_IDEMPOTENCY_KEY': str(uuid4())}
        payload = {
            'to_username': 'receiver_user',
            'amount': '200.0000',
            'description': 'Regalo de cumpleaños'
        }

        respuesta = self.client.post(self.url, payload, format='json', **headers)
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data['nuevo_balance'], '300.0000')

        # Verificar balances
        self.assertEqual(LedgerEntry.get_user_balance(self.sender), Decimal('300.0000'))
        self.assertEqual(LedgerEntry.get_user_balance(self.receiver), Decimal('200.0000'))

        # Verificar sistema invariant = 0
        self.assertEqual(LedgerEntry.get_system_zero_invariant(), Decimal('0.0000'))

    def test_transferencia_saldo_insuficiente(self):
        """Una transferencia mayor al saldo del sender debe fallar con HTTP 409."""
        from uuid import uuid4
        headers = {'HTTP_IDEMPOTENCY_KEY': str(uuid4())}
        payload = {
            'to_username': 'receiver_user',
            'amount': '1000.0000'
        }

        respuesta = self.client.post(self.url, payload, format='json', **headers)
        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('error', respuesta.data)

    def test_transferencia_a_uno_mismo(self):
        """Un usuario no puede transferirse a sí mismo."""
        from uuid import uuid4
        headers = {'HTTP_IDEMPOTENCY_KEY': str(uuid4())}
        payload = {
            'to_username': 'sender_user',
            'amount': '100.0000'
        }

        respuesta = self.client.post(self.url, payload, format='json', **headers)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('to_username', respuesta.data)

    def test_transferencia_destinatario_inexistente(self):
        """Un destinatario que no existe debe dar HTTP 400."""
        from uuid import uuid4
        headers = {'HTTP_IDEMPOTENCY_KEY': str(uuid4())}
        payload = {
            'to_username': 'no_existe',
            'amount': '100.0000'
        }

        respuesta = self.client.post(self.url, payload, format='json', **headers)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('to_username', respuesta.data)

    def test_transferencia_sender_autoexcluido(self):
        """Un remitente autoexcluido no puede transferir."""
        from responsible.models import AutoExclusion
        from django.utils import timezone
        AutoExclusion.objects.create(
            user=self.sender,
            excluded_until=timezone.now() + timezone.timedelta(days=7)
        )

        from uuid import uuid4
        headers = {'HTTP_IDEMPOTENCY_KEY': str(uuid4())}
        payload = {
            'to_username': 'receiver_user',
            'amount': '100.0000'
        }

        respuesta = self.client.post(self.url, payload, format='json', **headers)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', respuesta.data)

    def test_transferencia_receiver_autoexcluido(self):
        """No se puede transferir a un destinatario autoexcluido."""
        from responsible.models import AutoExclusion
        from django.utils import timezone
        AutoExclusion.objects.create(
            user=self.receiver,
            excluded_until=timezone.now() + timezone.timedelta(days=7)
        )

        from uuid import uuid4
        headers = {'HTTP_IDEMPOTENCY_KEY': str(uuid4())}
        payload = {
            'to_username': 'receiver_user',
            'amount': '100.0000'
        }

        respuesta = self.client.post(self.url, payload, format='json', **headers)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('to_username', respuesta.data)

    def test_transferencia_idempotente(self):
        """Las peticiones duplicadas con la misma clave de idempotencia deben retornar la misma respuesta."""
        from uuid import uuid4
        key = str(uuid4())
        headers = {'HTTP_IDEMPOTENCY_KEY': key}
        payload = {
            'to_username': 'receiver_user',
            'amount': '100.0000'
        }

        # Primer envío
        r1 = self.client.post(self.url, payload, format='json', **headers)
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

        # Segundo envío
        r2 = self.client.post(self.url, payload, format='json', **headers)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r1.data['transaction_id'], r2.data['transaction_id'])


class TestBonoBienvenidaYRollover(APITestCase):
    """
    Suite de pruebas para validar el Bono de Bienvenida (100% hasta S/ 500),
    la restricción de retiros con rollover pendiente, y la acumulación
    correcta del rollover según la cuota de la apuesta colocada.
    """

    def setUp(self):
        # Crear usuario para las pruebas de bonos
        self.usuario = User.objects.create_user(
            username='bonus_user',
            email='bonus_user@fairbet.pe',
            password='Password123!'
        )
        from users.models import UserProfile
        from datetime import date
        UserProfile.objects.get_or_create(
            user=self.usuario,
            defaults={
                'dni': '72418598',
                'birth_date': date(1995, 1, 1),
                'verification_status': UserProfile.STATUS_VERIFIED
            }
        )
        self.client.force_authenticate(user=self.usuario)

        # Crear catálogo deportivo mínimo para poder colocar apuestas
        from django.utils import timezone
        from betting.models import League, Team, Event, Market, Selection
        self.league = League.objects.create(api_id=40, name="Premier League", country="Inglaterra")
        self.home_team = Team.objects.create(api_id=3, name="Arsenal")
        self.away_team = Team.objects.create(api_id=4, name="Chelsea")
        self.event = Event.objects.create(
            api_id=101,
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            starts_at=timezone.now() + timezone.timedelta(days=1),
            status='scheduled'
        )
        self.market = Market.objects.create(event=self.event, name="1X2")
        # Selección elegible (cuota >= 1.50)
        self.sel_high = Selection.objects.create(market=self.market, name="Local", odds=Decimal("1.8000"))
        # Selección no elegible para rollover (cuota < 1.50)
        self.sel_low = Selection.objects.create(market=self.market, name="Empate", odds=Decimal("1.2000"))

    def test_primer_deposito_otorga_bono_bienvenida(self):
        """El primer depósito otorga un bono del 100% hasta S/ 500 y crea el UserBonus con rollover de 6x."""
        url_deposit = reverse('api-wallet-deposit')
        # Hacemos una recarga de 300
        respuesta = self.client.post(url_deposit, {'amount': '300.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        
        # Debe recibir 300 en efectivo + 300 de bono = 600 de balance
        self.assertEqual(Decimal(respuesta.data['nuevo_balance']), Decimal('600.0000'))
        self.assertIn('bono_bienvenida', respuesta.data)
        self.assertEqual(Decimal(respuesta.data['bono_bienvenida']['bono_otorgado']), Decimal('300.0000'))
        self.assertEqual(Decimal(respuesta.data['bono_bienvenida']['rollover_requerido']), Decimal('1800.0000')) # 300 * 6

        # Verificar en base de datos
        from wallet.models import UserBonus
        bono = UserBonus.objects.get(user=self.usuario)
        self.assertTrue(bono.is_active)
        self.assertEqual(bono.bonus_amount, Decimal('300.0000'))
        self.assertEqual(bono.required_turnover, Decimal('1800.0000'))
        self.assertEqual(bono.current_turnover, Decimal('0.0000'))
        self.assertEqual(bono.remaining_rollover, Decimal('1800.0000'))

    def test_bloqueo_de_retiros_con_rollover_activo(self):
        """Intentar retirar fondos teniendo un bono activo con rollover pendiente debe fallar con HTTP 400."""
        # 1. Realizar primer depósito para activar bono
        url_deposit = reverse('api-wallet-deposit')
        self.client.post(url_deposit, {'amount': '100.0000'}, format='json')

        # 2. Intentar retirar
        url_withdraw = reverse('api-wallet-withdraw')
        respuesta = self.client.post(url_withdraw, {'amount': '50.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', respuesta.data)
        self.assertIn('rollover pendiente', respuesta.data['error'])

    def test_acumulacion_de_rollover_y_liberacion(self):
        """Colocar apuestas elegibles acumula rollover. Al cumplir la meta, el bono se desactiva y se puede retirar."""
        # 1. Activar bono con depósito de 100 (Rollover requerido = 600)
        url_deposit = reverse('api-wallet-deposit')
        self.client.post(url_deposit, {'amount': '100.0000'}, format='json')
        
        from wallet.models import UserBonus
        bono = UserBonus.objects.get(user=self.usuario)
        self.assertEqual(bono.required_turnover, Decimal('600.0000'))

        # 2. Colocar apuesta con cuota baja (odds = 1.20). No debe acumular rollover
        from uuid import uuid4
        self.client.post(
            '/api/v1/betting/bets/',
            {
                "selections": [{"selection_id": self.sel_low.id, "expected_odds": "1.2000"}],
                "stake": "50.0000"
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )
        bono.refresh_from_db()
        self.assertEqual(bono.current_turnover, Decimal('0.0000')) # No acumuló por cuota baja

        # 3. Colocar apuesta con cuota elegible (odds = 1.80). Debe acumular rollover
        # Recargamos más fichas manualmente primero para evitar saldo insuficiente (409 Conflict)
        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal('500.0000'),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=uuid4(),
            description="Recarga manual previa"
        )
        self.client.post(
            '/api/v1/betting/bets/',
            {
                "selections": [{"selection_id": self.sel_high.id, "expected_odds": "1.8000"}],
                "stake": "200.0000"
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )
        bono.refresh_from_db()
        self.assertEqual(bono.current_turnover, Decimal('200.0000'))
        self.assertTrue(bono.is_active)

        # 4. Colocar apuesta elegible por el resto del rollover (S/ 400)
        # Recargamos fichas para tener saldo suficiente (el bono ya existe, no se otorga otro bono)
        LedgerEntry.objects.create(
            user=self.usuario,
            account=LedgerEntry.Account.WALLET_USUARIO,
            amount=Decimal('500.0000'),
            direction=LedgerEntry.Direction.CREDIT,
            transaction_id=uuid4(),
            description="Recarga manual"
        )
        
        self.client.post(
            '/api/v1/betting/bets/',
            {
                "selections": [{"selection_id": self.sel_high.id, "expected_odds": "1.8000"}],
                "stake": "400.0000"
            },
            format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid4())
        )
        bono.refresh_from_db()
        self.assertEqual(bono.current_turnover, Decimal('600.0000'))
        self.assertFalse(bono.is_active) # Bono liberado/completado

        # 5. Intentar retirar ahora (debe permitirlo)
        url_withdraw = reverse('api-wallet-withdraw')
        respuesta = self.client.post(url_withdraw, {'amount': '10.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)


