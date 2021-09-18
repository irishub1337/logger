import abc
import dataclasses
import datetime
import typing

from jinja2 import Template

import tortoise_models
from logger_server.utils import jinja2_env, prepare_text, api, Paginator
from tortoise_models import Message


class ABCRenderer(abc.ABC):
    template: typing.Union[str, Template] = None
    fields: typing.Dict[str, "ABCRenderer"] = {}

    def __init__(self, template: typing.Union[str, Template] = None, fields: typing.Dict[str, "ABCRenderer"] = None):
        self.template = template or self.__class__.template
        self.fields = fields or self.__class__.fields

    @abc.abstractmethod
    async def render(self, message: Message) -> str:
        ...

    @abc.abstractmethod
    def get_template(self) -> Template:
        ...


class BaseRenderer(ABCRenderer):

    def get_template(self) -> Template:
        if isinstance(self.template, Template):
            return self.template
        return jinja2_env.get_template(self.template)

    async def render(self, message: Message) -> str:
        fields = {}
        for k, v in self.fields.items():
            fields[k] = await v.render(message)
        return self.get_template().render(**fields)


@dataclasses.dataclass
class ChatResult:
    chat: tortoise_models.Chat
    count: int

    @classmethod
    async def gen(cls, chat: tortoise_models.Chat):
        return cls(
            chat,
            await chat.messages.all().count()
        )


class ListOfChatsRenderer(BaseRenderer):
    template = 'list_of_chats.html'

    async def render(self, search_phrase: str, *chats: tortoise_models.Chat) -> str:
        new_chats = []
        for chat in chats:
            new_chats.append(await ChatResult.gen(chat))

        return self.get_template().render(
            search_phrase=search_phrase,
            chats=new_chats
        )


class TitleRenderer(BaseRenderer):

    async def render(self, chat: tortoise_models.Chat) -> str:
        return chat.title


class ReplyMessageRenderer(BaseRenderer):
    template = 'reply_message.html'

    async def render(self, message: Message) -> str:
        reply = await message.reply_message
        return await MessageRenderer(self.template).render(reply) if reply else None


class ForwardMessagesRenderer(BaseRenderer):
    template = 'fwd_messages.html'

    async def render(self, fwd_messages: typing.List[dict]) -> typing.List[str]:
        fwd_msgs = []
        for fwd_msg in fwd_messages:
            author = await tortoise_models.Author.get_or_create_from_vk(api, fwd_msg['from_id'])
            fwd_msgs.append(
                self.get_template().render(
                    photo=author.photo,
                    link=author.get_link(),
                    name=author.title,
                    date=datetime.datetime.fromtimestamp(fwd_msg['date']).strftime("%d.%m.%Y %H:%M"),
                    text=prepare_text(fwd_msg['text']),
                    fwd_messages=await ForwardMessagesRenderer().render(fwd_msg.get('fwd_messages'))
                    if fwd_msg.get('fwd_messages')
                    else None,
                    attachments=await AttachmentsRenderer().render(fwd_msg.get('attachments', [])),
                    **{
                        k: v
                        for k, v in fwd_msg.items()
                        if k not in ('attachments', 'reply_message', 'fwd_messages', 'date', 'text',)
                    }
                )
            )
        return fwd_msgs


class AttachmentsRenderer(BaseRenderer):

    @staticmethod
    def get_template_by_attachment(type: str) -> typing.Optional[Template]:
        try:
            return jinja2_env.get_template(f'attachments/{type}.html')
        except:
            return None

    async def render(self, attachments: typing.List[dict]) -> typing.List[str]:
        atchs = []
        for attachment in attachments:
            template = self.get_template_by_attachment(attachment['type'])
            if template:
                atchs.append(template.render(**attachment[attachment['type']]))
        return atchs


class MessageRenderer(BaseRenderer):
    template = 'message.html'

    async def render(self, message: Message) -> str:
        author = await message.author
        return self.get_template().render(
            id=message.id,
            vk_link=message.vk_link,
            photo=author.photo,
            link=author.get_link(),
            name=author.title,
            date=message.date.strftime("%d.%m.%Y %H:%M"),
            text=prepare_text(message.message_text),
            reply_message=await ReplyMessageRenderer().render(message),
            fwd_messages=await ForwardMessagesRenderer().render(message.fwd_messages),
            attachments=await AttachmentsRenderer().render(message.attachments)
        )


class LayoutRenderer(BaseRenderer):
    template = 'layout.html'

    async def render(self, chat: tortoise_models.Chat, paginator: Paginator[Message], search_phrase: str) -> str:
        _messages = []
        for message in paginator.items:
            _messages.append(await MessageRenderer().render(message))
        return self.get_template().render(
            messages=_messages,
            title=await TitleRenderer().render(chat),
            chat_id=chat.id,
            paginator=paginator,
            search_phrase=search_phrase
        )
