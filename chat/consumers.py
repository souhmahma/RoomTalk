import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .database import messages_collection
from datetime import datetime

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = f"chat_{self.room_name}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name 
        )

        await self.accept()

        # Récupération de l'historique (avec support fichiers)
        cursor = messages_collection.find({"room": self.room_name}).sort("timestamp", 1).limit(50)
        async for msg in cursor:
            await self.send(text_data=json.dumps({
                "message": msg.get("message", ""),
                "username": msg["username"],
                "file_url": msg.get("file_url"), # Récupère l'URL/Data du fichier si présent
                "is_image": msg.get("is_image", False),
                "is_history": True 
            }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get("type", "text")
        username = data.get("username", "Anonyme")
        
        # Initialisation de l'entrée MongoDB
        chat_entry = {
            "room": self.room_name,
            "username": username,
            "timestamp": datetime.now(),
            "type": msg_type
        }

        if msg_type == "file":
            # On stocke les infos du fichier
            chat_entry["file_url"] = data.get("file_data") # Ici c'est le base64
            chat_entry["file_name"] = data.get("file_name")
            chat_entry["is_image"] = data.get("is_image", False)
            chat_entry["message"] = "" # Pas de texte si c'est un fichier pur
        else:
            chat_entry["message"] = data.get("message", "")
            chat_entry["file_url"] = None

        # Sauvegarde MongoDB
        await messages_collection.insert_one(chat_entry)

        # Envoi au groupe
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat.message",
                "message": chat_entry.get("message"),
                "username": username,
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