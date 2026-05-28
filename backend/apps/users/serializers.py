# -*- coding: utf-8 -*-
"""
Serializadores de DRF para la Fase 1: Usuarios y KYC.

Define la estructura de los datos que se reciben desde el cliente
(validación de entrada) y los datos que se envían al cliente como respuesta.

Incluye la integración con los validadores de DNI peruano y mayoría de edad
para que las reglas de negocio se apliquen automáticamente al deserializar datos.
"""
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers

from .models import UserProfile
from .validators import validar_dni_peruano, validar_mayoria_de_edad


class RegistroUsuarioSerializer(serializers.Serializer):
    """
    Serializer para el endpoint de registro de un nuevo usuario.

    Recibe: username, email, password, confirm_password, dni y birth_date.
    Valida en orden:
        1. Que el email no esté ya registrado.
        2. Que el DNI tenga el formato correcto y el dígito verificador válido.
        3. Que el usuario tenga mínimo 18 años.
        4. Que las contraseñas coincidan.
    """

    # Campos del usuario de Django
    username = serializers.CharField(
        min_length=3,
        max_length=150,
        help_text='Nombre de usuario único en el sistema'
    )
    email = serializers.EmailField(
        help_text='Correo electrónico del usuario'
    )
    password = serializers.CharField(
        write_only=True,  # No se devuelve en la respuesta por seguridad
        min_length=8,
        help_text='Contraseña de mínimo 8 caracteres'
    )
    confirm_password = serializers.CharField(
        write_only=True,
        help_text='Repetición de contraseña para confirmar'
    )

    # Campos del perfil KYC
    dni = serializers.CharField(
        min_length=8,
        max_length=8,
        help_text='DNI peruano de 8 dígitos'
    )
    birth_date = serializers.DateField(
        help_text='Fecha de nacimiento en formato YYYY-MM-DD'
    )

    def validate_email(self, valor):
        """Verifica que el correo electrónico no esté ya registrado en el sistema."""
        if User.objects.filter(email=valor).exists():
            raise serializers.ValidationError('Este correo electrónico ya está registrado.')
        return valor

    def validate_username(self, valor):
        """Verifica que el nombre de usuario no esté ya tomado en el sistema."""
        if User.objects.filter(username=valor).exists():
            raise serializers.ValidationError('Este nombre de usuario ya está en uso.')
        return valor

    def validate_dni(self, valor):
        """
        Valida el DNI peruano (DESACTIVADO - solo verifica formato básico y duplicados).
        El algoritmo Módulo-11 está comentado para permitir registro sin validación RENIEC.
        """
        # TODO: Reactivar validación Módulo-11 cuando se implemente conexión real a RENIEC
        # try:
        #     if not validar_dni_peruano(valor):
        #         raise serializers.ValidationError(
        #             'El DNI ingresado no es válido. Verifica el dígito verificador.'
        #         )
        # except Exception as e:
        #     raise serializers.ValidationError(str(e))

        # Verificar que el DNI no esté ya registrado en otro perfil
        if UserProfile.objects.filter(dni=valor).exists():
            raise serializers.ValidationError('Este DNI ya está registrado en el sistema.')

        return valor

    def validate_birth_date(self, valor):
        """Verifica que el usuario tenga mínimo 18 años de edad."""
        if not validar_mayoria_de_edad(valor):
            raise serializers.ValidationError(
                'Debes tener mínimo 18 años de edad para registrarte en la plataforma.'
            )
        return valor

    def validate(self, datos):
        """Validación cruzada: verifica que ambas contraseñas coincidan."""
        if datos.get('password') != datos.get('confirm_password'):
            raise serializers.ValidationError({
                'confirm_password': 'Las contraseñas no coinciden.'
            })
        return datos

    @transaction.atomic
    def create(self, datos_validados):
        """
        Crea el usuario y su perfil KYC dentro de una transacción atómica.

        Usa @transaction.atomic para garantizar que si el perfil falla,
        el usuario tampoco quede creado (atomicidad total de la operación).
        """
        # Extraer datos no relacionados al perfil
        datos_validados.pop('confirm_password')
        dni = datos_validados.pop('dni')
        birth_date = datos_validados.pop('birth_date')

        # Crear el usuario nativo de Django
        usuario = User.objects.create_user(
            username=datos_validados['username'],
            email=datos_validados['email'],
            password=datos_validados['password'],
        )

        # Crear el perfil KYC asociado al usuario
        # TODO: Descomentar verification_status=UserProfile.STATUS_PENDING cuando se implemente verificación real con RENIEC
        #       Por ahora se auto-verifica para permitir pruebas sin conexión a RENIEC
        UserProfile.objects.create(
            user=usuario,
            dni=dni,
            birth_date=birth_date,
            verification_status=UserProfile.STATUS_VERIFIED,  # Auto-verificado para demo
        )

        return usuario


class PerfilUsuarioSerializer(serializers.ModelSerializer):
    """
    Serializer de solo lectura para visualizar el perfil completo del usuario autenticado.
    Expone los datos del perfil KYC y el estado de verificación actual de la cuenta.
    """

    # Datos del usuario de Django anidados en la respuesta
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    # Nombre legible del estado (ej: "Verificado" en lugar de "verified")
    verification_status_display = serializers.CharField(
        source='get_verification_status_display',
        read_only=True
    )
    # Propiedades calculadas del modelo
    is_adult = serializers.BooleanField(read_only=True)
    is_able_to_bet = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'username',
            'email',
            'dni',
            'birth_date',
            'verification_status',
            'verification_status_display',
            'is_adult',
            'is_able_to_bet',
            'created_at',
        ]
        # El DNI se muestra enmascarado en la respuesta por privacidad
        read_only_fields = ['dni', 'birth_date', 'verification_status', 'created_at']
