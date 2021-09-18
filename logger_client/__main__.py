import asyncio
import json
import os
import sys

import vkquick as vq
import tortoise_models
from logger_client.load_messages import load_messages

app = vq.App()


@app.on_startup()
async def on_startup(*args, **kwargs):
    await tortoise_models.init_tortoise()


@app.on_message()
async def handler(ctx: vq.NewMessage):
    await tortoise_models.Message.parse_or_get(ctx.api, ctx.msg.id, tortoise_models.Message.TypeEnum.NEW_MESSAGE)


if __name__ == "__main__":
    if "load_messages" in sys.argv:
        asyncio.get_event_loop().run_until_complete(load_messages(vq.API(os.environ.get("USER_ACCESS_TOKEN"))))
    else:
        app.run("$USER_ACCESS_TOKEN")
