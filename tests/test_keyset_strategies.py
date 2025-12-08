from __future__ import annotations

import re
from typing import Any, cast
from unittest.mock import patch

import pytest
from sqlalchemy import Column, ColumnElement, Integer, Select, String, column, select
from sqlalchemy.orm import DeclarativeBase

from base_repository.query.strategies.keyset import KeysetStrategy


# SQLAlchemy Base / model definitions for tests
class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    age = Column(Integer)


def compile_sql(stmt) -> str:
    """
    < Compile a SQLAlchemy Select into a string (loose, dialect-agnostic) >
    1. Convert the statement to string.
    2. Return the SQL text for regex-based assertions.
    """
    # 1
    sql = str(stmt)

    # 2
    return sql


def has_limit(sql: str) -> bool:
    """
    < Return True if the SQL contains a LIMIT clause >
    1. Search for the LIMIT keyword using a case-insensitive regex.
    2. Return True if a match exists.
    """
    # 1
    m = re.search(r"LIMIT\b", sql, re.IGNORECASE)

    # 2
    return bool(m)


def has_where(sql: str) -> bool:
    """
    < Return True if the SQL contains a WHERE clause >
    1. Search for the WHERE keyword using a case-insensitive regex.
    2. Return True if a match exists.
    """
    # 1
    m = re.search(r"\bWHERE\b", sql, re.IGNORECASE)

    # 2
    return bool(m)


def has_tuple_gt(sql: str) -> bool:
    """
    < Loosely detect a tuple-greater-than comparison in SQL >
    1. Match the pattern: (col1, col2, ...) > (:p1, :p2, ...)
       - Allow flexible whitespace/newlines and quoted identifiers.
    2. Return True if such a pattern exists.
    """
    # 1
    pattern = r"\(\s*[^)]+?,\s*[^)]+?\)\s*>\s*\(\s*[^)]+?\)"
    m = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)

    # 2
    return m is not None


def test_raise_when_no_order_cols() -> None:
    """
    < apply raises when order_cols is empty >
    1. Create a simple select(User) statement.
    2. Call KeysetStrategy.apply with empty order_cols.
    3. Assert ValueError is raised indicating order_cols is required.
    """
    # 1
    stmt = select(User)

    # 2
    # 3
    with pytest.raises(ValueError, match="order_cols"):
        KeysetStrategy.apply(stmt, order_cols=[], cursor={}, size=10)


def test_raise_when_size_less_than_one() -> None:
    """
    < apply raises when size is less than 1 >
    1. Create a simple select(User) statement.
    2. Call KeysetStrategy.apply with size=0.
    3. Assert ValueError is raised indicating size must be valid.
    """
    # 1
    stmt = select(User)

    # 2
    # 3
    with pytest.raises(ValueError, match="size"):
        KeysetStrategy.apply(stmt, order_cols=[User.id], cursor={}, size=0)


def test_first_page_limit_only_when_cursor_is_empty_or_none() -> None:
    """
    < First page applies LIMIT without WHERE when cursor is {} or None >
    1. Create a select(User) statement.
    2. Apply keyset paging with cursor={} and assert LIMIT exists and WHERE does not.
    3. Apply keyset paging with cursor=None and assert LIMIT exists and WHERE does not.
    """
    # 1
    stmt = select(User)

    # 2
    q_empty = KeysetStrategy.apply(stmt, order_cols=[User.id], cursor={}, size=5)
    sql_empty = compile_sql(q_empty)
    assert has_limit(sql_empty)
    assert not has_where(sql_empty)

    # 3
    q_none = KeysetStrategy.apply(stmt, order_cols=[User.id], cursor=None, size=5)
    sql_none = compile_sql(q_none)
    assert has_limit(sql_none)
    assert not has_where(sql_none)


def test_cursor_key_set_mismatch_raises_for_multi_column() -> None:
    """
    < apply raises when cursor keys do not match order_cols keys (multi-column) >
    1. Use order_cols = [User.id, User.name].
    2. Provide a cursor with an unexpected key.
    3. Assert ValueError is raised.
    """
    # 1
    stmt = select(User)
    order_cols = [
        cast(ColumnElement[Any], User.id),
        cast(ColumnElement[Any], User.name)
    ]

    # 2
    cursor = {"id": 1, "wrong_key": "kim"}

    # 3
    with pytest.raises(ValueError):
        KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=10)


def test_cursor_key_set_mismatch_raises_for_single_column() -> None:
    """
    < apply raises when cursor keys do not match order_cols keys (single-column) >
    1. Use order_cols = [User.id].
    2. Provide a cursor with an extra key.
    3. Assert ValueError is raised.
    """
    # 1
    stmt = select(User)
    order_cols = [User.id]

    # 2
    cursor = {"id": 1, "extra": 999}

    # 3
    with pytest.raises(ValueError):
        KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=10)


def test_multi_columns_all_asc_uses_tuple_comparison() -> None:
    """
    < Multi-column all-ASC ordering uses tuple '>' comparison >
    1. Use order_cols = [User.id, User.name] (ASC by default).
    2. Provide cursor for both columns.
    3. Assert the SQL contains a tuple '>' comparison and includes WHERE and LIMIT.
    """
    # 1
    stmt = select(User)
    order_cols = [
        cast(ColumnElement[Any], User.id),
        cast(ColumnElement[Any], User.name)
    ]

    # 2
    cursor = {"id": 1, "name": "kim"}
    q = KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=7)

    # 3
    sql = compile_sql(q)
    assert has_tuple_gt(sql)
    assert has_where(sql) and has_limit(sql)


def test_single_column_desc_generates_less_than_condition() -> None:
    """
    < Single-column DESC generates a WHERE '<' comparison >
    1. Use order_cols = [User.id.desc()].
    2. Provide cursor for id.
    3. Assert WHERE exists and '<' is present.
    """
    # 1
    stmt = select(User)
    order_cols = [User.id.desc()]

    # 2
    cursor = {"id": 100}
    q = KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=10)

    # 3
    sql = compile_sql(q)
    assert has_where(sql)
    assert "<" in sql


def test_multiple_desc_and_asc_combination_generates_or_ladder_with_both_ops() -> None:
    """
    < Mixed directions across two columns generate an OR-ladder with both '<' and '>' >
    1. Use order_cols = [User.id.desc(), User.name.asc()].
    2. Provide cursor for both columns.
    3. Assert SQL contains an OR ladder and includes both operators.
    """
    # 1
    stmt = select(User)
    order_cols: list[ColumnElement[Any]] = [
        cast(ColumnElement[Any], User.id.desc()),
        cast(ColumnElement[Any], User.name.asc()),
    ]

    # 2
    cursor = {"id": 5, "name": "bob"}
    q = KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=15)

    # 3
    sql = compile_sql(q)
    assert " OR " in sql
    assert "<" in sql and ">" in sql
    assert has_limit(sql)


def test_mixed_direction_with_three_columns_generates_multi_or_ladder() -> None:
    """
    < Mixed directions across three columns produce a multi-OR ladder >
    1. Use order_cols = [User.id.asc(), User.name.desc(), User.age.desc()].
    2. Provide a full cursor for all columns.
    3. Assert the SQL contains at least two OR segments and includes LIMIT.
    """
    # 1
    stmt = select(User)
    order_cols = [
        cast(ColumnElement[Any], User.id.asc()),
        cast(ColumnElement[Any], User.name.desc()),
        cast(ColumnElement[Any], User.age.desc()),
    ]


    # 2
    cursor = {"id": 1, "name": "foo", "age": 10}
    q = KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=30)

    # 3
    sql = compile_sql(q)
    assert sql.count(" OR ") >= 2
    assert has_limit(sql)


def test_limit_clause_always_appended() -> None:
    """
    < LIMIT is always appended when size is provided >
    1. Apply keyset paging with a non-empty cursor.
    2. Assert the resulting SQL contains LIMIT.
    """
    # 1
    stmt = select(User)
    order_cols = [User.id]
    cursor = {"id": 123}
    q = KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=2)

    # 2
    sql = compile_sql(q)
    assert has_limit(sql)


def test_col_key_and_strip_unary_helpers() -> None:
    """
    < _col_key extracts the base key and _strip_unary removes unary wrappers >
    1. Create a unary expression (User.id.desc()).
    2. Assert _col_key returns "id".
    3. Call _strip_unary on [unary, User.name].
    4. Assert the stripped columns preserve the underlying keys.
    """
    # 1
    u = User.id.desc()

    # 2
    key = KeysetStrategy._col_key(u)
    assert key == "id"

    # 3
    stripped = KeysetStrategy._strip_unary([u, User.name])

    # 4
    assert stripped[0].key == "id"
    assert stripped[1].key == "name"


def test_cursor_key_order_enforced_raises_on_swapped_keys() -> None:
    """
    < apply raises when cursor key insertion order does not match order_cols >
    1. Use order_cols = [User.id, User.name].
    2. Provide cursor with the same keys but inserted in swapped order.
    3. Assert ValueError is raised.
    """
    # 1
    stmt = select(User)
    order_cols = [
        cast(ColumnElement[Any], User.id),
        cast(ColumnElement[Any], User.name),
    ]

    # 2
    cursor: dict[str, Any] = {"name": "kim", "id": 1}

    # 3
    with pytest.raises(ValueError):
        KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=10)


def test_cursor_value_none_rejected() -> None:
    """
    < apply rejects cursor values of None >
    1. Use order_cols = [User.id].
    2. Provide cursor={"id": None}.
    3. Assert ValueError is raised.
    """
    # 1
    stmt = select(User)
    order_cols = [User.id]

    # 2
    cursor = {"id": None}

    # 3
    with pytest.raises(ValueError):
        KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=10)


def test_cursor_integer_casting_ok_from_string_single_column() -> None:
    """
    < apply casts numeric strings to int for Integer columns (single-column ASC) >
    1. Use order_cols = [User.id] (ASC by default).
    2. Provide cursor={"id": "123"}.
    3. Assert SQL includes WHERE and '>' and LIMIT, and does not use tuple comparison.
    """
    # 1
    stmt = select(User)
    order_cols = [User.id]

    # 2
    cursor = {"id": "123"}
    q = KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=5)

    # 3
    sql = compile_sql(q)
    assert not has_tuple_gt(sql)
    assert ">" in sql and has_where(sql) and has_limit(sql)


def test_cursor_integer_casting_fail_for_non_numeric_string() -> None:
    """
    < apply raises TypeError when numeric casting fails for an Integer column >
    1. Use order_cols = [User.id].
    2. Provide cursor={"id": "abc"}.
    3. Assert TypeError is raised.
    """
    # 1
    stmt = select(User)
    order_cols = [User.id]

    # 2
    cursor = {"id": "abc"}

    # 3
    with pytest.raises(TypeError):
        KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=5)


def test_type_casting_on_multiple_integer_columns_ok() -> None:
    """
    < apply casts numeric strings to int for Integer columns (multi-column all-ASC) >
    1. Use order_cols = [User.id, User.age] (both Integer, ASC by default).
    2. Provide cursor values as numeric strings.
    3. Assert tuple '>' comparison exists and WHERE/LIMIT are present.
    """
    # 1
    stmt = select(User)
    order_cols = [User.id, User.age]

    # 2
    cursor = {"id": "5", "age": "42"}
    q = KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=9)

    # 3
    sql = compile_sql(q)
    assert has_tuple_gt(sql)
    assert ">" in sql and has_where(sql) and has_limit(sql)


def test_type_casting_fail_on_second_integer_column() -> None:
    """
    < apply raises TypeError when casting fails for a later Integer column >
    1. Use order_cols = [User.id, User.age].
    2. Provide cursor where age is not castable to int.
    3. Assert TypeError is raised.
    """
    # 1
    stmt = select(User)
    order_cols = [User.id, User.age]

    # 2
    cursor = {"id": "10", "age": "x42"}

    # 3
    with pytest.raises(TypeError):
        KeysetStrategy.apply(stmt, order_cols=order_cols, cursor=cursor, size=4)


def test_strip_unary_length_mismatch_triggers_error() -> None:
    """
    < apply raises when extracted key length does not match order_cols length >
    1. Build order_cols with two columns and a matching cursor.
    2. Patch _strip_unary to return a list with the wrong length.
    3. Assert ValueError is raised with the expected message.
    """
    # 1
    order_cols: list[ColumnElement[Any]] = [column("a"), column("b")]
    stmt: Select[Any] = select(column("a"))
    cursor: dict[str, Any] = {"a": 1, "b": 2}

    # 2
    with patch.object(KeysetStrategy, "_strip_unary", return_value=[column("a")]):

        # 3
        with pytest.raises(ValueError, match="order_cols length does not match extracted key length"):
            KeysetStrategy.apply(
                stmt,
                order_cols=order_cols,
                cursor=cursor,
                size=10,
            )
