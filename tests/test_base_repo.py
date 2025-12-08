from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, TypedDict, cast

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Integer, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from base_repository.base_filter import BaseRepoFilter
from base_repository.base_mapper import BaseMapper
from base_repository.query.list_query import ListQuery
from base_repository.repository.base_repo import BaseRepository
from base_repository.session_provider import SessionProvider

from .fakes import FakeAsyncSession, FakeResult
from .models import Result
from .schemas import ResultStrictSchema



# Filter used by StrictRepo tests
@dataclass
class RFilter(BaseRepoFilter):
    id: int | None = None
    ids: Iterable[int] | None = None
    tenant_id: int | None = None



# Repository with mapping_schema enabled (domain conversion by default)
class StrictRepo(BaseRepository[Result]):
    model = Result
    filter_class = RFilter
    mapping_schema = ResultStrictSchema



# Local ORM base for additional models in this test file
class Base(DeclarativeBase):
    pass



# Test model: Integer autoincrement primary key
class AutoIncModel(Base):
    __tablename__ = "autoinc_model"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(nullable=True)



# Pydantic schema aligned with AutoIncModel
class AutoIncSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pk: int | None = None
    name: str | None = None



# Dummy filter used for AutoIncModel
@dataclass
class DummyFilter(BaseRepoFilter):
    pk: int | None = None



@pytest.mark.asyncio
async def test_execute_select_listquery_returns_list_and_converts_by_default() -> None:
    """
    < get_list returns a list and converts to schema by default when mapping_schema is set >
    1. Prepare ORM rows.
    2. Create a StrictRepo with a FakeAsyncSession returning those rows.
    3. Call get_list(...) with default conversion.
    4. Assert results are schema objects and values match.
    """
    # 1
    rows = [
        Result(id=1, item_id=10, sub_category_id=None, result_value="A", is_abnormal=None, tenant_id=1, checkup_id=100),
        Result(id=2, item_id=10, sub_category_id=None, result_value="B", is_abnormal=None, tenant_id=1, checkup_id=100),
    ]

    # 2
    session = FakeAsyncSession(script=[FakeResult(rows)])
    repo = StrictRepo(cast(AsyncSession, session))

    # 3
    got = await repo.get_list(flt=RFilter(tenant_id=1))

    # 4
    assert [g.id for g in got] == [1, 2]
    assert isinstance(got[0], ResultStrictSchema)



@pytest.mark.asyncio
async def test_execute_select_convert_domain_false_returns_orm() -> None:
    """
    < convert_domain=False returns raw ORM rows >
    1. Prepare a single ORM row.
    2. Call get_list(..., convert_domain=False).
    3. Assert the returned item is an ORM instance, not a schema object.
    """
    # 1
    rows = [
        Result(id=1, item_id=10, sub_category_id=None, result_value=None, is_abnormal=None, tenant_id=1, checkup_id=100),
    ]

    # 2
    session = FakeAsyncSession(script=[FakeResult(rows)])
    repo = StrictRepo(cast(AsyncSession, session))
    got = await repo.get_list(flt=RFilter(tenant_id=1), convert_domain=False)

    # 3
    assert type(got[0]).__name__ == "Result"



@pytest.mark.asyncio
async def test_get_and_get_or_fail() -> None:
    """
    < get() and get_or_fail() return a single row when present >
    1. Prepare one ORM row.
    2. Call get(...) and assert it returns the row.
    3. Call get_or_fail(...) and assert it returns the row.
    """
    # 1
    rows = [
        Result(id=99, item_id=1, sub_category_id=None, result_value=None, is_abnormal=None, tenant_id=1, checkup_id=1),
    ]
    session = FakeAsyncSession(script=[FakeResult(rows), FakeResult(rows)])
    repo = StrictRepo(cast(AsyncSession, session))

    # 2
    one = await repo.get(RFilter(id=99))
    assert one and one.id == 99

    # 3
    got = await repo.get_or_fail(RFilter(id=99))
    assert got.id == 99



@pytest.mark.asyncio
async def test_get_or_fail_raises_when_missing() -> None:
    """
    < get_or_fail raises ValueError when not found >
    1. Prepare an empty result set.
    2. Call get_or_fail(...).
    3. Assert ValueError is raised.
    """
    # 1
    session = FakeAsyncSession(script=[FakeResult([])])
    repo = StrictRepo(cast(AsyncSession, session))

    # 2
    # 3
    with pytest.raises(ValueError):
        _ = await repo.get_or_fail(RFilter(id=404))



@pytest.mark.asyncio
async def test_count_and_delete_and_create() -> None:
    """
    < count, delete, and create basic flows >
    1. Prepare FakeAsyncSession scripts for count, delete, and create.
    2. Call count(...) and assert returned count.
    3. Call delete(...) and assert returned rowcount.
    4. Call create(...) and assert schema conversion and session side effects.
    """
    # 1
    session = FakeAsyncSession(
        script=[
            FakeResult(count=3),
            FakeResult(rowcount=2),
            FakeResult(),
        ]
    )
    repo = StrictRepo(cast(AsyncSession, session))

    # 2
    c = await repo.count(RFilter(tenant_id=1))
    assert c == 3

    # 3
    deleted = await repo.delete(RFilter(ids=[1, 2]))
    assert deleted == 2

    # 4
    created = await repo.create(
        ResultStrictSchema(
            item_id=1,
            sub_category_id=None,
            result_value="X",
            is_abnormal=None,
            tenant_id=1,
            checkup_id=1,
        )
    )
    assert isinstance(created, ResultStrictSchema)
    assert created.item_id == 1
    assert session.added and session.flushed



@pytest.mark.asyncio
async def test_create_many_converts_by_default_and_records_add_all() -> None:
    """
    < create_many returns converted domain list by default and calls add_all >
    1. Prepare a session that can accept add_all + flush.
    2. Call create_many with schema and dict payloads.
    3. Assert conversion output and recorded add_all behavior.
    """
    # 1
    session = FakeAsyncSession(script=[FakeResult(), FakeResult()])
    repo = StrictRepo(cast(AsyncSession, session))

    # 2
    created_any = await repo.create_many(
        [
            ResultStrictSchema(
                item_id=1,
                sub_category_id=None,
                result_value=None,
                is_abnormal=None,
                tenant_id=1,
                checkup_id=1,
            ),
            {
                "item_id": 2,
                "sub_category_id": None,
                "result_value": None,
                "is_abnormal": None,
                "tenant_id": 1,
                "checkup_id": 1,
            },
        ]
    )

    # 3
    assert created_any is not None
    created = cast(list[ResultStrictSchema], created_any)
    assert all(isinstance(c, ResultStrictSchema) for c in created)
    assert [c.item_id for c in created] == [1, 2]
    assert len(session.added_all) == 2
    assert session.flushed



@pytest.mark.asyncio
async def test_create_many_skip_convert_returns_orm_objects() -> None:
    """
    < create_many(skip_convert=True) returns ORM list even when schema exists >
    1. Prepare a session.
    2. Call create_many(..., skip_convert=True).
    3. Assert returned objects are ORM objects.
    """
    # 1
    session = FakeAsyncSession(script=[FakeResult(), FakeResult()])
    repo = StrictRepo(cast(AsyncSession, session))

    # 2
    created_any = await repo.create_many(
        [
            ResultStrictSchema(
                item_id=1,
                sub_category_id=None,
                result_value=None,
                is_abnormal=None,
                tenant_id=1,
                checkup_id=1,
            ),
        ],
        skip_convert=True,
    )

    # 3
    assert created_any is not None
    created = cast(list[Any], created_any)
    assert len(created) == 1
    assert type(created[0]).__name__ == "Result"



@pytest.mark.asyncio
async def test_default_convert_domain_guard_at_init() -> None:
    """
    < default_convert_domain=True without mapping_schema raises ValueError >
    1. Define a repository without mapping_schema.
    2. Instantiate with default_convert_domain=True.
    3. Assert ValueError is raised.
    """
    # 1
    class NoSchemaRepo(BaseRepository[Result]):
        model = Result
        filter_class = RFilter

    # 2
    session = FakeAsyncSession()

    # 3
    with pytest.raises(ValueError):
        _ = NoSchemaRepo(cast(AsyncSession, session), default_convert_domain=True)



@pytest.mark.asyncio
async def test_sessionless_init_then_method_param_session_works() -> None:
    """
    < Repo without a session works when method session parameter is provided >
    1. Prepare ORM rows.
    2. Instantiate repo without session.
    3. Call get_list(..., session=...) and assert results.
    """
    # 1
    rows = [
        Result(id=1, item_id=10, sub_category_id=None, result_value="A", is_abnormal=None, tenant_id=1, checkup_id=100),
        Result(id=2, item_id=10, sub_category_id=None, result_value="B", is_abnormal=None, tenant_id=1, checkup_id=100),
    ]
    s = FakeAsyncSession(script=[FakeResult(rows)])

    # 2
    repo = StrictRepo()

    # 3
    got = await repo.get_list(flt=RFilter(tenant_id=1), session=cast(AsyncSession, s))
    assert [g.id for g in got] == [1, 2]
    assert isinstance(got[0], ResultStrictSchema)



@pytest.mark.asyncio
async def test_raises_when_no_session_anywhere() -> None:
    """
    < Repo raises when no session is available anywhere >
    1. Instantiate repo without session.
    2. Call get_list(...) without session/provider.
    3. Assert RuntimeError is raised.
    """
    # 1
    repo = StrictRepo()

    # 2
    # 3
    with pytest.raises(RuntimeError):
        _ = await repo.get_list(flt=RFilter(tenant_id=1))



@pytest.mark.asyncio
async def test_method_param_session_overrides_repo_session() -> None:
    """
    < Method session parameter overrides repo-held session >
    1. Prepare two sessions: s1 (repo session) and s2 (override session returning a row).
    2. Call get_list(..., session=s2).
    3. Assert result comes from s2.
    """
    # 1
    s1 = FakeAsyncSession(script=[FakeResult([])])
    s2_rows = [
        Result(id=42, item_id=1, sub_category_id=None, result_value=None, is_abnormal=None, tenant_id=1, checkup_id=1),
    ]
    s2 = FakeAsyncSession(script=[FakeResult(s2_rows)])

    # 2
    repo = StrictRepo(cast(AsyncSession, s1))
    got = await repo.get_list(flt=RFilter(tenant_id=1), session=cast(AsyncSession, s2))

    # 3
    assert len(got) == 1 and got[0].id == 42



@pytest.mark.asyncio
async def test_create_uses_overridden_session_for_add_and_flush() -> None:
    """
    < create() uses overridden session, not repo session >
    1. Prepare repo session s1 and override session s2.
    2. Call create(..., session=s2).
    3. Assert flush happened on s2 and not on s1.
    """
    # 1
    s1 = FakeAsyncSession(script=[])
    s2 = FakeAsyncSession(script=[FakeResult()])

    # 2
    repo = StrictRepo(cast(AsyncSession, s1))
    created = await repo.create(
        ResultStrictSchema(
            item_id=123,
            sub_category_id=None,
            result_value="X",
            is_abnormal=None,
            tenant_id=77,
            checkup_id=555,
        ),
        session=cast(AsyncSession, s2),
    )

    # 3
    assert isinstance(created, ResultStrictSchema)
    assert created.item_id == 123
    assert getattr(s2, "flushed", False) is True
    assert not getattr(s1, "flushed", False)



@pytest.mark.asyncio
async def test_model_inference_when_model_not_declared() -> None:
    """
    < Model is inferred from generic argument when subclass does not declare `model` >
    1. Define a repo subclass without `model`.
    2. Instantiate it.
    3. Assert repo.model is inferred as Result.
    """
    # 1
    class NoModelRepo(BaseRepository[Result]):
        filter_class = RFilter
        mapping_schema = ResultStrictSchema

    # 2
    session = FakeAsyncSession()
    repo = NoModelRepo(cast(AsyncSession, session))

    # 3
    assert repo.model is Result



@pytest.mark.asyncio
async def test_update_from_model_dirty_check_and_flush() -> None:
    """
    < update_from_model sets attributes, flushes, and can convert to schema >
    1. Prepare a repo with a session.
    2. Call update_from_model with an update dict.
    3. Assert schema conversion and session.flush were executed.
    """
    # 1
    s = FakeAsyncSession(script=[FakeResult()])
    repo = StrictRepo(cast(AsyncSession, s))

    base = Result(
        id=1,
        item_id=10,
        sub_category_id=None,
        result_value="A",
        is_abnormal=None,
        tenant_id=1,
        checkup_id=100,
    )

    # 2
    after = await repo.update_from_model(
        base=base,
        update={"result_value": "Z"},
        convert_domain=True,
    )

    # 3
    assert isinstance(after, ResultStrictSchema)
    assert after.result_value == "Z"
    assert s.flushed is True



@pytest.mark.asyncio
async def test_create_from_model_add_and_flush_and_domain_convert() -> None:
    """
    < create_from_model adds, flushes, and converts by default when schema is set >
    1. Prepare a repo with a session.
    2. Call create_from_model(...) with an ORM object.
    3. Assert schema conversion and flush occurred.
    """
    # 1
    s = FakeAsyncSession(script=[FakeResult()])
    repo = StrictRepo(cast(AsyncSession, s))

    # 2
    created = await repo.create_from_model(
        Result(
            id=999,
            item_id=1,
            sub_category_id=None,
            result_value="X",
            is_abnormal=None,
            tenant_id=7,
            checkup_id=77,
        )
    )

    # 3
    assert isinstance(created, ResultStrictSchema)
    assert created.item_id == 1
    assert s.flushed is True



def test_subclass_definition_does_not_call_sa_mapper(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    < __init_subclass__ must not call sa_mapper() at class definition time >
    1. Patch repository.base_repo.sa_mapper to count calls.
    2. Define a Repo subclass.
    3. Assert sa_mapper was not called and default conversion is enabled.
    """
    # 1
    import base_repository.repository.base_repo as base_repo_mod

    called = {"count": 0}

    def fake_sa_mapper(_: object) -> object:
        called["count"] += 1
        return object()

    monkeypatch.setattr(base_repo_mod, "sa_mapper", fake_sa_mapper)

    # 2
    class TmpSchema(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        id: int



    class TmpModel(DeclarativeBase):
        __abstract__ = True



    class TmpRepo(BaseRepository[TmpModel]):
        model = TmpModel
        filter_class = RFilter
        mapping_schema = TmpSchema

    # 3
    assert called["count"] == 0
    assert TmpRepo._default_convert_domain is True



def test_init_session_warning_cases() -> None:
    """
    < __init__ warning behavior depends on whether a SessionProvider is configured >
    1. With SessionProvider: passing a session warns and provider session takes precedence.
    2. Without SessionProvider: passing a session warns about stale/closed session handling.
    """
    # 1
    class Provider(SessionProvider):
        def __init__(self, s: AsyncSession) -> None:
            self._s = s

        def get_session(self) -> AsyncSession:
            return self._s



    class RepoWithProvider(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        mapping_schema = AutoIncSchema

    s1 = cast(AsyncSession, FakeAsyncSession(script=[]))
    s2 = cast(AsyncSession, FakeAsyncSession(script=[]))
    RepoWithProvider.configure_session_provider(Provider(s2))

    with pytest.warns(UserWarning, match="SessionProvider takes precedence"):
        repo_p = RepoWithProvider(s1)

    assert repo_p.session is s2

    # 2
    class RepoNoProvider(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        mapping_schema = AutoIncSchema

    s3 = cast(AsyncSession, FakeAsyncSession(script=[]))

    with pytest.warns(UserWarning, match="Stale or closed session handling"):
        _ = RepoNoProvider(s3)



@pytest.mark.asyncio
async def test_get_list_cursor_requires_order_by_then_requires_size() -> None:
    """
    < get_list(cursor=...) requires order_by first, then requires size for keyset paging >
    1. Without order_by, get_list(cursor=...) must raise about order_by requirement.
    2. With order_by but size=None, get_list must raise about limit(size) requirement.
    """
    # 1
    class Repo(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        mapping_schema = AutoIncSchema

    repo = Repo(cast(AsyncSession, FakeAsyncSession(script=[FakeResult([])])))

    with pytest.raises(ValueError, match="Cursor paging requires order_by"):
        await repo.get_list(cursor={}, size=10)

    # 2
    with pytest.raises(ValueError, match="Keyset paging requires limit"):
        await repo.get_list(cursor={}, order_by=[AutoIncModel.pk.asc()], size=None)



def test_autoinc_pk_keys_includes_only_integer_autoincrement_primary_keys() -> None:
    """
    < _autoinc_pk_keys includes only Integer primary keys with autoincrement=True >
    1. Integer PK + autoincrement=True must be included.
    2. Non-Integer PK + autoincrement=True must be excluded.
    """
    # 1
    class Base2(DeclarativeBase):
        pass



    class IntAutoPKModel(Base2):
        __tablename__ = "int_autopk_model_for_autoinc_keys"

        pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        name: Mapped[str | None] = mapped_column(nullable=True)



    @dataclass
    class IntFilter(BaseRepoFilter):
        pk: int | None = None



    class IntRepo(BaseRepository[IntAutoPKModel]):
        model = IntAutoPKModel
        filter_class = IntFilter

    int_repo = IntRepo(cast(AsyncSession, FakeAsyncSession(script=[])))
    assert int_repo._autoinc_pk_keys() == {"pk"}

    # 2
    class StrAutoPKModel(Base2):
        __tablename__ = "str_autopk_model_for_autoinc_keys"

        pk: Mapped[str] = mapped_column(String, primary_key=True, autoincrement=True)
        name: Mapped[str | None] = mapped_column(nullable=True)



    @dataclass
    class StrFilter(BaseRepoFilter):
        pk: str | None = None



    class StrRepo(BaseRepository[StrAutoPKModel]):
        model = StrAutoPKModel
        filter_class = StrFilter

    str_repo = StrRepo(cast(AsyncSession, FakeAsyncSession(script=[])))
    assert str_repo._autoinc_pk_keys() == set()



def test_schema_payload_drops_unknown_keys_and_autoinc_pk() -> None:
    """
    < _schema_payload filters to model columns and drops autoincrement PK keys >
    1. Provide mapping payload including pk and unknown keys.
    2. Assert pk and unknown are removed and known keys remain.
    """
    # 1
    class Repo(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        mapping_schema = AutoIncSchema

    repo = Repo(cast(AsyncSession, FakeAsyncSession(script=[])))
    payload = repo._schema_payload({"pk": 123, "name": "A", "unknown": "X"})

    # 2
    assert "pk" not in payload
    assert "unknown" not in payload
    assert payload["name"] == "A"



def test_schema_payload_from_pydantic_exclude_unset() -> None:
    """
    < _schema_payload uses model_dump(exclude_unset=True) for Pydantic schemas >
    1. Create a schema without setting optional fields.
    2. Build payload.
    3. Assert optional unset fields are absent and autoinc pk is absent.
    """
    # 1
    class Repo(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        mapping_schema = AutoIncSchema

    repo = Repo(cast(AsyncSession, FakeAsyncSession(script=[])))

    # 2
    data = AutoIncSchema()
    payload = repo._schema_payload(data)

    # 3
    assert "name" not in payload
    assert "pk" not in payload



def test_schema_to_orm_falls_back_when_mapper_to_orm_not_implemented() -> None:
    """
    < _schema_to_orm falls back to payload construction when mapper.to_orm is not implemented >
    1. Define a mapper whose to_orm raises NotImplementedError.
    2. Instantiate repo with that mapper.
    3. Call _schema_to_orm(schema) and assert ORM is built via payload path.
    """
    # 1
    class BadMapper(BaseMapper):
        def to_domain(self, orm_object: AutoIncModel) -> AutoIncSchema:
            return AutoIncSchema(pk=orm_object.pk, name=orm_object.name)

        def to_orm(self, domain_object: AutoIncSchema) -> AutoIncModel:
            raise NotImplementedError()

    # 2
    class Repo(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        mapping_schema = AutoIncSchema
        mapper = BadMapper

    repo = Repo(cast(AsyncSession, FakeAsyncSession(script=[])))

    # 3
    obj = repo._schema_to_orm(AutoIncSchema(name="A"))
    assert isinstance(obj, AutoIncModel)
    assert obj.name == "A"



def test_convert_uses_mapper_to_domain_then_falls_back_to_pydantic_on_not_implemented() -> None:
    """
    < _convert uses mapper.to_domain first; on NotImplementedError it falls back to Pydantic conversion >
    1. Define a mapper that can either succeed or raise NotImplementedError.
    2. When mapper succeeds, assert the mapper-produced schema is returned.
    3. When mapper fails, assert fallback schema conversion is returned.
    """
    # 1
    class Mapper(BaseMapper):
        def __init__(self, fail: bool) -> None:
            self._fail = fail

        def to_domain(self, orm_object: AutoIncModel) -> AutoIncSchema:
            if self._fail:
                raise NotImplementedError()
            return AutoIncSchema(pk=999, name="M")

        def to_orm(self, domain_object: AutoIncSchema) -> AutoIncModel:
            return AutoIncModel(pk=1, name=domain_object.name)

    class Repo(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        mapping_schema = AutoIncSchema

    # 2
    r1 = Repo(cast(AsyncSession, FakeAsyncSession(script=[])), mapper=Mapper(fail=False))
    out1 = r1._convert(AutoIncModel(pk=1, name="A"), convert_domain=None)
    assert isinstance(out1, AutoIncSchema)
    assert out1.pk == 999

    # 3
    r2 = Repo(cast(AsyncSession, FakeAsyncSession(script=[])), mapper=Mapper(fail=True))
    out2 = r2._convert(AutoIncModel(pk=2, name="B"), convert_domain=None)
    assert isinstance(out2, AutoIncSchema)
    assert out2.pk == 2
    assert out2.name == "B"



def test_convert_returns_row_when_schema_missing() -> None:
    """
    < _convert returns the raw ORM row when mapping_schema is missing >
    1. Create a repo that does NOT define mapping_schema.
    2. Pass a real ORM row into _convert.
    3. Assert the same object is returned (no conversion path is possible).
    """
    # 1
    class RepoNoSchema(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        # NOTE: mapping_schema intentionally omitted

    repo_no_schema = RepoNoSchema(cast(AsyncSession, FakeAsyncSession(script=[])))

    # 2
    row = AutoIncModel(pk=1, name="A")
    out = repo_no_schema._convert(row, convert_domain=False)

    # 3
    assert out is row


def test_convert_none_row_returns_none_runtime_guard() -> None:
    """
    < _convert returns None when row is None (runtime guard branch coverage) >
    1. Create a repo that defines mapping_schema (conversion-capable repo).
    2. Call _convert with row=None via cast(Any, None) to reach the guard.
       - This is intentionally outside the type contract (row: TModel),
         but validates the defensive runtime behavior.
    3. Assert None is returned.
    """
    # 1
    class RepoWithSchema(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        mapping_schema = AutoIncSchema

    repo_with_schema = RepoWithSchema(cast(AsyncSession, FakeAsyncSession(script=[])))

    # 2
    out_none = repo_with_schema._convert(cast(Any, None), convert_domain=None)

    # 3
    assert out_none is None



@pytest.mark.asyncio
async def test_execute_rejects_non_listquery_via_query_to_stmt() -> None:
    """
    < execute rejects unsupported statement types through query_to_stmt >
    1. Build a repo.
    2. Call execute(...) with a non-ListQuery statement.
    3. Assert TypeError is raised from query_to_stmt.
    """
    # 1
    from sqlalchemy import insert

    class Repo(BaseRepository[AutoIncModel]):
        model = AutoIncModel
        filter_class = DummyFilter
        mapping_schema = AutoIncSchema

    repo = Repo(cast(AsyncSession, FakeAsyncSession(script=[FakeResult([])])))

    # 2
    # 3
    with pytest.raises(TypeError, match="Unsupported query/statement type"):
        await repo.execute(insert(AutoIncModel).values(name="A"))  # type: ignore[arg-type]



@pytest.mark.asyncio
async def test_update_builds_values_with_schema_payload_filtering() -> None:
    """
    < update filters payload to model columns and executes >
    1. Prepare a session where execute returns rowcount.
    2. Call update with an update dict including unknown keys.
    3. Assert the returned rowcount matches.
    """
    # 1
    s = FakeAsyncSession(script=[FakeResult(rowcount=3)])
    repo = StrictRepo(cast(AsyncSession, s))

    # 2
    updated = await repo.update(RFilter(id=1), update={"result_value": "Z", "unknown": 123})

    # 3
    assert updated == 3



def test_init_mapping_schema_param_validates_schema_against_model_and_enables_default_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    < __init__(mapping_schema=...) validates schema-model compatibility and enables default conversion >
    1. Define a model and matching schema (from_attributes=True).
    2. Define Repo without class-level mapping_schema.
    3. Monkeypatch _validate_schema_against_model to count calls.
    4. Instantiate Repo(mapping_schema=...).
    5. Assert validation was called once and default conversion is enabled.
    """
    # 1
    class Base2(DeclarativeBase):
        pass



    class AutoIncModel2(Base2):
        __tablename__ = "autoinc_model_for_init_schema_param"

        pk: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        name: Mapped[str | None] = mapped_column(nullable=True)



    class AutoIncSchema2(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        pk: int | None = None
        name: str | None = None



    @dataclass
    class DummyFilter2(BaseRepoFilter):
        pk: int | None = None

    # 2
    class Repo(BaseRepository[AutoIncModel2]):
        model = AutoIncModel2
        filter_class = DummyFilter2

    # 3
    called = {"n": 0}
    orig = Repo._validate_schema_against_model

    def wrapped(self: Repo, schema: type[BaseModel]) -> None:
        called["n"] += 1
        return orig(self, schema)

    monkeypatch.setattr(Repo, "_validate_schema_against_model", wrapped)

    # 4
    s = cast(AsyncSession, FakeAsyncSession(script=[]))
    repo = Repo(s, mapping_schema=AutoIncSchema2)

    # 5
    assert called["n"] == 1
    assert repo.mapping_schema is AutoIncSchema2
    assert repo._default_convert_domain is True



def test_init_default_convert_domain_override_assigns_and_disables_conversion_even_when_schema_exists() -> None:
    """
    < default_convert_domain override at init disables conversion even when schema exists >
    1. Define a Repo with class-level mapping_schema.
    2. Instantiate with default_convert_domain=False.
    3. Assert _default_convert_domain is False and _convert returns raw ORM row.
    """
    # 1
    class Base2(DeclarativeBase):
        pass



    class AutoIncModel2(Base2):
        __tablename__ = "autoinc_model_for_default_convert_override"

        pk: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        name: Mapped[str | None] = mapped_column(nullable=True)



    class AutoIncSchema2(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        pk: int | None = None
        name: str | None = None



    @dataclass
    class DummyFilter2(BaseRepoFilter):
        pk: int | None = None

    class Repo(BaseRepository[AutoIncModel2]):
        model = AutoIncModel2
        filter_class = DummyFilter2
        mapping_schema = AutoIncSchema2

    # 2
    s = cast(AsyncSession, FakeAsyncSession(script=[]))
    repo = Repo(s, default_convert_domain=False)

    # 3
    assert repo._default_convert_domain is False

    row = AutoIncModel2(pk=1, name="A")
    out = repo._convert(row, convert_domain=None)
    assert out is row



def test_init_rejects_non_base_mapper_instance_with_clear_type_error() -> None:
    """
    < _validate_mapper_integrity rejects invalid mapper objects >
    1. Define a Repo with mapping_schema.
    2. Instantiate with mapper=object().
    3. Assert TypeError with a clear message.
    """
    # 1
    class Base2(DeclarativeBase):
        pass



    class AutoIncModel2(Base2):
        __tablename__ = "autoinc_model_for_bad_mapper"

        pk: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        name: Mapped[str | None] = mapped_column(nullable=True)



    class AutoIncSchema2(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        pk: int | None = None
        name: str | None = None



    @dataclass
    class DummyFilter2(BaseRepoFilter):
        pk: int | None = None

    class Repo(BaseRepository[AutoIncModel2]):
        model = AutoIncModel2
        filter_class = DummyFilter2
        mapping_schema = AutoIncSchema2

    # 2
    s = cast(AsyncSession, FakeAsyncSession(script=[]))

    # 3
    with pytest.raises(TypeError, match="must inherit from BaseMapper"):
        _ = Repo(s, mapper=cast(Any, object()))



def test_list_returns_listquery_instance_bound_to_model_and_keeps_filter_reference() -> None:
    """
    < BaseRepository.list returns a ListQuery bound to the model >
    1. Define a minimal model and filter.
    2. Call repo.list(flt=...).
    3. Assert the returned object is ListQuery and is bound to the model.
    """
    # 1
    class Base2(DeclarativeBase):
        pass



    class M(Base2):
        __tablename__ = "m_for_list_method"

        id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)



    @dataclass
    class F(BaseRepoFilter):
        id: int | None = None



    class Repo(BaseRepository[M]):
        model = M
        filter_class = F

    # 2
    repo = Repo(cast(AsyncSession, FakeAsyncSession(script=[])))
    q = repo.list(flt=F(id=1))

    # 3
    assert isinstance(q, ListQuery)
    assert getattr(q, "model") is M



@pytest.mark.asyncio
async def test_get_list_cursor_path_calls_limit_when_size_is_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    < get_list(cursor=...) calls q.limit(size) when size is provided >
    1. Monkeypatch ListQuery.limit to record the called size.
    2. Monkeypatch Repo.execute to return [] without SQL execution.
    3. Call get_list(cursor={}, order_by=[...], size=7).
    4. Assert limit(size) was called exactly once with size=7 and output is [].
    """
    # 1
    class Base2(DeclarativeBase):
        pass



    class AutoIncModel2(Base2):
        __tablename__ = "autoinc_model_for_cursor_limit"

        pk: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)



    class AutoIncSchema2(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        pk: int | None = None



    @dataclass
    class DummyFilter2(BaseRepoFilter):
        pk: int | None = None



    class Repo(BaseRepository[AutoIncModel2]):
        model = AutoIncModel2
        filter_class = DummyFilter2
        mapping_schema = AutoIncSchema2


    class Called(TypedDict):
        limit: int
        size: int | None
        
    called: Called = {"limit": 0, "size": None}
    orig_limit = ListQuery.limit

    def wrapped_limit(self: ListQuery, size: int) -> ListQuery:
        called["limit"] += 1
        called["size"] = size
        return orig_limit(self, size)

    async def stub_execute(self: Repo, *_: Any, **__: Any) -> list[Any]:
        return []

    monkeypatch.setattr(ListQuery, "limit", wrapped_limit)
    monkeypatch.setattr(Repo, "execute", stub_execute, raising=True)

    # 2
    repo = Repo(cast(AsyncSession, FakeAsyncSession(script=[FakeResult([])])))

    # 3
    out = await repo.get_list(cursor={}, order_by=[AutoIncModel2.pk.asc()], size=7)

    # 4
    assert out == []
    assert called["limit"] == 1
    assert called["size"] == 7



@pytest.mark.asyncio
async def test_get_list_offset_paging_path_calls_paging_when_page_and_size_are_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    < get_list(page,size) calls q.paging(page=..., size=...) >
    1. Monkeypatch ListQuery.paging to record page and size.
    2. Monkeypatch Repo.execute to return [] without SQL execution.
    3. Call get_list(page=2, size=10).
    4. Assert paging(...) was called once with (2, 10) and output is [].
    """
    # 1
    class Base2(DeclarativeBase):
        pass



    class AutoIncModel2(Base2):
        __tablename__ = "autoinc_model_for_offset_paging"

        pk: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)



    class AutoIncSchema2(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        pk: int | None = None



    @dataclass
    class DummyFilter2(BaseRepoFilter):
        pk: int | None = None



    class Repo(BaseRepository[AutoIncModel2]):
        model = AutoIncModel2
        filter_class = DummyFilter2
        mapping_schema = AutoIncSchema2

    class PagingCalled(TypedDict):
        paging: int
        page: int | None
        size: int | None


    called: PagingCalled = {"paging": 0, "page": None, "size": None}
    orig_paging = ListQuery.paging

    def wrapped_paging(self: ListQuery, *, page: int, size: int) -> ListQuery:
        called["paging"] += 1
        called["page"] = page
        called["size"] = size
        return orig_paging(self, page=page, size=size)

    async def stub_execute(self: Repo, *_: Any, **__: Any) -> list[Any]:
        return []

    monkeypatch.setattr(ListQuery, "paging", wrapped_paging)
    monkeypatch.setattr(Repo, "execute", stub_execute, raising=True)

    # 2
    repo = Repo(cast(AsyncSession, FakeAsyncSession(script=[FakeResult([])])))

    # 3
    out = await repo.get_list(page=2, size=10)

    # 4
    assert out == []
    assert called["paging"] == 1
    assert called["page"] == 2
    assert called["size"] == 10



def test_validate_schema_against_model_raises_type_error_when_required_fields_are_missing() -> None:
    """
    < _validate_schema_against_model raises TypeError when schema requires a field missing on the model >
    1. Define a model with columns: pk, name.
    2. Define a schema requiring `missing_field` not present on the model.
    3. Instantiate Repo(mapping_schema=BadSchema) to trigger validation in __init__.
    4. Assert TypeError message includes strict prefix, missing field, and model name.
    """
    # 1
    class Base2(DeclarativeBase):
        pass



    class Model(Base2):
        __tablename__ = "model_for_schema_missing_required"

        pk: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
        name: Mapped[str | None] = mapped_column(nullable=True)



    # 2
    class BadSchema(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        missing_field: int
        name: str | None = None



    @dataclass
    class DummyFilter2(BaseRepoFilter):
        pk: int | None = None



    class Repo(BaseRepository[Model]):
        model = Model
        filter_class = DummyFilter2

    # 3
    s = cast(AsyncSession, FakeAsyncSession(script=[]))

    # 4
    with pytest.raises(
        TypeError,
        match=r"\[Strict\].*missing=.*missing_field.*model=Model",
    ):
        _ = Repo(s, mapping_schema=BadSchema)
