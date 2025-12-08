from __future__ import annotations
from typing import Any

from sqlalchemy import ColumnClause, column
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column

from base_repository.sa_helper import peel_unary, sa_mapper


# Base ORM setup for tests
class Base(DeclarativeBase):
    pass


# Test model: User (single PK)
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)


def test_sa_mapper_returns_sqlalchemy_mapper() -> None:
    """
    < sa_mapper returns an SQLAlchemy Mapper for a mapped ORM class >
    1. Call sa_mapper(User).
    2. Assert the return value is a sqlalchemy.orm.Mapper.
    3. Assert the mapper's class_ points back to User.
    """
    # 1
    m = sa_mapper(User)

    # 2
    assert isinstance(m, Mapper)

    # 3
    assert m.class_ is User


def test_peel_unary_returns_same_expr_if_not_unary() -> None:
    """
    < peel_unary returns the input unchanged when it is not a UnaryExpression >
    1. Create a simple ColumnElement via column("id").
    2. Call peel_unary(col).
    3. Assert the returned object is the same instance.
    """
    # 1
    col: ColumnClause[Any] = column("id")

    # 2
    out = peel_unary(col)

    # 3
    assert out is col


def test_peel_unary_strips_nested_unary_expressions() -> None:
    """
    < peel_unary removes nested UnaryExpression layers and returns the base ColumnElement >
    1. Create a ColumnElement via column("id").
    2. Wrap it with multiple unary modifiers (e.g., desc + nulls_last).
    3. Call peel_unary(expr).
    4. Assert the returned object is the original base ColumnElement.
    """
    # 1
    col: ColumnClause[Any] = column("id")

    # 2
    expr = col.desc().nulls_last()

    # 3
    out = peel_unary(expr)

    # 4
    assert out is col
