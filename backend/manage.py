#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Utilidad de línea de comandos de Django para tareas administrativas."""
import os
import sys


def main():
    """Ejecuta tareas administrativas del proyecto Django."""
    # Cargar variables de entorno desde el archivo .env si existe
    from pathlib import Path
    try:
        from dotenv import load_dotenv
        # Buscar .env en la raíz del proyecto (un nivel arriba de manage.py) o en la carpeta actual
        env_path = Path(__file__).resolve().parent.parent / '.env'
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
        else:
            env_path_direct = Path(__file__).resolve().parent / '.env'
            if env_path_direct.exists():
                load_dotenv(dotenv_path=env_path_direct)
    except ImportError:
        pass

    # Configura por defecto el archivo de settings de desarrollo
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. ¿Estás seguro de que está instalado y "
            "disponible en tu variable de entorno PYTHONPATH? ¿Olvidaste "
            "activar tu entorno virtual?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()

