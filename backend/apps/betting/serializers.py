# -*- coding: utf-8 -*-
# Serializadores de Django REST Framework para la aplicación betting
from decimal import Decimal
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import serializers
from betting.models import League, Team, Event, Market, Selection, Bet, BetSelection
from users.models import UserProfile

class LeagueSerializer(serializers.ModelSerializer):
    """
    Serializador para el modelo League (Ligas deportivas).
    """
    class Meta:
        model = League
        fields = ['id', 'api_id', 'name', 'sport', 'country', 'logo_url']


class TeamSerializer(serializers.ModelSerializer):
    """
    Serializador para el modelo Team (Equipos de fútbol).
    """
    class Meta:
        model = Team
        fields = ['id', 'api_id', 'name', 'logo_url']


class SelectionSerializer(serializers.ModelSerializer):
    """
    Serializador para el modelo Selection (Opciones individuales con sus cuotas).
    """
    class Meta:
        model = Selection
        fields = ['id', 'name', 'odds', 'is_active']


class MarketSerializer(serializers.ModelSerializer):
    """
    Serializador para el modelo Market (Mercados de apuestas).
    Incluye las selecciones activas asociadas.
    """
    selections = serializers.SerializerMethodField()

    class Meta:
        model = Market
        fields = ['id', 'name', 'is_active', 'selections']

    def get_selections(self, obj):
        # Retornar únicamente selecciones activas para evitar confusión al apostador
        active_selections = obj.selections.filter(is_active=True)
        return SelectionSerializer(active_selections, many=True).data


class EventSerializer(serializers.ModelSerializer):
    """
    Serializador detallado para el modelo Event (Eventos deportivos).
    Incluye detalles de la liga, equipos local/visitante y los mercados activos.
    """
    league = LeagueSerializer(read_only=True)
    home_team = TeamSerializer(read_only=True)
    away_team = TeamSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    markets = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'api_id', 'league', 'home_team', 'away_team', 
            'starts_at', 'status', 'status_display', 'home_score', 
            'away_score', 'last_updated', 'markets'
        ]

    def get_markets(self, obj):
        # Retornar únicamente mercados que estén activos
        active_markets = obj.markets.filter(is_active=True)
        return MarketSerializer(active_markets, many=True).data


class BetSelectionPostSerializer(serializers.Serializer):
    """
    Serializador para las selecciones enviadas al colocar una apuesta.
    """
    selection_id = serializers.IntegerField(help_text="ID local de la selección elegida")
    expected_odds = serializers.DecimalField(
        max_digits=10, 
        decimal_places=4, 
        help_text="Cuota que el usuario vio y espera recibir (para validar re-cotización)"
    )


class BetSelectionDetailSerializer(serializers.ModelSerializer):
    """
    Serializador detallado de la relación intermedia BetSelection.
    """
    selection_name = serializers.CharField(source='selection.name', read_only=True)
    market_name = serializers.CharField(source='selection.market.name', read_only=True)
    event_display = serializers.SerializerMethodField()

    class Meta:
        model = BetSelection
        fields = ['id', 'selection', 'selection_name', 'market_name', 'event_display', 'odds_at_bet', 'status']

    def get_event_display(self, obj):
        event = obj.selection.market.event
        return f"{event.home_team.name} vs {event.away_team.name}"


from rest_framework.exceptions import APIException

class OddsChangedException(APIException):
    """
    Excepción personalizada para manejar cambios de cuota en vivo (re-cotización).
    Retorna automáticamente un estado HTTP 409 Conflict.
    """
    status_code = 409
    default_detail = 'Las cuotas de las selecciones han cambiado.'
    default_code = 'odds_changed'

    def __init__(self, cambios, detail=None, code=None):
        self.detail = {
            'code': 'odds_changed',
            'message': detail or self.default_detail,
            'cambios': cambios
        }


class BetSerializer(serializers.ModelSerializer):
    """
    Serializador para la visualización y colocación de boletos de apuestas (Bet).
    Garantiza la validación transaccional rigurosa y síncrona en base a las reglas del negocio.
    """
    selections = BetSelectionPostSerializer(many=True, write_only=True, help_text="Lista de selecciones que componen el boleto")
    selections_detail = BetSelectionDetailSerializer(source='selections', many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    event_name = serializers.SerializerMethodField(read_only=True)
    selection_name = serializers.SerializerMethodField(read_only=True)
    can_cashout = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Bet
        fields = [
            'id', 'username', 'status', 'status_display', 'type', 
            'type_display', 'stake', 'potential_payout', 'idempotency_key', 
            'created_at', 'settled_at', 'selections', 'selections_detail',
            'event_name', 'selection_name', 'can_cashout'
        ]
        read_only_fields = ['id', 'user', 'status', 'type', 'potential_payout', 'idempotency_key', 'created_at', 'settled_at']

    def get_event_name(self, obj):
        """
        Retorna el nombre descriptivo del evento o eventos del boleto.
        """
        selections = obj.selections.all()
        if not selections.exists():
            return "Sin eventos"
        if obj.type == 'simple':
            first = selections.first()
            event = first.selection.market.event
            return f"{event.home_team.name} vs {event.away_team.name}"
        else:
            return f"Combinada ({selections.count()} partidos)"

    def get_selection_name(self, obj):
        """
        Retorna la descripción de la selección o selecciones realizadas en el boleto.
        """
        selections = obj.selections.all()
        if not selections.exists():
            return ""
        if obj.type == 'simple':
            first = selections.first()
            return f"{first.selection.name} @ {first.odds_at_bet:.2f} ({first.selection.market.name})"
        else:
            parts = []
            for s in selections:
                parts.append(f"{s.selection.name} @ {s.odds_at_bet:.2f}")
            return " / ".join(parts)

    def get_can_cashout(self, obj):
        """
        Determina dinámicamente si la apuesta califica para cobro anticipado (Cash-out).
        """
        if obj.status != 'accepted':
            return False

        # El cash-out no está disponible si algún partido terminó, se suspendió o anuló
        for s in obj.selections.all():
            event = s.selection.market.event
            if event.status in ['finished', 'cancelled', 'suspended']:
                return False
            if not s.selection.is_active or not s.selection.market.is_active:
                return False

        return True

    def validate_stake(self, value):
        """
        Valida los montos mínimo y máximo permitidos por apuesta.
        """
        min_stake = Decimal('1.0000')
        max_stake = Decimal('10000.0000')
        if value < min_stake:
            raise serializers.ValidationError(f"El monto mínimo de apuesta es de {min_stake:.4f} fichas.")
        if value > max_stake:
            raise serializers.ValidationError(f"El monto máximo de apuesta es de {max_stake:.4f} fichas.")
        return value

    def validate(self, data):
        """
        Valida de forma síncrona todas las reglas de negocio de colocación del boleto.
        """
        user = self.context['request'].user
        selections_data = data.get('selections', [])

        # 1. Validar que contenga selecciones
        if not selections_data:
            raise serializers.ValidationError("Debe incluir al menos una selección para apostar.")

        # 2. Validar KYC del usuario (cuenta verificada)
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            raise serializers.ValidationError("El usuario no tiene un perfil KYC registrado.")

        # --- CONTROLES DE JUEGO RESPONSABLE ---
        from responsible.models import AutoExclusion
        try:
            auto_ex = user.auto_exclusion
            if auto_ex.is_active:
                raise serializers.ValidationError(
                    "No puedes realizar apuestas si te encuentras bajo un período de autoexclusión activa."
                )
            # Si la autoexclusión ya expiró pero el estado sigue siendo self_excluded, restaurarlo
            if not auto_ex.is_active and profile.verification_status == UserProfile.STATUS_SELF_EXCLUDED:
                profile.verification_status = UserProfile.STATUS_VERIFIED
                profile.save(update_fields=['verification_status'])
        except AutoExclusion.DoesNotExist:
            if profile.verification_status == UserProfile.STATUS_SELF_EXCLUDED:
                raise serializers.ValidationError(
                    "Tu cuenta está en estado de autoexclusión y no puede realizar apuestas."
                )
        # --- FIN CONTROLES DE JUEGO RESPONSABLE ---

        if profile.verification_status != UserProfile.STATUS_VERIFIED:
            raise serializers.ValidationError(
                f"La cuenta está en estado '{profile.get_verification_status_display()}'. "
                "Sólo los usuarios verificados pueden colocar apuestas."
            )

        # 3. Cargar selecciones desde la BD local
        selection_ids = [s['selection_id'] for s in selections_data]
        selection_objs = list(Selection.objects.filter(id__in=selection_ids).select_related(
            'market', 'market__event', 'market__event__home_team', 'market__event__away_team'
        ))

        # Validar si todas las selecciones existen
        if len(selection_objs) != len(selections_data):
            raise serializers.ValidationError("Una o más selecciones enviadas no existen en el catálogo actual.")

        # 4. Validar política de re-cotización (Odds Change Check)
        diferencias_cuotas = []
        for s_post in selections_data:
            s_obj = next(s for s in selection_objs if s.id == s_post['selection_id'])
            # Comparar el valor esperado por el cliente con el valor actual en la BD
            if s_post['expected_odds'].quantize(Decimal('0.0001')) != s_obj.odds.quantize(Decimal('0.0001')):
                diferencias_cuotas.append({
                    'selection_id': s_obj.id,
                    'selection_name': s_obj.name,
                    'expected_odds': str(s_post['expected_odds']),
                    'actual_odds': str(s_obj.odds)
                })

        if diferencias_cuotas:
            # Lanzamos la excepción de API personalizada para forzar HTTP 409 Conflict directo
            raise OddsChangedException(
                cambios=diferencias_cuotas,
                detail="Las cuotas de tu boleto han cambiado. Por favor, reconfirma la operación."
            )


        # 5. Validar que las selecciones/mercados estén activos
        for s_obj in selection_objs:
            if not s_obj.is_active:
                raise serializers.ValidationError(f"La selección '{s_obj.name}' ya no está activa.")
            if not s_obj.market.is_active:
                raise serializers.ValidationError(f"El mercado '{s_obj.market.name}' para el partido '{s_obj.market.event}' está suspendido.")

        # 6. Validar que los partidos no hayan iniciado (excepto apuestas en vivo)
        for s_obj in selection_objs:
            event = s_obj.market.event
            # Bloquear apuestas en eventos suspendidos o cancelados (regulatorio)
            if event.status in ['suspended', 'cancelled']:
                raise serializers.ValidationError(
                    f"El partido '{event}' está en estado '{event.get_status_display()}' y no acepta apuestas."
                )
            if event.starts_at <= timezone.now() and event.status != 'in_play':
                raise serializers.ValidationError(f"El partido '{event}' ya ha comenzado y no acepta apuestas pre-match.")

        # 7. Validar exclusión mutua de selecciones del mismo evento (combinadas)
        event_ids = [s_obj.market.event.id for s_obj in selection_objs]
        if len(event_ids) != len(set(event_ids)):
            raise serializers.ValidationError("No puedes realizar una apuesta combinada con múltiples opciones del mismo partido.")

        # Guardar objetos cargados para uso directo en la vista
        self.context['loaded_selections'] = selection_objs
        return data

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['disclaimer'] = "Juego responsable: El juego de apuestas en exceso puede causar adicción. Juega con moderación. Plataforma de simulación educativa."
        return ret
