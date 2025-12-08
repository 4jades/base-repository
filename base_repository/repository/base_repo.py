from __future__ import annotations

import builtins
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Generic, cast, get_args

from pydantic import BaseModel
from sqlalchemy import Integer, Update, delete, func, select
from sqlalchemy import update as sa_update
from sqlalchemy.engine import ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapper
from sqlalchemy.sql import Select
from typing_extensions import Doc

from base_repository.base_filter import BaseRepoFilter
from base_repository.base_mapper import BaseMapper
from base_repository.query.converter import query_to_stmt
from base_repository.query.list_query import ListQuery
from base_repository.repo_types import QueryOrStmt, TModel
from base_repository.sa_helper import sa_mapper
from base_repository.session_provider import SessionProvider
from base_repository.validator import validate_schema_base


class BaseRepository(Generic[TModel]):
    """
    Safe single-model **Repository** base implementation.

    Principles
    ----------
    - **Single-model oriented design**: the default API assumes a single-model CRUD flow.
    (However, `execute()` can run a user-provided SQLAlchemy `Select` as-is, so joins are not strictly blocked in code.)
    - **Schema validation (Strict: required subset)**: when `mapping_schema` is set, its *required* fields must exist on
    the model's **columns (column_attrs)**. (required fields set ⊆ column key set)
    - **Conversion priority**:
        1) If `mapper(BaseMapper)` is provided, `to_domain` / `to_orm` is used first
        2) Otherwise, convert via Pydantic `model_validate(...)`
        (`mapping_schema.model_config.from_attributes=True` is enforced by `validate_schema_base()`.)
    """


    _session_provider: SessionProvider | None = None

    # Class configuration fields (to be set by subclasses)
    model: Annotated[
        type[TModel],
        Doc(
            "Target SQLAlchemy ORM model class. Usually inferred from the generic type argument, "
            "but can be explicitly declared in the subclass."
        ),
    ]
    filter_class: Annotated[
        type[BaseRepoFilter],
        Doc("Filter class for building default WHERE criteria. Dataclass-based filters are recommended."),
    ]
    mapping_schema: Annotated[
        type[BaseModel] | None,
        Doc("Pydantic schema used for ORM↔Domain conversion. Must pass 'column-only' validation rules."),
    ] = None
    mapper: Annotated[
        type[BaseMapper[TModel, BaseModel]] | None,
        Doc("Optional mapper class. If provided, it will take precedence for domain/ORM conversions."),
    ] = None

    _default_convert_domain: Annotated[
        bool,
        Doc("Default return type flag. True returns Domain(Pydantic) by default, False returns ORM objects."),
    ] = False


    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        Hook automatically invoked when a subclass is declared.

        Behavior
        --------
        1) Resolve the ORM model class from the generic argument (or an explicit `model` attribute).
        2) If `mapping_schema` is provided, validate the schema basics (BaseModel + from_attributes).
        - The required-subset check against actual model columns is performed at instance initialization time.
        3) If the schema is valid at class level, set `_default_convert_domain=True`.
        """
        super().__init_subclass__(**kwargs)

        # Infer `model` from the generic parameter
        if not hasattr(cls, "model"):
            for base in getattr(cls, "__orig_bases__", []):
                if hasattr(base, "__args__"):
                    cls.model = get_args(base)[0]

        if getattr(cls, "mapping_schema", None) is not None:
            schema = cast(type[BaseModel], cls.mapping_schema)
            validate_schema_base(schema)
            # Do not access SQLAlchemy mapper(column_attrs) at class definition time.
            cls._default_convert_domain = True


    def __init__(
        self,
        session: Annotated[
            AsyncSession | None,
            Doc("AsyncSession to bind initially. If None, bind later via set_session() (lazy binding)."),
        ] = None,
        *,
        mapper: Annotated[
            BaseMapper[TModel, BaseModel] | None,
            Doc(
                "Optionally inject a BaseMapper instance. If omitted, instantiate the class-level `mapper` "
                "(if configured)."
            ),
        ] = None,
        mapping_schema: Annotated[
            type[BaseModel] | None,
            Doc("Optionally override schema per instance. If provided, 'column-only' validation runs immediately."),
        ] = None,
        default_convert_domain: Annotated[
            bool | None,
            Doc(
                "Default return type when the caller does not specify convert_domain. "
                "True=Domain, False=ORM. If None, use the class default."
            ),
        ] = None,
    ):
        """
        Configure session/mapper/schema/default-conversion at the instance level.

        Raises
        ------
        - TypeError: when `mapping_schema` does not match model columns under strict rules.
        - ValueError: when `default_convert_domain=True` but no schema is configured.
        """
        self._specific_session = session
        self.sa_mapper: Mapper[Any] = sa_mapper(self.model)

        # Configure an instance-level mapper
        candiate_mapper = mapper
        if candiate_mapper is None and self.mapper is not None:
            candiate_mapper = self.mapper()

        self._mapper_instance: BaseMapper[TModel, BaseModel] | None = None
        if candiate_mapper is not None:
            self._validate_mapper_integrity(candiate_mapper)
            self._mapper_instance = candiate_mapper

        # Validate and apply instance-level schema (column-only)
        if mapping_schema is not None:
            validate_schema_base(mapping_schema)

            if self._mapper_instance is None:
                self._validate_schema_against_model(mapping_schema)

            self.mapping_schema = mapping_schema
            self._default_convert_domain = True

        # If only class-level schema is set, do a one-time column-only validation at instantiation.
        elif getattr(self, "mapping_schema", None) is not None and self._mapper_instance is None:
            schema = cast(type[BaseModel], self.mapping_schema)
            self._validate_schema_against_model(schema)
            self._default_convert_domain = True

        if default_convert_domain is not None:
            if default_convert_domain and getattr(self, "mapping_schema", None) is None:
                raise ValueError("default_convert_domain=True is not allowed without mapping_schema.")
            self._default_convert_domain = default_convert_domain

        if session is not None and self._session_provider is not None:
            import warnings

            warnings.warn(
                "[BaseRepository] Repository-level session was provided via __init__, "
                "but a SessionProvider is also configured. The SessionProvider takes precedence, "
                "and the repository-level session will be ignored.",
                stacklevel=2,
            )
        elif session is not None:
            import warnings

            warnings.warn(
                "[BaseRepository] Repository-level session was provided via __init__. "
                "Stale or closed session handling is the caller's responsibility.",
                stacklevel=2,
            )


    def _validate_mapper_integrity(self, mapper_instance: BaseMapper[TModel, BaseModel]) -> None:
        """
        Runtime-check that the injected mapper implements the correct interface
        and can handle this Repository's model type.
        """
        if not isinstance(mapper_instance, BaseMapper):
            raise TypeError(
                f"The injected mapper ({type(mapper_instance).__name__}) must inherit from BaseMapper."
            )


    def _validate_schema_against_model(self, schema: type[BaseModel]) -> None:
        """
        Validate that required fields in mapping_schema map ONLY to actual ORM model column names.

        Note
        ----
        Accessing SQLAlchemy mapper.column_attrs is only done after instance construction.
        """
        model_column_names = {prop.key for prop in self.sa_mapper.column_attrs}
        required = {n for n, f in schema.model_fields.items() if f.is_required()}
        missing = required - model_column_names
        if missing:
            raise TypeError(
                f"[Strict] Required schema fields must map to model columns only: missing={missing} "
                f"(model={self.model.__name__})"
            )


    @classmethod
    def configure_session_provider(cls, provider: SessionProvider) -> None:
        cls._session_provider = provider


    @property
    def session(self) -> AsyncSession:
        if self._session_provider is None:
            if self._specific_session is None:
                raise RuntimeError("Neither SessionProvider nor specific_session is configured.")
            return self._specific_session

        return self._session_provider.get_session()


    def _resolve_session(self, session: AsyncSession | None) -> AsyncSession:
        return session if session is not None else self.session


    def _autoinc_pk_keys(self) -> set[str]:
        """
        Autoincrement PK detection rules:

        - primary_key=True
        - isinstance(col.type, Integer) (includes BigInteger)
        - Column.autoincrement is True (string 'auto' is NOT accepted)
        """
        keys: set[str] = set()
        for col in self.sa_mapper.columns:
            if not getattr(col, "primary_key", False):
                continue
            if not isinstance(getattr(col, "type", None), Integer):
                continue
            if getattr(col, "autoincrement", None) is True:
                keys.add(col.key)
        return keys


    def _schema_payload(
        self,
        data: Annotated[BaseModel | Mapping[str, Any], Doc("Pydantic model or mapping input.")],
    ) -> Annotated[dict[str, Any], Doc("Payload sanitized to model columns only.")]:
        """
        Normalize schema/mapping input into a **model-columns-only payload**.

        Steps
        -----
        1) Pydantic → dict via `model_dump(exclude_unset=True)`
        2) Filter keys by model column keys
        3) Remove **autoincrement PK** keys (ignore client input)
        """
        raw = data.model_dump(exclude_unset=True) if isinstance(data, BaseModel) else dict(data)
        colnames = {prop.key for prop in self.sa_mapper.column_attrs}
        payload = {k: v for k, v in raw.items() if k in colnames}

        for k in self._autoinc_pk_keys():
            payload.pop(k, None)  # ignore client input for autoincrement PKs
        return payload


    def _schema_to_orm(
        self,
        data: Annotated[BaseModel | Mapping[str, Any], Doc("Domain(Pydantic) or mapping input.")],
    ) -> Annotated[TModel, Doc("Final ORM model instance.")]:
        """
        Convert input data into an **ORM model instance**.

        Precedence
        ----------
        1) If mapper instance exists and `data` matches mapping_schema type → use mapper.to_orm
        2) Otherwise → sanitize via `_schema_payload()` → `self.model(**payload)`
        """
        try:
            schema = self.mapping_schema
            if self._mapper_instance and schema is not None and isinstance(data, schema):
                return self._mapper_instance.to_orm(data)
        except NotImplementedError:
            pass

        payload = self._schema_payload(data)
        return self.model(**payload)


    def _convert(
        self,
        row: Annotated[TModel, Doc("ORM row (single) or None).")],
        *,
        convert_domain: Annotated[bool | None, Doc("Per-call domain conversion flag. None uses default.")],
    ) -> BaseModel | TModel:
        """
        Convert ORM → domain (Pydantic).

        Rules
        -----
        - If `convert_domain` is None, uses `_default_convert_domain`
        - Conversion happens only when: effective=True and row is not None and `mapping_schema` exists
        - Mapper(to_domain) first; if not implemented, fall back to Pydantic `model_validate(...)`
        (from_attributes is enforced via `mapping_schema.model_config`)
        """
        effective = self._default_convert_domain if convert_domain is None else convert_domain
        schema = self.mapping_schema
        if not effective or row is None or schema is None:
            return row

        try:
            if self._mapper_instance:
                return self._mapper_instance.to_domain(row)
        except NotImplementedError:
            pass

        return schema.model_validate(row)


    def list(
        self,
        flt: Annotated[BaseRepoFilter | None, Doc("Initial WHERE filter (optional). None means no conditions.")] = None,
    ) -> Annotated[ListQuery[TModel], Doc("ListQuery DSL entrypoint (where/order_by/paging/with_cursor/limit).")]:
        """
        Create a `ListQuery` and start the **chained query DSL**.

        Example
        -------
        >>> q = repo.list(flt=UserFilter(name="A")).order_by([User.id.asc()]).paging(page=1, size=10)
        >>> rows = await repo.execute(q)
        """
        return ListQuery[TModel](self.model, flt=flt)


    async def execute(
        self,
        q_or_stmt: Annotated[QueryOrStmt[TModel], Doc("ListQuery or SQLAlchemy Core statement.")],
        *,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
        convert_domain: Annotated[bool | None, Doc("Per-call domain conversion flag. None uses default.")] = None,
    ) -> Any:
        """
        Execute a `ListQuery` or a SQLAlchemy statement and return results in the final shape (domain/ORM).
        - SELECT always returns a `list`. (Use `get()` for single-row reads.)
        """
        stmt = query_to_stmt(q_or_stmt)  # ListQuery -> Select
        s = self._resolve_session(session)
        result = await s.execute(stmt)

        scalars: ScalarResult[TModel] = result.scalars()
        rows: list[TModel] = list(scalars)
        return [self._convert(r, convert_domain=convert_domain) for r in rows]


    async def get_list(
        self,
        *,
        flt: Annotated[BaseRepoFilter | None, Doc("WHERE filter (optional).")] = None,
        order_by: Annotated[Sequence[Any] | None, Doc("Ordering (optional). Supports str/column/asc()/desc(), etc.")] = None,
        cursor: Annotated[dict[str, Any] | None, Doc("Cursor dict for keyset paging. None/{} means first page.")] = None,
        page: Annotated[int | None, Doc("Offset paging: page number (>=1).")] = None,
        size: Annotated[int | None, Doc("Common page size for offset/cursor (>=1).")] = None,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
        convert_domain: Annotated[bool | None, Doc("Per-call domain conversion flag.")] = None,
    ) -> Any:
        """
        Convenience method: builds a ListQuery internally and executes it.

        Rules
        -----
        - If `cursor` is provided → keyset(cursor) paging (requires `size`)
        - If `page` and `size` are provided → OFFSET paging
        - If neither is provided → no paging
        """
        q = ListQuery(self.model, flt=None)
        if flt:
            q.where(flt)
        if order_by:
            q.order_by(order_by)

        if cursor is not None:
            # {} allowed: first page for keyset paging
            q.with_cursor(cursor)
            if size is None:
                raise ValueError("Keyset paging requires limit(size).")
            q.limit(size)
        elif page is not None and size is not None:
            q.paging(page=page, size=size)

        s = self._resolve_session(session)
        return await self.execute(q, session=s, convert_domain=convert_domain)


    async def get(
        self,
        flt: Annotated[BaseRepoFilter, Doc("WHERE filter for single-row lookup.")],
        *,
        convert_domain: Annotated[bool | None, Doc("Per-call domain conversion flag.")] = None,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
    ) -> Annotated[Any | None, Doc("Returns ORM/Domain object if found, otherwise None.")]:
        """
        Get a single row. Returns the first matching row.
        """
        s = self._resolve_session(session)
        stmt: Select[tuple[TModel]] = select(self.model)
        crit = flt.where_criteria(self.model)
        if crit:
            stmt = stmt.where(*crit)

        res = await s.execute(stmt)
        obj = res.scalars().first()
        return self._convert(obj, convert_domain=convert_domain) if obj else None


    async def get_or_fail(
        self,
        flt: Annotated[BaseRepoFilter, Doc("WHERE filter for required single-row lookup.")],
        *,
        convert_domain: Annotated[bool | None, Doc("Per-call domain conversion flag.")] = None,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
    ) -> Annotated[Any, Doc("Always returns an object; raises ValueError if not found.")]:
        """
        Get a single row (required). Raises ValueError if not found.
        """
        s = self._resolve_session(session)
        obj = await self.get(
            flt,
            convert_domain=convert_domain,
            session=s,
        )
        if not obj:
            raise ValueError(f"{self.model.__name__} not found with filter={flt}")
        return obj


    async def count(
        self,
        flt: Annotated[BaseRepoFilter | None, Doc("WHERE filter for aggregation (optional).")] = None,
        *,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
    ) -> Annotated[int, Doc("Number of rows matching the condition.")]:
        """
        Return row count based on the given condition.
        """
        s = self._resolve_session(session)
        stmt = select(func.count()).select_from(self.model)
        if flt:
            crit = flt.where_criteria(self.model)
            if crit:
                stmt = stmt.where(*crit)
        res = await s.execute(stmt)
        return res.scalar_one()


    async def delete(
        self,
        flt: Annotated[BaseRepoFilter, Doc("WHERE filter for delete target.")],
        *,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
    ) -> Annotated[int, Doc("Number of deleted rows (rowcount).")]:
        """
        Delete by condition. Returns affected row count.
        """
        s = self._resolve_session(session)
        stmt = delete(self.model).where(*flt.where_criteria(self.model))
        res = await s.execute(stmt)
        return res.rowcount or 0  # type: ignore[attr-defined]


    def add(
        self,
        obj: Annotated[TModel, Doc("ORM object to add to the session.")],
        *,
        session: Annotated[AsyncSession | None, Doc("Session to use (optional).")] = None,
    ) -> None:
        """
        Add an ORM object to the session. (flush/commit is controlled by the caller)
        """
        s = self._resolve_session(session)
        s.add(obj)

    def add_all(
        self,
        objs: Annotated[Sequence[TModel], Doc("Sequence of ORM objects to add to the session.")],
        *,
        session: Annotated[AsyncSession | None, Doc("Session to use (optional).")] = None,
    ) -> None:
        """
        Add multiple ORM objects to the session.
        """
        s = self._resolve_session(session)
        s.add_all(objs)


    async def create(
        self,
        data: Annotated[BaseModel | Mapping[str, Any], Doc("Pydantic schema or dict/mapping.")],
        *,
        convert_domain: Annotated[bool | None, Doc("Per-call domain conversion flag.")] = None,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
    ) -> Any:
        """
        Create a single row and `flush()`.

        Rules
        -----
        - For Pydantic schema input, validation is handled by Pydantic
        - Autoincrement PK values from the client are ignored
        - Return type is Domain/ORM depending on configuration
        """
        s = self._resolve_session(session)

        obj = self._schema_to_orm(data)
        self.add(obj, session=s)
        await s.flush()
        return self._convert(obj, convert_domain=convert_domain)


    async def create_many(
        self,
        items: Annotated[Sequence[BaseModel | Mapping[str, Any]], Doc("Batch create input (each item is schema or dict).")],
        *,
        convert_domain: Annotated[bool | None, Doc("Per-call domain conversion flag.")] = None,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
        skip_convert: Annotated[bool, Doc("If True, skip domain conversion and return ORM objects as-is.")] = False,
    ) -> Annotated[builtins.list[Any], Doc("Created objects list (Domain/ORM).")]:
        """
        Create multiple rows and `flush()`.

        - Same rule applies: autoincrement PK values from the client are ignored for each item
        - If skip_convert=True, returns ORM objects without conversion
        """
        objs = [self._schema_to_orm(data) for data in items]
        s = self._resolve_session(session)
        self.add_all(objs, session=s)
        await s.flush()

        if skip_convert:
            return objs
        return [self._convert(o, convert_domain=convert_domain) for o in objs]


    async def create_from_model(
        self,
        obj: Annotated[TModel, Doc("A fully constructed ORM model instance.")],
        *,
        convert_domain: Annotated[bool | None, Doc("Per-call domain conversion flag.")] = None,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
    ) -> Any:
        """
        Insert an **ORM model instance as-is** + `flush()`.

        Notes
        -----
        - The object is added as provided.
        - Autoincrement PK fields are NOT forcibly removed here. (If a PK is set, it may be included in the INSERT attempt.)
        """
        s = self._resolve_session(session)
        self.add(obj, session=s)
        await s.flush()
        return self._convert(obj, convert_domain=convert_domain)


    async def update(
        self,
        flt: Annotated[BaseRepoFilter, Doc("WHERE filter for update target.")],
        update: Annotated[Mapping[str, Any] | BaseModel, Doc("Values to update (schema or dict). Sanitized to columns-only.")],
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
    ) -> Annotated[int, Doc("Number of updated rows (rowcount).")]:
        """
        Update rows immediately with a single SQL UPDATE, without loading rows into memory.

        Suitable for
        ----------
        - Bulk updates
        - Simple field modifications
        """
        stmt: Update = sa_update(self.model)
        crit = flt.where_criteria(self.model)
        if crit:
            stmt = stmt.where(*crit)

        payload = self._schema_payload(update)
        stmt = stmt.values(**payload)

        s = self._resolve_session(session)
        res = await s.execute(stmt)
        return res.rowcount or 0  # type: ignore[attr-defined]


    async def update_from_model(
        self,
        base: Annotated[TModel, Doc("A persistent ORM object in the session (Dirty Checking target).")],
        update: Annotated[Mapping[str, Any] | BaseModel, Doc("Values to update (schema or dict). Sanitized to columns-only.")],
        *,
        convert_domain: Annotated[bool | None, Doc("Per-call domain conversion flag.")] = None,
        session: Annotated[AsyncSession | None, Doc("Session to use for execution (optional).")] = None,
    ) -> Any:
        """
        Update a persistent ORM model using Dirty Checking.

        Steps
        -----
        1) Build a columns-only payload via `_schema_payload(update)`
        2) Apply updates via `setattr(base, k, v)`
        3) Persist changes via `flush()`
        """
        payload = self._schema_payload(update)
        for k, v in payload.items():
            setattr(base, k, v)

        s = self._resolve_session(session)
        await s.flush()
        return self._convert(base, convert_domain=convert_domain)