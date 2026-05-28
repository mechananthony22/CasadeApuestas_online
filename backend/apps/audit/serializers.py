# -*- coding: utf-8 -*-
from rest_framework import serializers
from .models import AuditLogEntry


class AuditLogEntrySerializer(serializers.ModelSerializer):
    """
    Serializer para exponer los registros de auditoría vía API.
    Solo lectura (read-only) ya que los registros son inmutables.
    """

    event_type_display = serializers.CharField(
        source='get_event_type_display',
        read_only=True
    )

    class Meta:
        model = AuditLogEntry
        fields = [
            'id',
            'event_type',
            'event_type_display',
            'payload',
            'previous_hash',
            'current_hash',
            'created_at',
        ]
        read_only_fields = fields