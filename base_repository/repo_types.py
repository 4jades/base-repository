import sys
from typing import TYPE_CHECKING, Any, TypeAlias

from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.orm import DeclarativeBase

if sys.version_info >= (3, 13):
    from typing import TypeVar
else:
    from typing_extensions import TypeVar

if TYPE_CHECKING:
    from base_repository.query.list_query import ListQuery

TModel = TypeVar("TModel", bound=DeclarativeBase)
TDomain = TypeVar("TDomain", bound=BaseModel, default=Any)
# If we want to treat the domain type as a generic as well, consider this.
# It’s likely a trade-off between DX and type safety.


# If you add more query/statement types beyond ListQuery, extend this union type.
QueryOrStmt: TypeAlias = "ListQuery[TModel] | Select[tuple[TModel]]"
