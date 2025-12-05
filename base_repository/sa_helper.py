from typing import Any, cast

from sqlalchemy import ColumnElement, UnaryExpression, inspect
from sqlalchemy.orm import Mapper


def sa_mapper(model: type[Any]) -> Mapper[Any]:
    return cast(Mapper[Any], inspect(model))


def peel_unary(expr: ColumnElement[Any]) -> ColumnElement[Any]:
    base = expr
    while isinstance(base, UnaryExpression):
        base = cast(ColumnElement[Any], base.element)
    return base
