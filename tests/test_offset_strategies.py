from __future__ import annotations

import pytest
from sqlalchemy import Integer, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from base_repository.query.strategies.offset import OffsetStrategy



class Base(DeclarativeBase):
    pass


class M(Base):
    __tablename__ = "m_offset_strategy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


def test_offset_strategy_apply_raises_when_page_is_less_than_one() -> None:
    """
    < OffsetStrategy.apply must reject invalid page values >
    1. Build a simple SELECT statement.
    2. Call apply() with page=0.
    3. Assert ValueError with the expected message.
    """
    stmt = select(M)
    with pytest.raises(ValueError, match=r"page must be >= 1\."):
        _ = OffsetStrategy.apply(stmt, page=0, size=10)


def test_offset_strategy_apply_raises_when_size_is_less_than_one() -> None:
    """
    < OffsetStrategy.apply must reject invalid size values >
    1. Build a simple SELECT statement.
    2. Call apply() with size=0.
    3. Assert ValueError with the expected message.
    """
    stmt = select(M)
    with pytest.raises(ValueError, match=r"size must be >= 1\."):
        _ = OffsetStrategy.apply(stmt, page=1, size=0)


def test_offset_strategy_apply_sets_offset_and_limit_correctly() -> None:
    """
    < OffsetStrategy.apply must compute and apply offset/limit correctly >
    1. Build a SELECT statement.
    2. Apply paging with page=3, size=10 -> offset=(3-1)*10=20, limit=10.
    3. Assert:
       - the compiled SQL contains OFFSET 20 and LIMIT 10.
    """
    stmt = select(M)
    out = OffsetStrategy.apply(stmt, page=3, size=10)

    sql = str(out.compile(compile_kwargs={"literal_binds": True})).upper()

    assert "OFFSET 20" in sql
    assert "LIMIT 10" in sql
