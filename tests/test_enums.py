import pytest
from sqlalchemy import column, delete, insert, select, table, update

from base_repository.enums import StatementType


def _t():
    return table("t", column("id"), column("name"))


def test_from_stmt_select() -> None:
    stmt = select(_t())
    assert StatementType.from_stmt(stmt) == StatementType.SELECT


def test_from_stmt_insert() -> None:
    stmt = insert(_t()).values(id=1)
    assert StatementType.from_stmt(stmt) == StatementType.INSERT


def test_from_stmt_update() -> None:
    stmt = update(_t()).where(_t().c.id == 1).values(name="x")
    assert StatementType.from_stmt(stmt) == StatementType.UPDATE


def test_from_stmt_delete() -> None:
    stmt = delete(_t()).where(_t().c.id == 1)
    assert StatementType.from_stmt(stmt) == StatementType.DELETE


def test_from_stmt_unsupported() -> None:
    with pytest.raises(TypeError):
        StatementType.from_stmt(object())


def test_strenum_is_str_like() -> None:
    assert StatementType.SELECT == "select"
    assert str(StatementType.SELECT) == "select"
    assert StatementType.SELECT.value == "select"
    assert StatementType.SELECT.name == "SELECT"
    assert isinstance(StatementType.SELECT, str)
