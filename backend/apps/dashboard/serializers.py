# -*- coding: utf-8 -*-
from rest_framework import serializers
from decimal import Decimal


class SelectionExposureSerializer(serializers.Serializer):
    selection_id = serializers.IntegerField()
    selection_name = serializers.CharField()
    odds = serializers.DecimalField(max_digits=10, decimal_places=4)
    active_bets_count = serializers.IntegerField()
    total_stake = serializers.DecimalField(max_digits=18, decimal_places=4)
    gross_exposure = serializers.DecimalField(max_digits=18, decimal_places=4)
    net_exposure = serializers.DecimalField(max_digits=18, decimal_places=4)


class MarketExposureSerializer(serializers.Serializer):
    market_id = serializers.IntegerField()
    market_name = serializers.CharField()
    selections = SelectionExposureSerializer(many=True)


class EventExposureSerializer(serializers.Serializer):
    event_id = serializers.IntegerField()
    home_team = serializers.CharField()
    away_team = serializers.CharField()
    league_name = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    status_display = serializers.CharField()
    markets = MarketExposureSerializer(many=True)


class BetVolumeSerializer(serializers.Serializer):
    total_bets_count = serializers.IntegerField()
    total_stakes_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    active_bets_count = serializers.IntegerField()
    active_stakes_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    today_bets_count = serializers.IntegerField()
    today_stakes_amount = serializers.DecimalField(max_digits=18, decimal_places=4)


class ActiveUsersSerializer(serializers.Serializer):
    active_users_24h = serializers.IntegerField()
    active_users_7d = serializers.IntegerField()
    active_users_30d = serializers.IntegerField()
    total_registered_users = serializers.IntegerField()


class GGRMetricsSerializer(serializers.Serializer):
    ggr = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_stakes = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_payouts = serializers.DecimalField(max_digits=18, decimal_places=4)


class OperatorMetricsSerializer(serializers.Serializer):
    ggr = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_stakes = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_payouts = serializers.DecimalField(max_digits=18, decimal_places=4)
    bet_volume = BetVolumeSerializer()
    active_users = ActiveUsersSerializer()
    event_exposure = EventExposureSerializer(many=True)
    disclaimer = serializers.CharField()
    timestamp = serializers.DateTimeField()