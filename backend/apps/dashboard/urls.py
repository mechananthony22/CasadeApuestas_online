# -*- coding: utf-8 -*-
from django.urls import path
from dashboard.views import OperatorDashboardView, MinceturReportView
from dashboard.admin_views import (
    AdminMetricsAPIView,
    AdminMinceturCSVAPIView,
)

urlpatterns = [
    # === OPERATOR DASHBOARD API (IsAdminUser) ===
    path('dashboard/metrics/', OperatorDashboardView.as_view(), name='operator-dashboard-metrics'),
    path('dashboard/mincetur-report/', MinceturReportView.as_view(), name='operator-mincetur-report'),

    # === ADMIN API ENDPOINTS (IsAdminUser) ===
    path('admin/metrics/', AdminMetricsAPIView.as_view(), name='admin-metrics'),
    path('admin/mincetur-csv/', AdminMinceturCSVAPIView.as_view(), name='admin-mincetur-csv'),
]
