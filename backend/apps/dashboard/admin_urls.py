# -*- coding: utf-8 -*-
from django.urls import path
from django.contrib.auth.views import LoginView
from dashboard.admin_views import (
    AdminDashboardView,
    AdminMinceturView,
    AdminLogoutView,
)
from dashboard.admin_login import admin_login_api

urlpatterns = [
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('mincetur/', AdminMinceturView.as_view(), name='admin-mincetur'),
    path('login/', LoginView.as_view(
        template_name='admin/login.html',
        redirect_authenticated_user=True,
        next_page='/admin/dashboard/'
    ), name='admin-login'),
    path('logout/', AdminLogoutView.as_view(), name='admin-logout'),
    path('api/login/', admin_login_api, name='admin-api-login'),
]