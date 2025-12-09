from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, List, overload

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Literal

from base_repository.base_filter import BaseRepoFilter
from base_repository.repo_types import NoSchema, QueryOrStmt, TModel, TPydanticSchema, TSchema


class BaseRepository(Generic[TModel, TSchema]):
    # =========================
    # execute
    # =========================
    @overload
    async def execute(
        self: "BaseRepository[TModel, NoSchema]",
        q_or_stmt: QueryOrStmt[TModel],
        *,
        session: AsyncSession | None = ...,
        convert_domain: bool | None = ...,
    ) -> List[TModel]: ...

    @overload
    async def execute(
        self: "BaseRepository[TModel, TPydanticSchema]",
        q_or_stmt: QueryOrStmt[TModel],
        *,
        session: AsyncSession | None = ...,
        convert_domain: None = ...,
    ) -> List[TPydanticSchema]: ...

    @overload
    async def execute(
        self: "BaseRepository[TModel, TPydanticSchema]",
        q_or_stmt: QueryOrStmt[TModel],
        *,
        session: AsyncSession | None = ...,
        convert_domain: Literal[False],
    ) -> List[TModel]: ...

    @overload
    async def execute(
        self: "BaseRepository[TModel, TPydanticSchema]",
        q_or_stmt: QueryOrStmt[TModel],
        *,
        session: AsyncSession | None = ...,
        convert_domain: Literal[True],
    ) -> List[TPydanticSchema]: ...

    @overload
    async def execute(
        self: "BaseRepository[TModel, TPydanticSchema]",
        q_or_stmt: QueryOrStmt[TModel],
        *,
        session: AsyncSession | None = ...,
        convert_domain: bool,
    ) -> List[TModel] | List[TPydanticSchema]: ...


    # =========================
    # get_list
    # =========================
    @overload
    async def get_list(
        self: "BaseRepository[TModel, NoSchema]",
        *,
        flt: BaseRepoFilter | None = ...,
        order_by: Sequence[Any] | None = ...,
        cursor: dict[str, Any] | None = ...,
        page: int | None = ...,
        size: int | None = ...,
        session: AsyncSession | None = ...,
        convert_domain: bool | None = ...,
    ) -> List[TModel]: ...

    @overload
    async def get_list(
        self: "BaseRepository[TModel, TPydanticSchema]",
        *,
        flt: BaseRepoFilter | None = ...,
        order_by: Sequence[Any] | None = ...,
        cursor: dict[str, Any] | None = ...,
        page: int | None = ...,
        size: int | None = ...,
        session: AsyncSession | None = ...,
        convert_domain: None = ...,
    ) -> List[TPydanticSchema]: ...

    @overload
    async def get_list(
        self: "BaseRepository[TModel, TPydanticSchema]",
        *,
        flt: BaseRepoFilter | None = ...,
        order_by: Sequence[Any] | None = ...,
        cursor: dict[str, Any] | None = ...,
        page: int | None = ...,
        size: int | None = ...,
        session: AsyncSession | None = ...,
        convert_domain: Literal[False],
    ) -> List[TModel]: ...

    @overload
    async def get_list(
        self: "BaseRepository[TModel, TPydanticSchema]",
        *,
        flt: BaseRepoFilter | None = ...,
        order_by: Sequence[Any] | None = ...,
        cursor: dict[str, Any] | None = ...,
        page: int | None = ...,
        size: int | None = ...,
        session: AsyncSession | None = ...,
        convert_domain: Literal[True],
    ) -> List[TPydanticSchema]: ...

    @overload
    async def get_list(
        self: "BaseRepository[TModel, TPydanticSchema]",
        *,
        flt: BaseRepoFilter | None = ...,
        order_by: Sequence[Any] | None = ...,
        cursor: dict[str, Any] | None = ...,
        page: int | None = ...,
        size: int | None = ...,
        session: AsyncSession | None = ...,
        convert_domain: bool,
    ) -> List[TModel] | List[TPydanticSchema]: ...


    # =========================
    # get
    # =========================
    @overload
    async def get(
        self: "BaseRepository[TModel, NoSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: bool | None = ...,
        session: AsyncSession | None = ...,
    ) -> TModel | None: ...

    @overload
    async def get(
        self: "BaseRepository[TModel, TPydanticSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: None = ...,
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema | None: ...

    @overload
    async def get(
        self: "BaseRepository[TModel, TPydanticSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: Literal[False],
        session: AsyncSession | None = ...,
    ) -> TModel | None: ...

    @overload
    async def get(
        self: "BaseRepository[TModel, TPydanticSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: Literal[True],
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema | None: ...

    @overload
    async def get(
        self: "BaseRepository[TModel, TPydanticSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: bool,
        session: AsyncSession | None = ...,
    ) -> TModel | TPydanticSchema | None: ...


    # =========================
    # get_or_fail
    # =========================
    @overload
    async def get_or_fail(
        self: "BaseRepository[TModel, NoSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: bool | None = ...,
        session: AsyncSession | None = ...,
    ) -> TModel: ...

    @overload
    async def get_or_fail(
        self: "BaseRepository[TModel, TPydanticSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: None = ...,
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema: ...

    @overload
    async def get_or_fail(
        self: "BaseRepository[TModel, TPydanticSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: Literal[False],
        session: AsyncSession | None = ...,
    ) -> TModel: ...

    @overload
    async def get_or_fail(
        self: "BaseRepository[TModel, TPydanticSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: Literal[True],
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema: ...

    @overload
    async def get_or_fail(
        self: "BaseRepository[TModel, TPydanticSchema]",
        flt: BaseRepoFilter,
        *,
        convert_domain: bool,
        session: AsyncSession | None = ...,
    ) -> TModel | TPydanticSchema: ...
