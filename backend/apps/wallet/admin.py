# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id',
        'user',
        'account',
        'direction',
        'amount',
        'description',
        'created_at',
    ]

    list_filter = ['account', 'direction', 'created_at']

    search_fields = [
        'user__username',
        'user__email',
        'transaction_id',
        'description',
    ]

    readonly_fields = [
        'transaction_id',
        'user',
        'account',
        'amount',
        'direction',
        'created_at',
    ]

    date_hierarchy = 'created_at'

    def has_delete_permission(self, request, obj=None):
        """
        Los registros contables NO se pueden eliminar desde el admin.
        La auditoría inmutable requiere que ninguna transacción sea borrada.
        """
        return False

    def has_change_permission(self, request, obj=None):
        """
        Los registros contables NO se pueden modificar desde el admin.
        Solo lectura para garantizar la integridad de la pista de auditoría.
        """
        if obj is not None:
            return False
        return True
