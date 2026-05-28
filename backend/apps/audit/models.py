# -*- coding: utf-8 -*-
# Modelos de base de datos para la cadena inmutable de logs SHA-256 en FairBet Lab
import hashlib
import json
from django.db import models
from django.core.exceptions import ValidationError

class AuditLogEntry(models.Model):
    """
    Representa una entrada inmutable de auditoría regulada (Ley 31557 Art. 18).
    Implementa encadenamiento hash SHA-256 (Blockchain básico append-only)
    para impedir de forma absoluta cualquier manipulación o borrado de datos.
    """

    EVENT_WALLET_MOVEMENT = 'WALLET_MOVEMENT'
    EVENT_BET_STATUS_CHANGE = 'BET_STATUS_CHANGE'
    EVENT_ODDS_CHANGE = 'ODDS_CHANGE'
    EVENT_STATUS_CHANGE = 'EVENT_STATUS_CHANGE'
    MARKET_CREATION = 'MARKET_CREATION'
    SELECTION_CREATION = 'SELECTION_CREATION'

    EVENT_TYPE_CHOICES = [
        (EVENT_WALLET_MOVEMENT, 'Movimiento de Billetera'),
        (EVENT_BET_STATUS_CHANGE, 'Cambio de Estado de Apuesta'),
        (EVENT_ODDS_CHANGE, 'Variación de Cuotas'),
        (EVENT_STATUS_CHANGE, 'Cambio de Estado de Evento'),
        (MARKET_CREATION, 'Creación de Mercado'),
        (SELECTION_CREATION, 'Creación de Selección'),
    ]
    
    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPE_CHOICES,
        verbose_name='Tipo de Evento'
    )
    
    payload = models.JSONField(
        verbose_name='Detalles del Evento (JSON)'
    )
    
    previous_hash = models.CharField(
        max_length=64,
        verbose_name='Hash del Registro Anterior',
        db_index=True
    )
    
    current_hash = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Hash del Registro Actual',
        db_index=True
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Registro'
    )

    class Meta:
        verbose_name = 'Registro de Auditoría'
        verbose_name_plural = 'Registros de Auditoría'
        ordering = ['id']

    def __str__(self):
        return f"Log #{self.id} [{self.get_event_type_display()}] - Hash: {self.current_hash[:10]}..."

    def calculate_hash(self):
        """
        Calcula el hash del bloque actual encadenando el hash anterior.
        Si es el primer bloque de la cadena, utiliza un hash génesis.
        """
        # Buscar el último log registrado
        prev_entry = AuditLogEntry.objects.order_by('-id').first()
        prev_hash = prev_entry.current_hash if prev_entry else '0' * 64
        
        # Representación canónica del payload en formato JSON ordenado por claves
        canonical_payload = json.dumps(self.payload, sort_keys=True)
        
        # Generar hash SHA-256
        sha = hashlib.sha256()
        sha.update((prev_hash + canonical_payload).encode('utf-8'))
        
        return prev_hash, sha.hexdigest()

    def save(self, *args, **kwargs):
        """
        Garantiza la inmutabilidad de los registros.
        Solo se permiten inserciones (append-only), bloqueando cualquier actualización.
        """
        if self.pk is not None:
            raise ValidationError("Los registros de auditoría son inmutables y no pueden ser modificados.")
            
        # Calcular los hashes criptográficos antes de insertar
        prev_hash, curr_hash = self.calculate_hash()
        self.previous_hash = prev_hash
        self.current_hash = curr_hash
        
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Impide de forma absoluta la eliminación de logs históricos.
        """
        raise ValidationError("Los registros de auditoría son inmutables y no pueden ser eliminados.")
