from __future__ import annotations

import enum
import re
import sys
from typing import Any

import pytest
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    asc,
    func,
    literal_column,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, aliased, relationship
from sqlalchemy.sql.elements import UnaryExpression

from base_repository.query.strategies.order_by import OrderByStrategy
import base_repository.query.strategies.order_by as order_by_mod


# Base ORM setup for tests
class Base(DeclarativeBase):
    pass

# Test model: User (single PK)
class User(Base):
    __tablename__ = "user"

    id = Column("id", Integer, primary_key=True)
    name = Column("name", String(50), nullable=False)
    org_id = Column("org_id", Integer, nullable=False)

    posts = relationship("Post", back_populates="user")

# Test model: Post (FK to User)
class Post(Base):
    __tablename__ = "post"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    title = Column(String(100), nullable=False)

    user = relationship("User", back_populates="posts")

# Test model: Composite primary key
class CompositePK(Base):
    __tablename__ = "composite_pk"

    tenant_id = Column(Integer, primary_key=True)
    item_id = Column(Integer, primary_key=True)
    value = Column(String(20), nullable=False)

# Enum inputs for order_by
class UserOrder(enum.Enum):
    ID = "id"
    NAME = "name"
    ORG = "org_id"


# -------------------------------
# Utils
# -------------------------------
def compile_sql(stmt) -> str:
    """
    < Compile SQLAlchemy statement into a string for assertions >
    1. Convert the statement to a string (dialect differences are tolerated).
    2. Return the compiled text.
    """
    # 1
    return str(stmt)


def order_clause(sql: str) -> str:
    """
    < Extract ORDER BY clause substring from a compiled SQL string >
    1. Find "ORDER BY" and capture everything after it.
    2. Return the captured part (trimmed), or empty string if not present.
    """
    # 1
    m = re.search(r"\bORDER BY\b(.+)$", sql, re.IGNORECASE)

    # 2
    return (m.group(1).strip() if m else "").strip()


# -------------------------------
# Tests
# -------------------------------
def test_string_key_normalizes_to_column() -> None:
    """
    < Accept a string key and normalize it to a model column >
    1. Pass ["id"] to OrderByStrategy.apply.
    2. Ensure one ORDER BY item is returned.
    3. Ensure the generated ORDER BY does not contain DESC.
    """
    # 1
    cols = OrderByStrategy.apply(User, ["id"])

    # 2
    assert len(cols) == 1

    # 3
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert "id" in oc and "DESC" not in oc


def test_enum_value_normalizes_to_column() -> None:
    """
    < Accept an Enum value (string-backed) and normalize it to a model column >
    1. Pass [UserOrder.ID] to OrderByStrategy.apply.
    2. Ensure one ORDER BY item is returned.
    3. Ensure the generated ORDER BY does not contain DESC.
    """
    # 1
    cols = OrderByStrategy.apply(User, [UserOrder.ID])

    # 2
    assert len(cols) == 1

    # 3
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert "id" in oc and "DESC" not in oc


def test_instrumented_attribute_is_allowed() -> None:
    """
    < Accept an InstrumentedAttribute (User.id) as an order_by item >
    1. Pass [User.id] to OrderByStrategy.apply.
    2. Ensure one ORDER BY item is returned.
    3. Ensure the generated ORDER BY contains the column reference.
    """
    # 1
    cols = OrderByStrategy.apply(User, [User.id])

    # 2
    assert len(cols) == 1

    # 3
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert "user.id" in oc or "id" in oc


def test_unary_expression_preserves_direction_desc() -> None:
    """
    < Preserve direction for UnaryExpression (DESC) >
    1. Pass [User.id.desc()] to OrderByStrategy.apply.
    2. Ensure the result is UnaryExpression.
    3. Ensure is_desc() is True.
    4. Ensure SQL ORDER BY includes DESC.
    """
    # 1
    cols = OrderByStrategy.apply(User, [User.id.desc()])

    # 2
    assert len(cols) == 1
    assert isinstance(cols[0], UnaryExpression)

    # 3
    assert OrderByStrategy.is_desc(cols[0]) is True

    # 4
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert re.search(r"\bid\b.*\bDESC\b", oc, re.IGNORECASE)


def test_unary_expression_preserves_direction_asc() -> None:
    """
    < Preserve direction for UnaryExpression (ASC) >
    1. Pass [User.name.asc()] to OrderByStrategy.apply.
    2. Ensure the result is UnaryExpression.
    3. Ensure is_desc() is False.
    4. Ensure SQL ORDER BY does not contain DESC for that field.
    """
    # 1
    cols = OrderByStrategy.apply(User, [User.name.asc()])

    # 2
    assert len(cols) == 1
    assert isinstance(cols[0], UnaryExpression)

    # 3
    assert OrderByStrategy.is_desc(cols[0]) is False

    # 4
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert re.search(r"\bname\b(?!.*DESC)", oc, re.IGNORECASE)


def test_mixed_inputs_are_normalized_and_validated() -> None:
    """
    < Normalize mixed input types and validate them against the model >
    1. Apply mixed inputs: string, UnaryExpression, Enum.
    2. Ensure all inputs are accepted and returned in order.
    3. Ensure DESC is present only where requested.
    """
    # 1
    cols = OrderByStrategy.apply(User, ["id", User.name.desc(), UserOrder.ORG])

    # 2
    assert len(cols) == 3

    # 3
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert re.search(r"\bid\b(?![^,]*DESC)", oc, re.IGNORECASE)
    assert re.search(r"\bname\b[^,]*\bDESC\b", oc, re.IGNORECASE)
    assert re.search(r"\borg_id\b(?![^,]*DESC)", oc, re.IGNORECASE)


def test_duplicates_collapse_to_first_entry() -> None:
    """
    < Collapse duplicates to the first occurrence >
    1. Provide the same underlying column via different representations.
    2. Ensure only one order_by element remains.
    3. Ensure the remaining one corresponds to the first directive (ASC by default here).
    """
    # 1
    cols = OrderByStrategy.apply(User, ["id", User.id.desc(), UserOrder.ID, User.id.asc()])

    # 2
    assert len(cols) == 1

    # 3
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert re.search(r"\bid\b(?!.*DESC)", oc, re.IGNORECASE)


def test_invalid_string_field_raises() -> None:
    """
    < Reject invalid string field names >
    1. Pass a non-existent field key.
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, ["does_not_exist"])


def test_invalid_enum_value_raises() -> None:
    """
    < Reject invalid Enum values that do not map to model fields >
    1. Define a Bad Enum with a non-existent column key.
    2. Assert ValueError.
    """
    # 1
    class Bad(enum.Enum):
        BAD = "does_not_exist"

    # 2
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [Bad.BAD])


def test_invalid_enum_non_string_value_rejected() -> None:
    """
    < Reject Enum values that are not string-backed >
    1. Define an Enum whose value is not a str.
    2. Assert ValueError.
    """
    # 1
    class BadE(enum.Enum):
        BAD = 999

    # 2
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [BadE.BAD])


def test_unsupported_input_type_raises() -> None:
    """
    < Reject unsupported item types in order_by list >
    1. Pass a plain integer.
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [123])


def test_order_items_must_be_a_list_like() -> None:
    """
    < Reject non-list-like order_by input >
    1. Pass a string instead of a list/tuple.
    2. Assert TypeError.
    """
    # 1
    with pytest.raises(TypeError):
        OrderByStrategy.apply(User, "id")


def test_text_clause_is_rejected() -> None:
    """
    < Reject TextClause inputs >
    1. Pass [text("id")].
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [text("id")])


def test_function_element_is_rejected() -> None:
    """
    < Reject FunctionElement inputs >
    1. Pass [func.lower(User.name)].
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [func.lower(User.name)])


def test_pk_fallback_default_when_order_is_none_single_pk() -> None:
    """
    < Default to primary key ordering when order_by is None (single PK) >
    1. Pass None as order_by.
    2. Ensure one column is returned.
    3. Ensure ORDER BY contains the PK.
    """
    # 1
    cols = OrderByStrategy.apply(User, None)

    # 2
    assert len(cols) == 1

    # 3
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert "id" in oc


def test_pk_fallback_default_when_order_is_none_composite_pk() -> None:
    """
    < Default to primary key ordering when order_by is None (composite PK) >
    1. Pass None as order_by.
    2. Ensure composite PK columns are used.
    3. Ensure ORDER BY contains both PK columns.
    """
    # 1
    cols = OrderByStrategy.apply(CompositePK, None)

    # 2
    assert len(cols) == 2

    # 3
    sql = compile_sql(select(CompositePK).order_by(*cols))
    oc = order_clause(sql)
    assert re.search(r"\btenant_id\b", oc)
    assert re.search(r"\bitem_id\b", oc)


def test_is_desc_helper() -> None:
    """
    < is_desc helper behavior >
    1. DESC UnaryExpression returns True.
    2. ASC UnaryExpression returns False.
    3. Raw column returns False.
    """
    # 1
    assert OrderByStrategy.is_desc(User.id.desc()) is True

    # 2
    assert OrderByStrategy.is_desc(User.id.asc()) is False

    # 3
    assert OrderByStrategy.is_desc(User.id) is False


def test_rejects_instrumented_attribute_from_another_model() -> None:
    """
    < Reject InstrumentedAttribute belonging to another model >
    1. Pass Post.id while model=User.
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [Post.id])


def test_unary_instrumented_attribute_from_other_model_rejected() -> None:
    """
    < Reject UnaryExpression whose inner InstrumentedAttribute belongs to another model >
    1. Manually construct UnaryExpression with element=Post.id.
    2. Assert ValueError.
    """
    # 1
    ue = object.__new__(UnaryExpression)
    object.__setattr__(ue, "element", Post.id)

    # 2
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [ue])


def test_unary_text_clause_is_rejected() -> None:
    """
    < Reject UnaryExpression built from TextClause >
    1. Create asc(text("name")).
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [asc(text("name"))])


def test_unary_function_element_is_rejected() -> None:
    """
    < Reject UnaryExpression built from FunctionElement >
    1. Provide func.now().desc().
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [func.now().desc()])


def test_aliased_attributes_are_rejected() -> None:
    """
    < Reject aliased(User) attributes and their expression forms >
    1. Create UA = aliased(User).
    2. Reject UA.id (InstrumentedAttribute for aliased mapper).
    3. Reject UA.id.desc() (UnaryExpression).
    4. Reject UA.id.expression (ColumnElement).
    """
    # 1
    UA = aliased(User)

    # 2
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [UA.id])

    # 3
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [UA.id.desc()])

    # 4
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [UA.id.expression])


def test_literal_column_is_rejected() -> None:
    """
    < Reject literal_column >
    1. Provide literal_column("user.id").
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [literal_column("user.id")])


def test_relationship_attribute_is_rejected() -> None:
    """
    < Reject relationship attributes as order_by inputs >
    1. Provide [User.posts].
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [User.posts])


def test_label_is_rejected_both_plain_and_unary() -> None:
    """
    < Reject labeled columns (both plain and unary) >
    1. Reject User.id.label("x").
    2. Reject User.id.label("x").desc().
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [User.id.label("x")])

    # 2
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [User.id.label("x").desc()])


def test_binary_expression_is_rejected() -> None:
    """
    < Reject binary expressions as order_by inputs >
    1. Provide [User.id + 1].
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [User.id + 1])


def test_none_inside_order_list_is_rejected() -> None:
    """
    < Reject None inside order_by list >
    1. Provide ["id", None, "name"].
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, ["id", None, "name"])


# 1
# Helper class used to ensure "value attribute but not Enum" is rejected
class FakeWithValue:
    value = "id"


def test_non_enum_with_value_attr_is_rejected() -> None:
    """
    < Reject objects that only look like Enum (have .value) >
    1. Provide [FakeWithValue()].
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [FakeWithValue()])


def test_column_element_same_model_is_allowed() -> None:
    """
    < Accept a ColumnElement that belongs to the same model >
    1. Provide [User.id.expression].
    2. Ensure one column is returned.
    3. Ensure ORDER BY contains the field.
    """
    # 1
    cols = OrderByStrategy.apply(User, [User.id.expression])

    # 2
    assert len(cols) == 1

    # 3
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert re.search(r"\bid\b(?!.*DESC)", oc, re.IGNORECASE)


def test_column_element_other_model_is_rejected() -> None:
    """
    < Reject a ColumnElement belonging to another model >
    1. Provide [Post.id.expression] while model=User.
    2. Assert ValueError.
    """
    # 1
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [Post.id.expression])


def test_unary_relationship_attribute_rejected_via_manual_unary_expression() -> None:
    """
    < Reject UnaryExpression whose inner is a relationship attribute >
    1. Manually construct UnaryExpression with element=User.posts (relationship attribute).
    2. Assert ValueError.
    """
    # 1
    ue = object.__new__(UnaryExpression)
    object.__setattr__(ue, "element", User.posts)

    # 2
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [ue])


def test_unary_binary_expression_with_no_key_hits_missing_field_branch() -> None:
    """
    < Cover branch: UnaryExpression inner has no usable key/name and triggers missing-field error >
    1. Create a BinaryExpression via (User.id + 1).
    2. Apply .desc() to make it a UnaryExpression.
    3. Assert ValueError contains "does not have a field".
    """
    # 1
    # 2
    with pytest.raises(ValueError) as exc:
        OrderByStrategy.apply(User, [(User.id + 1).desc()])

    # 3
    assert "does not have a field" in str(exc.value)


def test_apply_raises_when_model_has_no_pk_for_default(monkeypatch) -> None:
    """
    < Force the "model must have a primary key" branch by monkeypatching sa_mapper >
    1. Provide a FakeMapper with empty primary_key.
    2. monkeypatch order_by_mod.sa_mapper to return FakeMapper.
    3. Call OrderByStrategy.apply(User, None) to trigger pk fallback.
    4. Assert ValueError message contains "must have a primary key".
    """
    # 1
    class FakeMapper:
        column_attrs: list[Any] = []
        primary_key: list[Any] = []

    # 2
    def fake_sa_mapper(_model):
        return FakeMapper()

    monkeypatch.setattr(order_by_mod, "sa_mapper", fake_sa_mapper)

    # 3
    with pytest.raises(ValueError) as exc:
        OrderByStrategy.apply(User, None)

    # 4
    assert "must have a primary key" in str(exc.value)


def test_same_column_compare_exception_then_proxy_set_true() -> None:
    """
    < _same_column returns True via proxy_set even if compare() raises >
    1. Create an object A whose compare() raises.
    2. Ensure A.proxy_set contains b.
    3. Assert _same_column(A(), b) is True.
    """
    # 1
    class B:
        pass

    b = B()

    class A:
        def compare(self, _other):
            raise RuntimeError("boom")

        @property
        def proxy_set(self):
            return {b}

    # 2
    # 3
    assert OrderByStrategy._same_column(A(), b) is True


def test_same_column_recursive_element_path_true() -> None:
    """
    < _same_column returns True via element recursion path >
    1. Create Inner that exposes proxy_set containing b.
    2. Create Outer whose element returns Inner.
    3. Assert _same_column(Outer(), b) is True.
    """
    # 1
    class B:
        pass

    b = B()

    class Inner:
        def compare(self, _other):
            return False

        @property
        def proxy_set(self):
            return {b}

    # 2
    class Outer:
        def compare(self, _other):
            return False

        @property
        def proxy_set(self):
            return set()

        @property
        def element(self):
            return Inner()

    # 3
    assert OrderByStrategy._same_column(Outer(), b) is True


def test_same_column_recursionerror_breaks_and_returns_false() -> None:
    """
    < _same_column returns False when recursion over element causes RecursionError >
    1. Lower recursion limit to make self-referential element recursion fail fast.
    2. Create Loop whose element returns itself.
    3. Assert _same_column(Loop(), b) is False.
    4. Restore recursion limit.
    """
    # 1
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(80)
    try:
        # 2
        class B:
            pass

        b = B()

        class Loop:
            def compare(self, _other):
                return False

            @property
            def proxy_set(self):
                return set()

            @property
            def element(self):
                return self

        # 3
        assert OrderByStrategy._same_column(Loop(), b) is False
    finally:
        # 4
        sys.setrecursionlimit(old)


def test_same_table_none_tables_are_false() -> None:
    """
    < _same_table returns False if both sides have table=None >
    1. Create two objects with table=None.
    2. Assert _same_table returns False.
    """
    # 1
    class X:
        table: Any | None = None

    class Y:
        table: Any | None = None

    # 2
    assert OrderByStrategy._same_table(X(), Y()) is False


def test_same_column_false_triggers_error_for_both_unary_and_column_element(monkeypatch) -> None:
    """
    < Force error branch when _same_table is True but _same_column is False >
    1. monkeypatch _same_table to always return True.
    2. monkeypatch _same_column to always return False.
    3. Call apply() with UnaryExpression(ColumnElement) path and assert ValueError.
    4. Call apply() with ColumnElement path and assert ValueError.
    """
    # 1
    monkeypatch.setattr(OrderByStrategy, "_same_table", lambda _a, _b: True)

    # 2
    monkeypatch.setattr(OrderByStrategy, "_same_column", lambda _a, _b: False)

    # 3
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [User.id.expression.desc()])

    # 4
    with pytest.raises(ValueError):
        OrderByStrategy.apply(User, [User.id.expression])


def test_unary_instrumented_attribute_success_preserves_direction() -> None:
    """
    < UnaryExpression with InstrumentedAttribute inner preserves direction and is appended as-is >
    1. Manually construct UnaryExpression with element=User.id.
    2. Set modifier to desc_op so is_desc() becomes True.
    3. Apply and ensure the UnaryExpression object itself is returned.
    4. Assert is_desc() is True.
    """
    # 1
    ue = object.__new__(UnaryExpression)
    object.__setattr__(ue, "element", User.id)

    # 2
    object.__setattr__(ue, "modifier", order_by_mod.operators.desc_op)

    # 3
    cols = OrderByStrategy.apply(User, [ue])
    assert len(cols) == 1
    assert cols[0] is ue
    assert isinstance(cols[0], UnaryExpression)

    # 4
    assert OrderByStrategy.is_desc(cols[0]) is True


def test_unary_column_element_success_preserves_direction() -> None:
    """
    < UnaryExpression with ColumnElement inner preserves direction and is appended as-is >
    1. Create UnaryExpression via User.id.expression.desc().
    2. Apply and ensure UnaryExpression is returned.
    3. Assert is_desc() is True.
    4. Assert ORDER BY contains DESC for id.
    """
    # 1
    cols = OrderByStrategy.apply(User, [User.id.expression.desc()])

    # 2
    assert len(cols) == 1
    assert isinstance(cols[0], UnaryExpression)

    # 3
    assert OrderByStrategy.is_desc(cols[0]) is True

    # 4
    sql = compile_sql(select(User).order_by(*cols))
    oc = order_clause(sql)
    assert re.search(r"\bid\b[^,]*\bDESC\b", oc, re.IGNORECASE)


def test_unary_expression_with_unknown_inner_hits_final_unsupported_branch() -> None:
    """
    < UnaryExpression with unknown inner hits final unsupported branch >
    1. Create a custom inner object that is not InstrumentedAttribute, ColumnElement, FunctionElement, or TextClause.
    2. Manually construct UnaryExpression with element=WeirdInner().
    3. Assert ValueError matches "Unsupported order_by input type:".
    """
    # 1
    class WeirdInner:
        pass

    # 2
    ue = object.__new__(UnaryExpression)
    object.__setattr__(ue, "element", WeirdInner())

    # 3
    with pytest.raises(ValueError, match=r"Unsupported order_by input type:"):
        OrderByStrategy.apply(User, [ue])
