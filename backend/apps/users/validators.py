# -*- coding: utf-8 -*-
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
    hoy = timezone.now().date()
    edad = (
        hoy.year - fecha_nacimiento.year
        - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
    )
    return edad >= 18
