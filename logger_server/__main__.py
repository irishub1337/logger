import os
import re

from aiohttp import web
from tortoise.query_utils import Q

import tortoise_models
from logger_server.renderer import ListOfChatsRenderer, LayoutRenderer
from logger_server.utils import jinja2_env, prepare_text, Paginator

app = web.Application()


async def list_of_chats(request: web.Request) -> web.Response:
    if request.method == 'POST':
        data = await request.post()
        search_ph = data.get('searchPhrase', '')
        chats = await tortoise_models.Chat.filter(title__icontains=search_ph)
    else:
        search_ph = ''
        chats = await tortoise_models.Chat.all()

    return web.Response(
        text=await ListOfChatsRenderer().render(search_ph, *chats),
        content_type='text/html'
    )


async def show_chat(request: web.Request) -> web.Response:
    if request.method == 'POST':
        data = await request.post()
        search_ph = data.get('searchPhrase', '')
        page = int(data.get('page', '1'))
    else:
        page = 1
        search_ph = ''

    chat = await tortoise_models.Chat.get(id=int(request.match_info['peer_id']))
    qs = Q(chat=chat)
    if search_ph:
        qs &= Q(message_text__icontains=search_ph) | Q(author__title__icontains=search_ph)

    paginator = await Paginator.create(
        tortoise_models.Message,
        qs,
        200,
        page
    )
    return web.Response(
        text=await LayoutRenderer().render(chat, paginator, search_ph),
        content_type='text/html'
    )


app.router.add_get('/', list_of_chats)
app.router.add_post('/', list_of_chats)
app.router.add_get(r'/{peer_id}', show_chat)
app.router.add_post(r'/{peer_id}', show_chat)

app.on_startup.append(tortoise_models.init_tortoise)

if __name__ == "__main__":
    app.router.add_static('/static', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static'))
    web.run_app(app)
