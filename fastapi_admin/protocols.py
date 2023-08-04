from tortoise import fields
from typing import ClassVar, Protocol


class AdminModel(Protocol):
    password: ClassVar[fields.CharField]
