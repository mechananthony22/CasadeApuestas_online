# -*- coding: utf-8 -*-
"""
Tareas de Celery para la aplicación responsible en FairBet Lab.

Contiene las tareas en segundo plano periódicas para procesar límites expirados.
"""
import logging
from celery import shared_task
from django.utils import timezone
from django.db.models import Q
from responsible.models import ResponsibleGamingLimit

logger = logging.getLogger(__name__)

@shared_task(name='responsible.tasks.apply_expired_limits')
def apply_expired_limits():
    """
    Tarea periódica para consolidar límites preventivos pendientes.
    Filtra los perfiles cuyos cooldowns de 24 horas para aumento o desactivación
    hayan vencido y los aplica como límites activos.
    """
    logger.info("Iniciando barrido de límites pendientes de juego responsable...")
    now = timezone.now()
    
    # Obtener perfiles que tengan al menos un cooldown que ya expiró
    query = (
        Q(cooldown_until_daily__lte=now) |
        Q(cooldown_until_weekly__lte=now) |
        Q(cooldown_until_monthly__lte=now)
    )
    
    perfiles = ResponsibleGamingLimit.objects.filter(query)
    count = perfiles.count()
    
    if count > 0:
        logger.info(f"Se encontraron {count} perfiles con límites de cooldown expirados. Procesando...")
        for perfil in perfiles:
            # clean_expired_cooldowns se encarga de guardar el modelo si hay cambios
            perfil.clean_expired_cooldowns()
        logger.info(f"Barrido completado exitosamente. Se aplicaron cambios en {count} perfiles.")
    else:
        logger.info("No se encontraron límites con cooldowns expirados para procesar.")
        
    return count
