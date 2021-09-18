import asyncio
import threading
import time
from typing import List

import vkquick
import vkquick as vq

from tortoise_models import init_tortoise, Message, Chat, Author
from loguru import logger


class ConversationGenerator:

    def __init__(self, api: vq.API, filter_group: List[str]):
        self._api = api
        self._filter_group = filter_group

    async def __aiter__(self):
        conversations = await self._api.method("messages.getConversations", count=1)
        offset = 0
        count = conversations['count']
        while offset < count:
            try:
                conversations = await self._api.method("messages.getConversations", offset=offset, count=200)
                for conv in conversations['items']:
                    if conv['conversation']['peer']['type'] not in self._filter_group or (
                            self._filter_group[0] == 'peer_id' and
                            conv['conversation']['peer']['id'] not in self._filter_group[0]
                    ):
                        continue
                    yield conv['conversation']['peer']['id']
                offset += len(conversations['items'])
            except Exception as ex:
                logger.error(f"{ex}: sleep 5 second")
                await asyncio.sleep(5)


class HistoryGenerator:

    def __init__(self, api: vq.API, conversation_peer_id: int, conv_name: str):
        self._api = api
        self._peer_id = conversation_peer_id
        self.conv_name = conv_name

    async def get_list(self):
        messages = []
        async for msg in self:
            messages.append(msg)
        return messages

    async def __aiter__(self):
        await asyncio.sleep(2)
        hist = await self._api.method("messages.getHistory", peer_id=self._peer_id, count=0)
        offset = 0
        hist_count = hist['count']

        while offset < hist_count:
            logger.opt(colors=True).info(
                f"Load messages for conversation <red>{self.conv_name}</red>: "
                f"<green>{offset}</green>/<green>{hist_count}</green>"
            )
            try:
                hist = await self._api.method(
                    "messages.getHistory",
                    peer_id=self._peer_id,
                    count=200,
                    offset=offset
                )
                for message in hist['items']:
                    # if message['date'] < time.time() - 24 * 60 * 60:
                    #     return
                    yield message
                offset += len(hist['items'])
            except Exception as ex:
                logger.error(f"{ex}: sleep 5 second")
                await asyncio.sleep(.5)


async def load_messages(api: vq.API):
    await init_tortoise()

    filt = input("filter by [user, chat, group, email, all, peer_id[,peer_id[,peer_id[,...]]]]")
    if filt == 'all':
        filter_group = ['user', 'chat', 'group', 'email']
    else:
        filter_group = [filt]

    async for conversation_peer_id in ConversationGenerator(api, filter_group):
        chat = await Chat.get_or_create_from_vk(api, conversation_peer_id)
        async for msg in HistoryGenerator(api, chat.id, chat.title):
            try:
                await Message.parse_or_get(api, msg, Message.TypeEnum.NEW_MESSAGE, chat=chat)
            except Exception as ex:
                logger.exception(ex)