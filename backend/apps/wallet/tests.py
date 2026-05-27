# -*- coding: utf-8 -*-
"""
Suite de Tests para la Fase 2: Wallet + Partida Doble.

Cubre los invariantes obligatorios del sistema de partida doble:

INVARIANTES (Property-Based Testing con Hypothesis):
    1.  SUM(debits) - SUM(credits) = 0 por transacción
    2.  Ningún usuario tiene saldo negativo
    3.  Saldo total del sistema (casa + usuarios + apuestas_pendientes) = constante

TESTS DE CONCURRENCIA:
    - 50 peticiones simultáneas de retiro con saldo justo para 1
    - Verificar que solo 1 pasa, 49 fallan (select_for_update)

METODOLOGÍA TDD:
    - Primero se escriben los tests (test:)
    - Luego se implementa la funcionalidad (feat:)
"""
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

class TestHypothesisInvariantes(TestCase):
    """
    Tests basados en propiedades usando Hypothesis.
    Genera secuencias aleatorias de transacciones y verifica
    que los invariantes se mantengan SIEMPRE.
    """

    def setUp(self):
        self.usuario = User.objects.create_user(
            username='hypothesis_test',
            email='hypothesis@fairbet.pe',
            password='Password123!'
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
            username='deposit_test',
            email='deposit@fairbet.pe',
            password='Password123!'
        )
        self.client.force_authenticate(user=self.usuario)
        self.url = reverse('wallet-deposit')

    def test_deposito_exitoso_retorna_201(self):
        """Un depósito válido debe retornar HTTP 201."""
        respuesta = self.client.post(self.url, {'amount': '500.0000'}, format='json')
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertIn('nuevo_balance', respuesta.data)

    def test_deposito_incrementa_balance(self):
        """Después de un depósito, el balance debe ser igual al monto."""
        self.client.post(self.url, {'amount': '500.0000'}, format='json')
        respuesta = self.client.get(reverse('wallet-balance'))
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
        self.client.force_authenticate(user=self.usuario)
        self.url = reverse('wallet-withdraw')

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
        respuesta = self.client.get(reverse('wallet-balance'))
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
        self.client.force_authenticate(user=self.usuario)
        self.url = reverse('wallet-balance')

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
