from django.urls import path
from . import views

urlpatterns = [
    path('', views.DashboardPageView.as_view(), name='dashboard'),
    path('login/', views.LoginPageView.as_view(), name='login'),
    path('register/', views.RegisterPageView.as_view(), name='register'),
    path('events/', views.EventListView.as_view(), name='events-list'),
    path('events/<int:pk>/', views.EventDetailView.as_view(), name='events-detail'),
    path('bets/', views.BetListView.as_view(), name='bets-list'),
    path('wallet/', views.WalletBalanceView.as_view(), name='wallet-balance'),
    path('wallet/deposit/', views.WalletDepositView.as_view(), name='wallet-deposit'),
    path('responsible/limits/', views.ResponsibleLimitsView.as_view(), name='responsible-limits'),
    path('responsible/self-exclude/', views.ResponsibleSelfExcludeView.as_view(), name='responsible-self-exclude'),
]
