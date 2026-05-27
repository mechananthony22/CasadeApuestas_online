# -*- coding: utf-8 -*-
# Serializadores de Django REST Framework para la detección de fraude en FairBet Lab
from rest_framework import serializers
from django.contrib.auth.models import User
from fraud.models import SuspiciousActivity

class SuspiciousActivitySerializer(serializers.ModelSerializer):
    """
    Serializador para ver y actualizar alertas de comportamiento sospechoso.
    El campo status es el único editable por el operador administrativo.
    """
    
    username = serializers.CharField(source='user.username', read_only=True)
    activity_type_display = serializers.CharField(source='get_activity_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    resolved_by_username = serializers.CharField(source='resolved_by.username', read_only=True)

    class Meta:
        model = SuspiciousActivity
        fields = [
            'id', 'username', 'activity_type', 'activity_type_display',
            'description', 'payload', 'severity', 'severity_display',
            'status', 'status_display', 'created_at', 'resolved_at',
            'resolved_by_username'
        ]
        read_only_fields = [
            'id', 'username', 'activity_type', 'activity_type_display',
            'description', 'payload', 'severity', 'severity_display',
            'created_at', 'resolved_at', 'resolved_by_username'
        ]
