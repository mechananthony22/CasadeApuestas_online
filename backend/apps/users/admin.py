# -*- coding: utf-8 -*-
from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Configuración del panel de administración para los perfiles KYC."""

    # Columnas visibles en la lista de perfiles
    list_display = ['user', 'dni', 'birth_date', 'verification_status', 'created_at']

    # Filtros en el panel lateral derecho del admin
    list_filter = ['verification_status']

    # Campo de búsqueda por username, email y DNI
    search_fields = ['user__username', 'user__email', 'dni']

    # Campos que no se pueden modificar desde el admin (solo lectura)
    readonly_fields = ['created_at', 'updated_at', 'dni', 'birth_date']

    # Acción rápida para verificar masivamente desde el admin
    actions = ['marcar_como_verificado', 'marcar_como_bloqueado']

    def marcar_como_verificado(self, request, queryset):
        """Acción de admin: cambia el estado de usuarios seleccionados a 'verificado'."""
        actualizados = queryset.update(verification_status=UserProfile.STATUS_VERIFIED)
        self.message_user(request, f'{actualizados} perfil(es) marcado(s) como verificado(s).')
    marcar_como_verificado.short_description = 'Marcar como Verificado'

    def marcar_como_bloqueado(self, request, queryset):
        """Acción de admin: bloquea masivamente los perfiles seleccionados."""
        actualizados = queryset.update(verification_status=UserProfile.STATUS_BLOCKED)
        self.message_user(request, f'{actualizados} perfil(es) bloqueado(s).')
    marcar_como_bloqueado.short_description = 'Bloquear Cuentas Seleccionadas'
