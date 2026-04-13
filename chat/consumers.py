import json
import random
import string
from channels.generic.websocket import AsyncWebsocketConsumer
from .database import messages_collection
from datetime import datetime

class ChatConsumer(AsyncWebsocketConsumer):
    # Dictionnaire partagé pour suivre les pseudos actifs par room
    # Format: { 'room_name': { 'pseudo1', 'pseudo2' } }
    active_users = {}

    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"

        # Initialiser l'ensemble des utilisateurs pour la room si inexistant
        if self.room_name not in ChatConsumer.active_users:
            ChatConsumer.active_users[self.room_name] = set()

        # Générer un pseudo unique
        self.username = self.generate_unique_username()
        ChatConsumer.active_users[self.room_name].add(self.username)

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.send(text_data=json.dumps({
            "type": "setup",
            "suggested_username": self.username
        }))

        # Récupération de l'historique
        cursor = messages_collection.find({"room": self.room_name}).sort("timestamp", 1).limit(50)
        async for msg in cursor:
            await self.send(text_data=json.dumps({
                "message": msg.get("message", ""),
                "username": msg["username"],
                "file_url": msg.get("file_url"),
                "is_image": msg.get("is_image", False),
                "is_history": True 
            }))

    def generate_unique_username(self):
        while True:
            # Génère un pseudo comme User4285
            suffix = ''.join(random.choices(string.digits, k=4))
            name = f"User{suffix}"
            if name not in ChatConsumer.active_users[self.room_name]:
                return name

    async def disconnect(self, close_code):
        # Retirer l'utilisateur de la liste des actifs
        if self.room_name in ChatConsumer.active_users:
            ChatConsumer.active_users[self.room_name].discard(self.username)
        
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get("type", "text")
        new_username = data.get("username", self.username).strip()

        # Validation du changement de pseudo
        if new_username != self.username:
            if new_username not in ChatConsumer.active_users[self.room_name] and new_username != "":
                ChatConsumer.active_users[self.room_name].discard(self.username)
                self.username = new_username
                ChatConsumer.active_users[self.room_name].add(self.username)
            else:
                pass

        chat_entry = {
            "room": self.room_name,
            "username": self.username,
            "timestamp": datetime.now(),
            "type": msg_type
        }

        if msg_type == "file":
            chat_entry["file_url"] = data.get("file_data")
            chat_entry["file_name"] = data.get("file_name")
            chat_entry["is_image"] = data.get("is_image", False)
            chat_entry["message"] = ""
        else:
            chat_entry["message"] = data.get("message", "")

        await messages_collection.insert_one(chat_entry)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.message",
                "message": chat_entry.get("message"),
                "username": self.username,
                "file_url": chat_entry.get("file_url"),
                "is_image": chat_entry.get("is_image", False),
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "message": event.get("message"),
            "username": event["username"],
            "file_url": event.get("file_url"),
            "is_image": event.get("is_image", False),
        }))