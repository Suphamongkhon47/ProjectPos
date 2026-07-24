import json
from channels.generic.websocket import AsyncWebsocketConsumer


class DashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("dashboard", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("dashboard", self.channel_name)

    # รับ broadcast จาก group แล้วส่งไป browser
    async def dashboard_update(self, event):
        await self.send(text_data=json.dumps(event["data"]))
