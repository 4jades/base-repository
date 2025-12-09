import sys
from typing import TYPE_CHECKING, TypeAlias

from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.orm import DeclarativeBase

if sys.version_info >= (3, 13):
    from typing import TypeVar, Never
else:
    from typing_extensions import TypeVar

if TYPE_CHECKING:
    from base_repository.query.list_query import ListQuery

class NoSchema:
    """Typing-only sentinel. Never used as a real mapping schema."""
    pass

TModel = TypeVar("TModel", bound=DeclarativeBase)
TPydanticSchema = TypeVar("TPydanticSchema", bound=BaseModel)
TSchema = TypeVar("TSchema", bound=BaseModel | NoSchema, default=NoSchema)


# If you add more query/statement types beyond ListQuery, extend this union type.
QueryOrStmt: TypeAlias = "ListQuery[TModel] | Select[tuple[TModel]]"
