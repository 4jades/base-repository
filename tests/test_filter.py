from __future__ import annotations

from collections.abc import Iterable as IterableABC
from dataclasses import dataclass

import pytest
from sqlalchemy.dialects import sqlite
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.elements import BindParameter

from base_repository.base_filter import BaseRepoFilter


# SQLAlchemy Base / model definitions for tests
class DummyModel(DeclarativeBase):
    pass


class M(DummyModel):
    __tablename__ = "m"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column()
    is_active: Mapped[bool] = mapped_column()


# Test filter for BaseRepoFilter.where_criteria()
@dataclass
class F(BaseRepoFilter):
    id: int | list[int] | None = None
    user_id: int | IterableABC[int] | None = None
    is_active: bool | None = None


def test_where_criteria_builds_expressions() -> None:
    """
    < where_criteria builds expected expressions for scalar, sequence, and bool fields >
    1. Provide id as a scalar -> equality expression.
    2. Provide user_id as a sequence -> IN expression.
    3. Provide is_active as a bool -> IS expression (not ==).
    4. Assert three expressions are produced and compile as expected.
    """
    # 1
    # 2
    # 3
    f = F(id=1, user_id=[10, 20], is_active=True)
    crit = f.where_criteria(M)

    # 4
    assert len(crit) == 3

    expr_id = crit[0]
    expr_user_id = crit[1]
    expr_active = crit[2]

    compiled_id = str(
        expr_id.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "id" in compiled_id
    assert "1" in compiled_id

    compiled_user_id = str(
        expr_user_id.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "user_id" in compiled_user_id
    assert "10" in compiled_user_id
    assert "20" in compiled_user_id

    compiled_active = str(
        expr_active.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "is_active" in compiled_active
    assert ("1" in compiled_active) or ("true" in compiled_active.lower())


def test_none_values_are_skipped() -> None:
    """
    < None values are skipped and do not produce WHERE criteria >
    1. Create a filter where all fields are None.
    2. Call where_criteria(Model).
    3. Assert no criteria are produced.
    """
    # 1
    f = F(id=None, user_id=None, is_active=None)

    # 2
    crit = f.where_criteria(M)

    # 3
    assert crit == []


def test_empty_sequences_are_skipped() -> None:
    """
    < Empty sequences are skipped and do not produce IN criteria >
    1. Create a filter with empty sequences for fields.
    2. Call where_criteria(Model).
    3. Assert no criteria are produced.
    """
    # 1
    f = F(id=[], user_id=[])

    # 2
    crit = f.where_criteria(M)

    # 3
    assert crit == []


def test_alias_mapping_simple() -> None:
    """
    < __aliases__ maps filter field names to different model column names (scalar -> ==) >
    1. Define a filter that aliases account_id -> user_id.
    2. Build criteria and assert a single criterion is produced.
    3. Assert the expression targets user_id and binds the expected value.
    4. Assert the compiled SQL includes user_id and the literal value.
    """

    @dataclass
    class FAlias(BaseRepoFilter):
        __aliases__ = {"account_id": "user_id"}
        account_id: int | None = 7

    # 1
    f = FAlias()

    # 2
    crit = f.where_criteria(M)
    assert len(crit) == 1
    expr = crit[0]

    # 3
    right = expr.right
    assert isinstance(right, BindParameter)
    assert right.value == 7

    # 4
    compiled = str(
        expr.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "user_id" in compiled
    assert "7" in compiled


def test_sequence_value_generates_in_expression_with_alias() -> None:
    """
    < __aliases__ + sequence value generates an IN expression >
    1. Define a filter that aliases user_ids -> user_id.
    2. Provide a sequence value for user_ids.
    3. Assert a single IN expression is produced for user_id.
    4. Assert bound parameter contains the sequence values and compiled SQL includes them.
    """

    @dataclass
    class FSeq(BaseRepoFilter):
        __aliases__ = {"user_ids": "user_id"}
        user_ids: IterableABC[int] | None = None

    # 1
    # 2
    f = FSeq(user_ids=[10, 20])
    crit = f.where_criteria(M)

    # 3
    assert len(crit) == 1
    expr = crit[0]

    right = expr.right
    assert isinstance(right, BindParameter)

    value = list(right.value)  # type: ignore[arg-type]
    assert sorted(value) == [10, 20]

    # 4
    compiled = str(
        expr.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "user_id" in compiled
    assert "10" in compiled
    assert "20" in compiled


def test_strict_mode_raises_on_unknown_column() -> None:
    """
    < __strict__=True raises when the filter references an unknown model column >
    1. Define a strict filter with a field that does not exist on the model.
    2. Call where_criteria(Model).
    3. Assert ValueError is raised.
    """

    @dataclass
    class FStrict(BaseRepoFilter):
        __strict__ = True
        unknown_field: int | None = 1

    # 1
    f = FStrict()

    # 2
    # 3
    with pytest.raises(ValueError):
        f.where_criteria(M)


def test_non_dataclass_raises_type_error() -> None:
    """
    < BaseRepoFilter requires dataclass subclasses and raises TypeError otherwise >
    1. Define a BaseRepoFilter subclass without @dataclass.
    2. Call where_criteria(Model).
    3. Assert TypeError is raised.
    """

    class NotDataclassFilter(BaseRepoFilter):
        id: int | None = 1

    # 1
    f = NotDataclassFilter()

    # 2
    # 3
    with pytest.raises(TypeError):
        f.where_criteria(M)


@pytest.mark.parametrize(
    "filter_cls, value",
    [
        ("str", "10"),
        ("bytes", b"10"),
        ("bytearray", bytearray(b"10")),
    ],
)
def test_string_like_values_are_not_treated_as_sequences_and_do_not_use_in(filter_cls: str, value) -> None:
    """
    < str/bytes/bytearray values are not treated as sequences for IN and do not generate IN clauses >
    1. Create a dataclass filter that sets user_id to a str/bytes/bytearray value.
    2. Build criteria for the model.
    3. Assert the compiled SQL does not contain an IN clause.
    """

    @dataclass
    class FStringLike(BaseRepoFilter):
        user_id: object | None = None

    # 1
    f = FStringLike(user_id=value)

    # 2
    crit = f.where_criteria(M)
    assert len(crit) == 1
    expr = crit[0]

    # 3
    compiled = str(
        expr.compile(
            dialect=sqlite.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "user_id" in compiled
    assert "IN" not in compiled.upper()
