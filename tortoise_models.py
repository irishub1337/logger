import json
import typing
import vkquick
from loguru import logger
from tortoise import Model, fields, Tortoise
from datetime import datetime
import enum


class DataTypeEnum(enum.Enum):
    USER = enum.auto()
    GROUP = enum.auto()
    CHAT = enum.auto()

    @classmethod
    def get_type(cls, peer_id: int) -> "DataTypeEnum":
        if peer_id < 0:
            return DataTypeEnum.GROUP
        if peer_id > 2e9:
            return DataTypeEnum.CHAT
        return DataTypeEnum.USER


class GetMixin:

    @classmethod
    async def get_or_create_from_vk(
            cls: typing.Union["Author", "Chat"],
            api: vkquick.API,
            peer_id: int
    ) -> typing.Union["Author", "Chat"]:
        db = await cls.get_or_none(id=peer_id)
        if not db:
            if DataTypeEnum.get_type(peer_id) == DataTypeEnum.USER:
                user = await vkquick.User.fetch_one(api, peer_id, fields=['photo_200'])
                db = await cls.create(
                    id=peer_id,
                    title=f"{user.fn} {user.ln}",
                    photo=user.fields.get('photo_200')
                )
            elif DataTypeEnum.get_type(peer_id) == DataTypeEnum.GROUP:
                group = await vkquick.Group.fetch_one(api, abs(peer_id))
                db = await cls.create(
                    id=peer_id,
                    title=group.fields["name"],
                    photo=group.fields.get('photo_200')
                )
            else:
                chat = await api.use_cache().method("messages.getConversationsById", peer_ids=peer_id)
                db = await cls.create(
                    id=peer_id,
                    title=chat['items'][0]['chat_settings']['title'],
                    photo=chat['items'][0]['chat_settings'].get('photo', {}).get(
                        'photo_200',
                        "https://sun1-87.userapi.com/s/v1/if1/"
                        "wOKwTPQQd3aCLZwg6kqbmPLTe_SIV8R2CjmjikmcByHjTsVo0XjvCO1LWsI5_TaZAfPLZwNl.jpg?"
                        "size=200x200&amp;quality=96&amp;crop=0,0,400,400&amp;ava=1"
                    )
                )
        return db


class Author(Model, GetMixin):
    id = fields.IntField(pk=True)
    title = fields.TextField()
    photo = fields.TextField()

    def get_link(self):
        if DataTypeEnum.get_type(self.id) == DataTypeEnum.USER:
            return f"https://vk.com/id{self.id}"
        else:
            return f"https://vk.com/club{abs(self.id)}"


class Chat(Model, GetMixin):
    id = fields.IntField(pk=True)
    title = fields.TextField()
    photo = fields.TextField()


class Message(Model):
    class TypeEnum(enum.Enum):
        NEW_MESSAGE = "n"
        EDIT_MESSAGE = "e"

    id = fields.UUIDField(pk=True)
    message_id = fields.BigIntField()
    type: TypeEnum = fields.CharEnumField(TypeEnum, max_length=1, default=TypeEnum.NEW_MESSAGE)

    chat: typing.Awaitable['Chat'] = fields.ForeignKeyField(
        'models.Chat',
        on_delete=fields.CASCADE,
        related_name='messages'
    )
    author: typing.Awaitable['Author'] = fields.ForeignKeyField(
        'models.Author',
        on_delete=fields.CASCADE,
        related_name='messages'
    )
    message_text = fields.TextField()
    attachments_json = fields.TextField(default="[]")
    date = fields.DatetimeField(default=datetime.utcnow)

    reply_message = fields.ForeignKeyField(
        'models.Message',
        on_delete=fields.SET_NULL,
        null=True,
        blank=True
    )

    fwd_messages_json = fields.TextField(default="[]")

    @property
    def fwd_messages(self):
        return json.loads(self.fwd_messages_json)

    @property
    def attachments(self):
        return json.loads(self.attachments_json)

    @attachments.setter
    def attachments(self, new_value):
        self.attachments_json = json.dumps(new_value, ensure_ascii=False)

    @property
    def vk_link(self):
        chat_id = self.chat_id
        if DataTypeEnum.get_type(chat_id) == DataTypeEnum.CHAT:
            chat_id = chat_id - int(2e9)
            chat_id = f"c{chat_id}"
        return f"https://vk.com/im?msgid={self.message_id}&sel={chat_id}"

    @classmethod
    async def parse_or_get(
            cls,
            api: vkquick.API,
            message_or_message_id: typing.Union[dict, int],
            type: TypeEnum,
            chat: Chat = None,
            author: Author = None
    ):
        message_id = message_or_message_id if isinstance(message_or_message_id, int) else message_or_message_id['id']
        db = await cls.get_or_none(message_id=message_id, type=cls.TypeEnum.NEW_MESSAGE)

        if db:
            logger.opt(colors=True).success(
                f"Сообщение {db.type} <red>{db.id}</red>"
                f" успешно <yellow>выгружено</yellow> из БД"
            )
            return db

        if isinstance(message_or_message_id, int):
            message = (await api.method("messages.getById", message_ids=[message_id]))['items'][0]
        else:
            message = message_or_message_id

        if not chat:
            chat = await Chat.get_or_create_from_vk(api, message['peer_id'])

        if not author:
            author = await Author.get_or_create_from_vk(api, message['from_id'])

        if message.get('reply_message'):
            await Author.get_or_create_from_vk(api, message['reply_message']['from_id'])
        for fwd in message.get('fwd_messages', []):
            await Author.get_or_create_from_vk(api, fwd['from_id'])

        db = await cls.create(
            type=type,
            message_id=message['id'],
            chat=chat,
            author=author,
            message_text=message['text'],
            attachments_json=json.dumps(message['attachments'], ensure_ascii=False),
            reply_message=await cls.parse_or_get(api, message['reply_message'], type.NEW_MESSAGE) if message.get(
                'reply_message') else None,
            fwd_messages_json=json.dumps(message.get('fwd_messages', [])),
            date=datetime.fromtimestamp(message['date'])
        )
        logger.opt(colors=True).success(
            f"Сообщение {db.type} <red>{db.id}</red> | by <red>{author.title}</red>"
            f" успешно <yellow>загружено</yellow> в БД"
        )
        return db

    class Meta:
        ordering = ['-date']


async def init_tortoise(*args, **kwargs):
    await Tortoise.init(
        db_url="sqlite://db.sq",
        modules={"models": ["tortoise_models"]}
    )
    await Tortoise.generate_schemas()
 