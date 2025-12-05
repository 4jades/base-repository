from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
  pass



class Item(Base):
  __tablename__ = "item"
  id: Mapped[int] = mapped_column(primary_key=True)
  name: Mapped[str] = mapped_column(String(50))



class Category(Base):
  __tablename__ = "category"
  id: Mapped[int] = mapped_column(primary_key=True)
  title: Mapped[str] = mapped_column(String(50))



class Result(Base):
  __tablename__ = "result"
  id: Mapped[int] = mapped_column(primary_key=True)
  item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
  sub_category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), nullable=True)
  result_value: Mapped[str | None]
  is_abnormal: Mapped[bool | None]
  tenant_id: Mapped[int]
  checkup_id: Mapped[int]

  item: Mapped[Item] = relationship()
  sub_category: Mapped[Category | None] = relationship()
