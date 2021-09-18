import dataclasses
import math
import os.path
import re
import typing

import vkquick
from jinja2 import Environment, FileSystemLoader, select_autoescape
from tortoise import Model
from tortoise.query_utils import Q

from tortoise_models import Message

api = vkquick.API(os.environ.get("USER_ACCESS_TOKEN"))

user_regex = re.compile(r"\[id(\d+)\|([^]\n\f\t]+)\]")
group_regex = re.compile(r"\[club(\d+)\|([^]\n\f\t]+)\]")

jinja2_env = Environment(
    loader=FileSystemLoader(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    ),
    autoescape=select_autoescape()
)


def prepare_text(text: str) -> str:
    for user_id, user_name in re.findall(user_regex, text):
        text = text.replace(
            f"[id{user_id}|{user_name}]",
            f'<a href="https://vk.com/id{user_id}" target="_blank">{user_name}</a>'
        )

    for group_id, group_name in re.findall(group_regex, text):
        text = text.replace(
            f"[club{group_id}|{group_name}]",
            f'<a href="https://vk.com/club{group_id}" target="_blank">{group_name}</a>'
        )
    return "".join(f"{line}<br>" for line in text.split("\n")) if text else ""


T = typing.TypeVar('T')


@dataclasses.dataclass
class Paginator(typing.Generic[T]):
    items: typing.List[T]
    all_count: int
    page: int
    has_next: bool
    has_prev: bool
    all_page_count: int

    @property
    def next_page(self):
        return self.page + 1

    @property
    def prev_page(self):
        return self.page - 1

    @property
    def xrange(self):
        all_page_range = range(1, self.all_page_count + 1)
        for i in range(self.page - 2, self.page + 3):
            if i in all_page_range:
                yield i

    @classmethod
    async def create(
            cls: typing.Type["Paginator[T]"],
            model_cls: typing.Type[T],
            queryset: Q,
            count_per_page: int,
            page: int = 1
    ) -> "Paginator[T]":
        count_all = await model_cls.filter(queryset).count()
        current_position_min = (page - 1) * count_per_page
        current_position_max = (page - 1) * count_per_page + count_per_page
        qs = await model_cls.filter(queryset).offset((page - 1) * count_per_page).limit(count_per_page)

        has_next: bool = False
        has_prev: bool = False

        if current_position_max < count_all:
            has_next = True

        if current_position_min > 0:
            has_prev = True

        all_page_count = math.floor(count_all / count_per_page)

        if count_all % count_per_page != 0:
            all_page_count += 1

        return cls(
            items=list(qs),
            all_count=count_all,
            page=page,
            has_next=has_next,
            has_prev=has_prev,
            all_page_count=all_page_count
        )
