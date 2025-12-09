from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Generic, List, overload

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapper
from typing_extensions import Literal

from base_repository.base_filter import BaseRepoFilter
from base_repository.base_mapper import BaseMapper
from base_repository.query.list_query import ListQuery
from base_repository.repo_types import NoSchema, QueryOrStmt, TModel, TPydanticSchema, TSchema
from base_repository.session_provider import SessionProvider


class BaseRepository(Generic[TModel, TSchema]):
    # =========================
    # class configuration fields
    # =========================
    _session_provider: SessionProvider | None

    model: type[TModel]
    mapping_schema: type[TSchema] | None
    filter_class: type[BaseRepoFilter]
    mapper: type[BaseMapper] | None
    _default_convert_domain: bool

    # =========================
    # instance attributes
    # =========================
    _specific_session: AsyncSession | None
    sa_mapper: Mapper[Any]
    _mapper_instance: BaseMapper | None

    # =========================
    # lifecycle
    # =========================
    def __init_subclass__(cls, **kwargs: Any) -> None: ...

    def __init__(
        self,
        session: AsyncSession | None = ...,
        *,
        mapper: BaseMapper | None = ...,
        default_convert_domain: bool | None = ...,
    ) -> None: ...

    # =========================
    # session
    # =========================
    @classmethod
    def configure_session_provider(cls, provider: SessionProvider) -> None: ...

    @property
    def session(self) -> AsyncSession: ...

    def _resolve_session(self, session: AsyncSession | None) -> AsyncSession: ...

    # =========================
    # internal helpers (typed for tests / subclassing)
    # =========================
    def _validate_mapper_integrity(self, mapper_instance: BaseMapper) -> None: ...

    def _validate_schema_against_model(self, schema: type[BaseModel]) -> None: ...

    def _autoinc_pk_keys(self) -> set[str]: ...

    def _schema_payload(self, data: BaseModel | Mapping[str, Any]) -> dict[str, Any]: ...

    def _schema_to_orm(self, data: BaseModel | Mapping[str, Any]) -> TModel: ...

    @overload
    def _convert(
        self: "BaseRepository[TModel, NoSchema]",
        row: TModel,
        *,
        convert_domain: bool | None = ...,
    ) -> TModel: ...

    @overload
    def _convert(
        self: "BaseRepository[TModel, TPydanticSchema]",
        row: TModel,
        *,
        convert_domain: None = ...,
    ) -> TPydanticSchema: ...

    @overload
    def _convert(
        self: "BaseRepository[TModel, TPydanticSchema]",
        row: TModel,
        *,
        convert_domain: Literal[False],
    ) -> TModel: ...

    @overload
    def _convert(
        self: "BaseRepository[TModel, TPydanticSchema]",
        row: TModel,
        *,
        convert_domain: Literal[True],
    ) -> TPydanticSchema: ...

    @overload
    def _convert(
        self: "BaseRepository[TModel, TPydanticSchema]",
        row: TModel,
        *,
        convert_domain: bool,
    ) -> TModel | TPydanticSchema: ...

    # =========================
    # list (DSL entrypoint)
    # =========================
    def list(self, flt: BaseRepoFilter | None = ...) -> ListQuery[TModel]: ...

    # =========================
    # execute (existing overloads)
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
    # get_list (existing overloads)
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
    # get (existing overloads)
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
    # get_or_fail (existing overloads)
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

    # =========================
    # count, delete
    # =========================
    async def count(self, flt: BaseRepoFilter | None = ..., *, session: AsyncSession | None = ...) -> int: ...

    async def delete(self, flt: BaseRepoFilter, *, session: AsyncSession | None = ...) -> int: ...

    # =========================
    # add, add_all
    # =========================
    def add(self, obj: TModel, *, session: AsyncSession | None = ...) -> None: ...

    def add_all(self, objs: Sequence[TModel], *, session: AsyncSession | None = ...) -> None: ...

    # =========================
    # create
    # =========================
    @overload
    async def create(
        self: "BaseRepository[TModel, NoSchema]",
        data: BaseModel | Mapping[str, Any],
        *,
        convert_domain: bool | None = ...,
        session: AsyncSession | None = ...,
    ) -> TModel: ...

    @overload
    async def create(
        self: "BaseRepository[TModel, TPydanticSchema]",
        data: BaseModel | Mapping[str, Any],
        *,
        convert_domain: None = ...,
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema: ...

    @overload
    async def create(
        self: "BaseRepository[TModel, TPydanticSchema]",
        data: BaseModel | Mapping[str, Any],
        *,
        convert_domain: Literal[False],
        session: AsyncSession | None = ...,
    ) -> TModel: ...

    @overload
    async def create(
        self: "BaseRepository[TModel, TPydanticSchema]",
        data: BaseModel | Mapping[str, Any],
        *,
        convert_domain: Literal[True],
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema: ...

    @overload
    async def create(
        self: "BaseRepository[TModel, TPydanticSchema]",
        data: BaseModel | Mapping[str, Any],
        *,
        convert_domain: bool,
        session: AsyncSession | None = ...,
    ) -> TModel | TPydanticSchema: ...

    # =========================
    # create_many
    # =========================
    @overload
    async def create_many(
        self: "BaseRepository[TModel, NoSchema]",
        items: Sequence[BaseModel | Mapping[str, Any]],
        *,
        convert_domain: bool | None = ...,
        session: AsyncSession | None = ...,
        skip_convert: bool = ...,
    ) -> List[TModel]: ...

    @overload
    async def create_many(
        self: "BaseRepository[TModel, TPydanticSchema]",
        items: Sequence[BaseModel | Mapping[str, Any]],
        *,
        convert_domain: bool | None = ...,
        session: AsyncSession | None = ...,
        skip_convert: Literal[True],
    ) -> List[TModel]: ...

    @overload
    async def create_many(
        self: "BaseRepository[TModel, TPydanticSchema]",
        items: Sequence[BaseModel | Mapping[str, Any]],
        *,
        convert_domain: None = ...,
        session: AsyncSession | None = ...,
        skip_convert: Literal[False] = ...,
    ) -> List[TPydanticSchema]: ...

    @overload
    async def create_many(
        self: "BaseRepository[TModel, TPydanticSchema]",
        items: Sequence[BaseModel | Mapping[str, Any]],
        *,
        convert_domain: Literal[False],
        session: AsyncSession | None = ...,
        skip_convert: Literal[False] = ...,
    ) -> List[TModel]: ...

    @overload
    async def create_many(
        self: "BaseRepository[TModel, TPydanticSchema]",
        items: Sequence[BaseModel | Mapping[str, Any]],
        *,
        convert_domain: Literal[True],
        session: AsyncSession | None = ...,
        skip_convert: Literal[False] = ...,
    ) -> List[TPydanticSchema]: ...

    @overload
    async def create_many(
        self: "BaseRepository[TModel, TPydanticSchema]",
        items: Sequence[BaseModel | Mapping[str, Any]],
        *,
        convert_domain: bool,
        session: AsyncSession | None = ...,
        skip_convert: Literal[False] = ...,
    ) -> List[TModel] | List[TPydanticSchema]: ...

    # =========================
    # create_from_model
    # =========================
    @overload
    async def create_from_model(
        self: "BaseRepository[TModel, NoSchema]",
        obj: TModel,
        *,
        convert_domain: bool | None = ...,
        session: AsyncSession | None = ...,
    ) -> TModel: ...

    @overload
    async def create_from_model(
        self: "BaseRepository[TModel, TPydanticSchema]",
        obj: TModel,
        *,
        convert_domain: None = ...,
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema: ...

    @overload
    async def create_from_model(
        self: "BaseRepository[TModel, TPydanticSchema]",
        obj: TModel,
        *,
        convert_domain: Literal[False],
        session: AsyncSession | None = ...,
    ) -> TModel: ...

    @overload
    async def create_from_model(
        self: "BaseRepository[TModel, TPydanticSchema]",
        obj: TModel,
        *,
        convert_domain: Literal[True],
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema: ...

    @overload
    async def create_from_model(
        self: "BaseRepository[TModel, TPydanticSchema]",
        obj: TModel,
        *,
        convert_domain: bool,
        session: AsyncSession | None = ...,
    ) -> TModel | TPydanticSchema: ...

    # =========================
    # update (bulk SQL UPDATE)
    # =========================
    async def update(
        self,
        flt: BaseRepoFilter,
        update: Mapping[str, Any] | BaseModel,
        session: AsyncSession | None = ...,
    ) -> int: ...

    # =========================
    # update_from_model (dirty checking)
    # =========================
    @overload
    async def update_from_model(
        self: "BaseRepository[TModel, NoSchema]",
        base: TModel,
        update: Mapping[str, Any] | BaseModel,
        *,
        convert_domain: bool | None = ...,
        session: AsyncSession | None = ...,
    ) -> TModel: ...

    @overload
    async def update_from_model(
        self: "BaseRepository[TModel, TPydanticSchema]",
        base: TModel,
        update: Mapping[str, Any] | BaseModel,
        *,
        convert_domain: None = ...,
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema: ...

    @overload
    async def update_from_model(
        self: "BaseRepository[TModel, TPydanticSchema]",
        base: TModel,
        update: Mapping[str, Any] | BaseModel,
        *,
        convert_domain: Literal[False],
        session: AsyncSession | None = ...,
    ) -> TModel: ...

    @overload
    async def update_from_model(
        self: "BaseRepository[TModel, TPydanticSchema]",
        base: TModel,
        update: Mapping[str, Any] | BaseModel,
        *,
        convert_domain: Literal[True],
        session: AsyncSession | None = ...,
    ) -> TPydanticSchema: ...

    @overload
    async def update_from_model(
        self: "BaseRepository[TModel, TPydanticSchema]",
        base: TModel,
        update: Mapping[str, Any] | BaseModel,
        *,
        convert_domain: bool,
        session: AsyncSession | None = ...,
    ) -> TModel | TPydanticSchema: ...
