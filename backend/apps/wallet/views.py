# -*- coding: utf-8 -*-
"""
Vistas de la API para la Fase 2: Wallet + Partida Doble.

REGLA DE ARQUITECTURA HÍBRIDA:
    Todas las operaciones que modifican el wallet van por HTTP síncrono.
    NUNCA se usa WebSocket para mover dinero.

REGLAS DE ORO:
    - NUNCA almacenar saldo en una columna (siempre calcular por SUM).
    - Cada transacción = mínimo 2 entries balanceadas (suma algebraica = 0).
    - select_for_update en TODA operación que modifica el wallet.
    - @transaction.atomic para garantizar atomicidad.
"""
from uuid import uuid4
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LedgerEntry
from .serializers import (
    DepositoSerializer,
    RetiroSerializer,
    BalanceSerializer,
    LedgerEntrySerializer,
)


class DepositoView(APIView):
    """
    POST /api/v1/wallet/deposit/

    Endpoint para recarga simulada de fichas virtuales.

    Flujo:
        1. Valida que el monto sea positivo.
        2. Crea dos entradas en LedgerEntry dentro de una transacción atómica:
           - CREDIT en wallet_usuario (entra dinero al usuario)
           - DEBIT en casa (sale dinero de la casa)
        3. Retorna el nuevo saldo del usuario.

    Respuestas:
        201 Created: Depósito exitoso, retorna el nuevo saldo.
        400 Bad Request: Monto inválido o datos incorrectos.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DepositoSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount = serializer.validated_data['amount']
        description = serializer.validated_data.get(
            'description', 'Recarga de fichas virtuales'
        )

        transaction_id = uuid4()

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)

            LedgerEntry.objects.create(
                user=user,
                account=LedgerEntry.Account.WALLET_USUARIO,
                amount=amount,
                direction=LedgerEntry.Direction.CREDIT,
                transaction_id=transaction_id,
                description=description,
            )

            LedgerEntry.objects.create(
                user=None,
                account=LedgerEntry.Account.CASA,
                amount=amount,
                direction=LedgerEntry.Direction.DEBIT,
                transaction_id=transaction_id,
                description=f'Recarga de {user.username}',
            )

        nuevo_balance = LedgerEntry.get_user_balance(user)

        return Response(
            {
                'mensaje': 'Depósito realizado exitosamente.',
                'transaction_id': str(transaction_id),
                'amount': str(amount),
                'nuevo_balance': str(nuevo_balance),
                'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.',
            },
            status=status.HTTP_201_CREATED,
        )


class RetiroView(APIView):
    """
    POST /api/v1/wallet/withdraw/

    Endpoint para retiro simulado de fichas virtuales.

    Flujo:
        1. Valida que el monto sea positivo.
        2. Verifica saldo suficiente (select_for_update).
        3. Crea dos entradas en LedgerEntry:
           - DEBIT en wallet_usuario (sale dinero del usuario)
           - CREDIT en casa (entra dinero a la casa)
        4. Retorna el nuevo saldo.

    Respuestas:
        200 OK: Retiro exitoso.
        400 Bad Request: Monto inválido.
        409 Conflict: Saldo insuficiente.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RetiroSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount = serializer.validated_data['amount']
        description = serializer.validated_data.get(
            'description', 'Retiro simulado de fichas'
        )

        transaction_id = uuid4()

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)

            balance_actual = LedgerEntry.get_user_balance(user)

            if balance_actual < amount:
                return Response(
                    {
                        'error': 'Saldo insuficiente para realizar el retiro.',
                        'balance_actual': str(balance_actual),
                        'monto_solicitado': str(amount),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            LedgerEntry.objects.create(
                user=user,
                account=LedgerEntry.Account.WALLET_USUARIO,
                amount=amount,
                direction=LedgerEntry.Direction.DEBIT,
                transaction_id=transaction_id,
                description=description,
            )

            LedgerEntry.objects.create(
                user=None,
                account=LedgerEntry.Account.CASA,
                amount=amount,
                direction=LedgerEntry.Direction.CREDIT,
                transaction_id=transaction_id,
                description=f'Retiro de {user.username}',
            )

        nuevo_balance = LedgerEntry.get_user_balance(user)

        return Response(
            {
                'mensaje': 'Retiro realizado exitosamente.',
                'transaction_id': str(transaction_id),
                'amount': str(amount),
                'nuevo_balance': str(nuevo_balance),
                'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.',
            },
            status=status.HTTP_200_OK,
        )


class BalanceView(APIView):
    """
    GET /api/v1/wallet/balance/

    Endpoint para consultar el saldo disponible del usuario autenticado.
    El saldo SIEMPRE se calcula mediante SUM(credits) - SUM(debits),
    NUNCA se lee de una columna almacenada.

    Respuestas:
        200 OK: Datos del balance y movimientos recientes.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        balance = LedgerEntry.get_user_balance(user)

        total_credits = LedgerEntry.objects.filter(
            user=user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            direction=LedgerEntry.Direction.CREDIT,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        total_debits = LedgerEntry.objects.filter(
            user=user,
            account=LedgerEntry.Account.WALLET_USUARIO,
            direction=LedgerEntry.Direction.DEBIT,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0000')

        movimientos = LedgerEntry.objects.filter(
            user=user,
            account=LedgerEntry.Account.WALLET_USUARIO,
        ).order_by('-created_at')[:10]

        movimientos_serializer = LedgerEntrySerializer(movimientos, many=True)

        return Response(
            {
                'username': user.username,
                'balance': str(balance),
                'total_depositado': str(total_credits),
                'total_retirado': str(total_debits),
                'ultimos_movimientos': movimientos_serializer.data,
                'disclaimer': 'Plataforma educativa con moneda virtual. No constituye una casa de apuestas.',
            },
            status=status.HTTP_200_OK,
        )


class HistorialView(APIView):
    """
    GET /api/v1/wallet/history/

    Endpoint para consultar el historial completo de movimientos
    del usuario autenticado en el libro contable.

    Respuestas:
        200 OK: Lista paginada de movimientos.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        movimientos = LedgerEntry.objects.filter(
            user=user,
        ).select_related('user').order_by('-created_at')

        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        start = (page - 1) * page_size
        end = start + page_size
        total = movimientos.count()

        serializer = LedgerEntrySerializer(
            movimientos[start:end], many=True
        )

        return Response(
            {
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size,
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )
