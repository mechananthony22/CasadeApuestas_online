# -*- coding: utf-8 -*-
from django.urls import path
from .views import DepositoView, RetiroView, BalanceView, HistorialView

# Se prefija con 'api/v1/' desde config/urls.py
urlpatterns = [
    # POST /api/v1/wallet/deposit/ → Recarga simulada de fichas
    path('wallet/deposit/', DepositoView.as_view(), name='wallet-deposit'),

    # POST /api/v1/wallet/withdraw/ → Retiro simulado de fichas
    path('wallet/withdraw/', RetiroView.as_view(), name='wallet-withdraw'),

    # GET /api/v1/wallet/balance/ → Saldo calculado por SUM(credits) - SUM(debits)
    path('wallet/balance/', BalanceView.as_view(), name='wallet-balance'),

    # GET /api/v1/wallet/history/ → Historial de movimientos contables
    path('wallet/history/', HistorialView.as_view(), name='wallet-history'),
]
