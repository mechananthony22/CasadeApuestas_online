# -*- coding: utf-8 -*-
# Consumidores de WebSockets (Django Channels) para la aplicación betting
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class EventConsumer(AsyncWebsocketConsumer):
    """
    Consumidor para transmitir en tiempo real actualizaciones de un evento específico
    (goles, marcadores y cambios de cuotas en vivo).
    """
    async def connect(self):
        self.event_id = self.scope['url_route']['kwargs']['event_id']
        self.group_name = f"event_{self.event_id}"

        # Unirse al grupo del partido
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Salir del grupo del partido
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def event_update(self, event):
        """
        Recibe marcador y estado del partido desde la Channel Layer y lo envía por WebSocket al cliente.
        """
        await self.send(text_data=json.dumps(event))

    async def odds_changed(self, event):
        """
        Recibe la fluctuación de cuotas (re-cotización) desde la Channel Layer y la transmite por WebSocket.
        """
        await self.send(text_data=json.dumps(event))

    async def market_suspended(self, event):
        """
        Recibe la notificación de suspensión de mercados y la transmite por WebSocket al cliente.
        """
        await self.send(text_data=json.dumps(event))

    async def market_resumed(self, event):
        """
        Recibe la notificación de reanudación de mercados y la transmite por WebSocket al cliente.
        """
        await self.send(text_data=json.dumps(event))


class UserNotificationConsumer(AsyncWebsocketConsumer):
    """
    Consumidor seguro para transmitir notificaciones privadas de transacciones
    (apuestas aceptadas, cash-out exitosos, apuestas liquidadas).
    Exige obligatoriamente autenticación de sesión de Django.
    """
    async def connect(self):
        self.user = self.scope.get('user')

        # Denegar conexión de forma segura si el usuario es anónimo (requisito regulatorio)
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.user_id = self.user.id
        self.group_name = f"user_{self.user_id}"

        # Registrar el canal WebSocket en el grupo personal del usuario
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def bet_accepted(self, event):
        """
        Envía notificación de colocación exitosa del ticket.
        """
        await self.send(text_data=json.dumps(event))

    async def cashout_accepted(self, event):
        """
        Envía notificación de cobro anticipado (Cash-out) exitoso.
        """
        await self.send(text_data=json.dumps(event))

    async def bet_settled(self, event):
        """
        Envía notificación de liquidación contable (apuesta resuelta como ganada/perdida/anulada).
        """
        await self.send(text_data=json.dumps(event))
