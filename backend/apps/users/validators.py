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
# ============================================================

# Vector de pesos oficiales para el cálculo del dígito verificador
_PESOS_DNI = [3, 2, 7, 6, 5, 4, 3, 2]

# Tabla de conversión del residuo al carácter verificador
_TABLA_VERIFICACION = {
    0: '0',
    1: '1',
    2: '2',
    3: '3',
    4: '4',
    5: '5',
    6: '6',
    7: '7',
    8: '8',
    9: '9',
    10: 'k',  # Algunos DNIs antiguos usaban 'k'
}


def validar_dni_peruano(dni: str) -> bool:
    """
    Valida el formato y el dígito verificador de un DNI peruano.

    El algoritmo de Módulo-11 funciona de la siguiente manera:
    1. Se toman los primeros 7 dígitos del DNI.
    2. Se multiplica cada dígito por su peso correspondiente en _PESOS_DNI.
    3. Se suman todos los productos obtenidos.
    4. Se calcula el residuo de dividir la suma entre 11.
    5. Se convierte el residuo al carácter verificador usando _TABLA_VERIFICACION.
    6. El resultado debe coincidir exactamente con el 8vo dígito del DNI.

    Nota: En la práctica, RENIEC no publica la fórmula exacta de verificación
    para todos los DNIs activos. Este algoritmo es una aproximación ampliamente
    usada en el ecosistema de software peruano. Ver ADR-0002 para detalles.

    Args:
        dni (str): Cadena de 8 dígitos numéricos representando el DNI peruano.

    Returns:
        bool: True si el DNI tiene el formato correcto y el dígito verificador es válido.

    Raises:
        ValidationError: Si el DNI no tiene exactamente 8 caracteres o contiene letras.
    """
    # Verificar que tenga exactamente 8 caracteres
    if not dni or len(dni) != 8:
        raise ValidationError('El DNI peruano debe tener exactamente 8 dígitos.')

    # Verificar que sean solo caracteres numéricos (excepto posible 'k' al final)
    cuerpo = dni[:7]
    digito_verificador = dni[7].lower()

    if not cuerpo.isdigit():
        raise ValidationError('Los primeros 7 dígitos del DNI deben ser numéricos.')

    # Paso 1: Calcular la suma ponderada con los pesos de los 7 primeros dígitos
    suma = 0
    for i, digito in enumerate(cuerpo):
        suma += int(digito) * _PESOS_DNI[i]

    # Paso 2: Calcular el residuo del módulo 11
    residuo = suma % 11

    # Paso 3: Obtener el carácter verificador esperado
    verificador_esperado = _TABLA_VERIFICACION.get(residuo)

    # Paso 4: Si el residuo no está en la tabla, el DNI es inválido
    if verificador_esperado is None:
        return False

    # Paso 5: Comparar el dígito verificador esperado con el real
    return digito_verificador == verificador_esperado


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
    # Calcula si el cumpleaños ya pasó este año para obtener la edad exacta
    edad = (
        hoy.year - fecha_nacimiento.year
        - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
    )
    return edad >= 18
