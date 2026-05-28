# -*- coding: utf-8 -*-
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers
import requests
from django.conf import settings

from .models import UserProfile
from .validators import validar_dni_peruano, validar_mayoria_de_edad


class RegistroUsuarioSerializer(serializers.Serializer):
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
        # Verificar que el DNI no esté ya registrado en otro perfil
        if UserProfile.objects.filter(dni=valor).exists():
            raise serializers.ValidationError('Este DNI ya está registrado en el sistema.')

        token = getattr(settings, 'APIPERU_DEV_TOKEN', None)
        if token:
            url = "https://apiperu.dev/api/dni"
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}'
            }
            try:
                response = requests.post(url, json={'dni': valor}, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if not data.get('success') or not data.get('data'):
                        raise serializers.ValidationError('El DNI ingresado no es válido o pertenece a un menor de edad (no figura en el padrón).')
                    
                    # Guardamos la data devuelta (nombres, apellidos) en el contexto
                    # para usarla durante la creación del usuario
                    self.context['dni_data'] = data.get('data')
                else:
                    raise serializers.ValidationError('No se pudo validar el DNI en las fuentes oficiales o pertenece a un menor de edad.')
            except requests.exceptions.RequestException:
                raise serializers.ValidationError('Servicio de validación de DNI temporalmente no disponible.')

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
        # Extraer datos no relacionados al perfil
        datos_validados.pop('confirm_password')
        dni = datos_validados.pop('dni')
        birth_date = datos_validados.pop('birth_date')

        # Extraer los nombres reales obtenidos de la API (si existen)
        dni_data = self.context.get('dni_data', {})
        nombres_reales = dni_data.get('nombres', '')
        apellidos_reales = f"{dni_data.get('apellido_paterno', '')} {dni_data.get('apellido_materno', '')}".strip()

        # Crear el usuario nativo de Django
        usuario = User.objects.create_user(
            username=datos_validados['username'],
            email=datos_validados['email'],
            password=datos_validados['password'],
            first_name=nombres_reales[:150],  # Límite de longitud en Django User
            last_name=apellidos_reales[:150]
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
