from __future__ import annotations
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from base_repository.base_filter import BaseRepoFilter
from base_repository.repository.base_repo import BaseRepository


# =========================
# SQLAlchemy ORM Model
# =========================
class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


# =========================
# Pydantic Domain Schema
# =========================
class UserDomain(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str

@dataclass
class UserFilter(BaseRepoFilter):
    id: int | None = None
    name: str | None = None

class UserRepo(BaseRepository[UserModel, UserDomain]):
    filter_class=UserFilter

user_repo = UserRepo()

async def get_user_by_id(id: int) -> UserDomain | None:
    user_domain = await user_repo.get(UserFilter(id=id))

    return user_domain


async def get_user_by_id_domain(id: int) -> UserDomain | None:
    user_domain = await user_repo.get(UserFilter(id=id), convert_domain=True)

    return user_domain


async def get_user_by_id_orm(id: int) -> UserModel | None:
    user_model = await user_repo.get(UserFilter(id=id), convert_domain=False)

    return user_model


"""
------------------------------------------------------------------------------------------
"""

class PostModel(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

@dataclass
class PostFilter(BaseRepoFilter):
    id: int | None = None
    name: str | None = None

class PostRepo(BaseRepository[PostModel]):
    filter_class=PostFilter



post_repo = PostRepo()

async def get_post_by_id(id: int) -> PostModel | None:
    post_model = await post_repo.get(PostFilter(id=id), convert_domain=True)

    return post_model