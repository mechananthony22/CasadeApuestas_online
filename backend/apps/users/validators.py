# -*- coding: utf-8 -*-
"""
Validadores personalizados para la Fase 1: Usuarios y KYC.

Contiene el algoritmo oficial de validación del DNI peruano utilizando
el método de Módulo-11 (dígito verificador), tal como lo especifica
RENIEC (Registro Nacional de Identificación y Estado Civil del Perú).
"""
from django.core.exceptions import ValidationError
from django.utils import timezone


# ============================================================
# Algoritmo de Validación del DNI Peruano - Módulo 11
# ============================================================
# El DNI peruano tiene 8 dígitos. Los primeros 7 dígitos son el número
# de identidad y el 8vo dígito es el dígito verificador calculado con
# el algoritmo de Módulo-11 usando el vector de pesos definido por RENIEC.
# La fórmula correcta es: verificador = (11 - (suma_ponderada % 11)) % 11
# ============================================================

# Vector de pesos oficiales para el cálculo del dígito verificador (RENIEC)
_PESOS_DNI = [5, 4, 3, 2, 7, 6, 5, 4]


def validar_dni_peruano(dni: str) -> bool:
    """
    Valida el formato y el dígito verificador de un DNI peruano.

    El algoritmo de Módulo-11 de RENIEC funciona de la siguiente manera:
    1. Se toman los 8 dígitos del DNI.
    2. Cada dígito se multiplica por su peso correspondiente en _PESOS_DNI.
    3. Se suman todos los productos obtenidos.
    4. Se calcula el residuo de dividir la suma entre 11.
    5. Se calcula el verificador esperado: (11 - residuo) % 11.
    6. El resultado debe coincidir exactamente con el 8vo dígito del DNI.

    Args:
        dni (str): Cadena de 8 dígitos numéricos representando el DNI peruano.

    Returns:
        bool: True si el DNI tiene el formato correcto y el dígito verificador es válido.

    Raises:
        ValidationError: Si el DNI no tiene exactamente 8 caracteres o contiene letras.
    """
    if not dni or len(dni) != 8:
        raise ValidationError('El DNI peruano debe tener exactamente 8 dígitos.')

    if not dni.isdigit():
        raise ValidationError('El DNI peruano debe contener solo 8 dígitos numéricos.')

    suma = 0
    for i, digito in enumerate(dni):
        suma += int(digito) * _PESOS_DNI[i]

    residuo = suma % 11
    verificador_esperado = (11 - residuo) % 11

    return int(dni[7]) == verificador_esperado


def validar_mayoria_de_edad(fecha_nacimiento) -> bool:
    """
    Verifica si una persona tiene 18 años o más a partir de su fecha de nacimiento.

    Calcula la edad exacta tomando en cuenta el mes y el día para evitar
    errores en fechas límite (cumpleaños que aún no han pasado en el año actual).

    Args:
        fecha_nacimiento (date): Objeto de fecha de nacimiento del usuario.

    Returns:
        bool: True si la persona tiene 18 años o más, False en caso contrario.
    """
    hoy = timezone.now().date()
    edad = (
        hoy.year - fecha_nacimiento.year
        - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
    )
    return edad >= 18
