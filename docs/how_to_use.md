<div align="right">
  <a href="https://4jades.github.io/base-repository/how_to_use.html">English</a> | <a href="https://4jades.github.io/base-repository/how_to_use.ko.html">한국어</a>
</div>       

# How To Use (User Guide)

## Table of Contents

- [0) Scope](#0-scope)
- [1) Model & Schema Definition](#1-model--schema-definition)
- [2) Repository Implementation](#2-repository-implementation)
- [3) Quick Start (Step-by-step)](#3-quick-start-step-by-step)
  - [3.1 Session Binding (Important)](#31-session-binding-important)
    - [3.1.1 (Recommended) Provider-based Setup](#311-recommended-provider-based-setup)
    - [3.1.2 (Option) Inject Session Per Call](#312-option-inject-session-per-call)
    - [3.1.3 (Option) Bind a Session to the Repo (No Provider)](#313-option-bind-a-session-to-the-repo-no-provider)
  - [3.2 Transaction / Commit Responsibility (Important)](#32-transaction--commit-responsibility-important)
  - [3.3 Create (Single / Bulk)](#33-create-single--bulk)
  - [3.4 Read (Single)](#34-read-single)
  - [3.5 Read (List - ListQuery Chaining)](#35-read-list---listquery-chaining)
  - [3.6 Read (List - get_list)](#36-read-list---get_list)
  - [3.7 Count](#37-count)
  - [3.8 Update](#38-update)
  - [3.9 Delete](#39-delete)
- [4) Public API Reference](#4-public-api-reference)
  - [4.1 Repository Instance Methods](#41-repository-instance-methods)
  - [4.2 ListQuery Chaining Methods](#42-listquery-chaining-methods)
- [5) BaseRepoFilter](#5-baserepofilter)
- [6) Mapping (schema Conversion) Options](#6-mapping-schema-conversion-options)
  - [6.1 Schema Validation Behavior When Using a Mapper](#61-schema-validation-behavior-when-using-a-mapper)
- [7) Performance Tests](#7-performance-tests)

---

## 0) Scope

- ORM: SQLAlchemy
- Schema: Pydantic
- Repository pattern: `BaseRepository[TModel]`
- Filter: `BaseRepoFilter` (dataclass-based)
- Query DSL: `ListQuery` chaining (`where → order_by → paging` or `with_cursor + limit`)

---

## 1) Model & Schema Definition

```python
# SQLAlchemy ORM
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]

# Pydantic schema
class UserSchema(BaseModel):
    id: int
    name: str
    email: str
    model_config = ConfigDict(from_attributes=True)
```

---

## 2) Repository Implementation

```python
@dataclass
class UserFilter(BaseRepoFilter):
    id: int | None = None
    name: str | None = None

class UserRepo(BaseRepository[User, UserSchema]): # (default) enables Schema(UserSchema) return by default
    filter_class = UserFilter
```

Options

* If you provide `mapper: type[BaseMapper] | None`, you can customize Schema ↔ ORM conversion rules.
* At instance construction time, you can override `mapping_schema`, `mapper`, and `default_convert_schema`.

---

## 3) Quick Start (Step-by-step)

## 3.1 Session Binding (Important)

BaseRepository session priority

1. If a `SessionProvider` is configured, the repo **always** uses `provider.get_session()`.
2. If no provider is configured, the repo uses the `session` passed to the repo constructor (specific session).
3. If neither exists, it raises a runtime error.

Additionally, if you pass `session=...` to any repository method call, that session has the **highest priority for that call**.

### 3.1.1 (Recommended) Provider-based Setup

```python
# Configure once during app initialization
UserRepo.configure_session_provider(session_provider)

# After that, the repo does not need to hold a session itself
repo = UserRepo()

rows = await repo.get_list(
    flt=UserFilter(name="A"),
    page=1,
    size=10,
)
```

### 3.1.2 (Option) Inject Session Per Call

```python
repo = UserRepo()

async with AsyncSession(engine) as session:
    rows = await repo.get_list(
        flt=UserFilter(name="A"),
        page=1,
        size=10,
        session=session,  # used only for this call
    )
```

### 3.1.3 (Option) Bind a Session to the Repo (No Provider)

```python
async with AsyncSession(engine) as session:
    repo = UserRepo(session=session)
    rows = await repo.get_list(flt=UserFilter(name="A"), page=1, size=10)
```

Notes

* If a provider is configured, passing `UserRepo(session=...)` is ignored (and a warning is emitted). The provider wins.

---

## 3.2 Transaction / Commit Responsibility (Important)

* BaseRepository never calls `commit()`.
* `create/create_many/create_from_model/update_from_model` only performs up to `flush()`.
* `update/delete/execute/get/get_list/count` does not perform `flush()` or `commit()`.
* Transaction boundaries (`commit/rollback`) are the caller’s responsibility (service/use-case/middleware).

---

## 3.3 Create (Single / Bulk)

```python
# Single: schema or dict
created = await repo.create(UserSchema(name="Alice", email="a@test.com"))
created2 = await repo.create({"name": "Bob", "email": "b@test.com"})

# Bulk
bulk = await repo.create_many([
    {"name": "C", "email": "c@test.com"},
    UserSchema(name="D", email="d@test.com"),
])

# ORM model directly
created3 = await repo.create_from_model(User(name="E", email="e@test.com"))
```

PK handling rules

* `create()` / `create_many()` ignore autoincrement PK input (columns-only payload + autoinc PK removal).
* `create_from_model()` adds + flushes the ORM object as-is, so if you set a PK, it may be included in the INSERT.

---

## 3.4 Read (Single)

```python
row = await repo.get(UserFilter(name="Alice"))  # default: Schema return (when mapping_schema is set)
row_raw = await repo.get(UserFilter(name="Alice"), convert_schema=False)  # ORM return
```

---

## 3.5 Read (List - ListQuery Chaining)

### OFFSET paging

```python
q = (
    repo.list(flt=UserFilter())
        .order_by([User.id.asc()])   # optional (may be auto-augmented by your implementation if omitted)
        .paging(page=1, size=20)     # page>=1, size>=1
)

# Or: where chaining
q = (
    repo.list()
        .where(UserFilter())
        .order_by([User.id.asc()])
        .paging(page=1, size=20)
)

rows = await repo.execute(q)         # SELECT always returns a list
```

### CURSOR (Keyset) paging

```python
# First page: None or {}
q1 = (
    repo.list()
        .order_by([User.id.asc()])   # must be set before cursor
        .with_cursor(None)
        .limit(20)                   # size>=1
)
rows1 = await repo.execute(q1)

# Next page
next_cursor = {"id": 123}
q2 = (
    repo.list()
        .order_by([User.id.asc()])
        .with_cursor(next_cursor)    # must match order_by column keys/order
        .limit(20)
)
rows2 = await repo.execute(q2)
```

### where usage pattern

```python
q = repo.list().where(UserFilter(id=1, name="Kyu"))

# Using both list(flt=...) and .where(...) may raise an exception in where(),
# because list() already set the filter.
```

### order_by input examples (supported shapes)

```python
# 1) string key
q = repo.list().order_by(["id"]).paging(page=1, size=10)

# 2) Enum.value (string) — example Enum
class SortKey(Enum):
    ID = "id"
    NAME = "name"
q = repo.list().order_by([SortKey.ID, SortKey.NAME]).paging(page=1, size=10)

# 3) model column attribute
q = repo.list().order_by([User.name]).paging(page=1, size=10)

# 4) asc()/desc()
q = repo.list().order_by([User.name.desc(), User.id.asc()]).paging(page=1, size=10)

# 5) ColumnElement (expression)
q = repo.list().order_by([User.name.expression]).paging(page=1, size=10)

# 6) default: omit order_by
q = repo.list().paging(page=1, size=10)
```

### Cursor dict example (multi-column)

```python
q = (
  repo.list()
     .order_by([User.id.asc(), User.name.desc()])
     .with_cursor({
         "id": 120,
         "name": "Z",
     })
     .limit(20)
)
rows = await repo.execute(q)
```

Not allowed

* Columns from other models, `func(...)`, `text("...")`, arbitrary types
* `None` values in cursor
* Cursor key set/order mismatch

---

## 3.6 Read (List - get_list)

### OFFSET paging

```python
rows = await repo.get_list(
    flt=UserFilter(name="A"),
    order_by=[User.id.asc()],
    page=1,
    size=10,
)

rows = await repo.get_list(
    flt=UserFilter(id=1, name="A"),
)

rows = await repo.get_list(
    order_by=["id", User.name.desc()],
    page=2,
    size=10,
)

rows = await repo.get_list(page=1, size=10)
```

### CURSOR (Keyset) paging

```python
rows1 = await repo.get_list(
    order_by=[User.id.asc()],
    cursor={},   # or None (still keyset mode)
    size=10,
)

rows2 = await repo.get_list(
    order_by=[User.id.asc(), User.name.desc()],
    cursor={"id": 120, "name": "Z"},
    size=10,
)
```

get_list composition rules

1. If you pass `cursor` (including None), it runs in keyset paging mode.

* `order_by` is required
* `size` is required (keyset limit)

2. If you provide both `page` and `size`, it runs in offset paging mode.

3. Otherwise, no paging is applied.

* Avoid passing only `page` since it does not page anything.

---

## 3.7 Count

```python
cnt = await repo.count(UserFilter(name="Alice"))
```

---

## 3.8 Update

```python
# Bulk UPDATE (single UPDATE SQL)
updated = await repo.update(UserFilter(name="Bob"), {"email": "bob@new"})

# Dirty Checking on a persistent object
obj = await repo.get(UserFilter(name="Alice"), convert_schema=False)
updated_Schema = await repo.update_from_model(obj, {"email": "alice@new"})
```

---

## 3.9 Delete

```python
deleted = await repo.delete(UserFilter(name="Alice"))
```

---

## 4) Public API Reference

## 4.1 Repository Instance Methods

* `configure_session_provider(provider: SessionProvider) -> None` (class method)

  * If a provider is configured, the repo pulls sessions from the provider.

* `session -> AsyncSession` (property)

  * Uses provider session if present, otherwise uses the repo’s bound specific session.

* `list(flt: BaseRepoFilter | None = None) -> ListQuery`

  * DSL entrypoint for list queries.

* `execute(q_or_stmt, *, session=None, convert_schema=None)`

  * Executes `ListQuery` or a statement.
  * SELECT always returns a `list`.

* `get(flt, *, convert_schema=None, session=None)` / `get_or_fail(...)`

  * Single-row read.

* `get_list(*, flt=None, order_by=None, cursor=None, page=None, size=None, session=None, convert_schema=None)`

  * Convenience method; builds a `ListQuery` internally and calls `execute()`.

* `count(flt=None, *, session=None)` / `delete(flt, *, session=None)`

  * Count / delete.

* `add(obj, *, session=None)` / `add_all(objs, *, session=None)`

  * Only adds to session. Caller controls flush/commit.

* `create(data, *, session=None, convert_schema=None)` /
  `create_many(items, *, session=None, convert_schema=None)` /
  `create_from_model(obj, *, session=None, convert_schema=None)`

  * Insert + flush.
  * `create/create_many` ignore autoincrement PK input.
  * `create_from_model` uses ORM object as-is, so a set PK may be included in INSERT.

* `update(flt, update, *, session=None)`

  * Bulk update via a single UPDATE SQL. Returns rowcount.

* `update_from_model(base, update, *, session=None, convert_schema=None)`

  * Applies values to a persistent object and flushes. Returns Schema or ORM.

---

## 4.2 ListQuery Chaining Methods

* `.where(flt: BaseRepoFilter | None) -> ListQuery`

  * Can be set only once. Ignored if None.

* `.order_by(items: Sequence[Any]) -> ListQuery`

  * Must be called before entering cursor mode.
  * Allowed: string key ("id"), `Enum.value`(string), model column attributes, `asc()/desc()`, column `expression`.
  * Not allowed: other-model/join columns, `func(...)`, `text("...")`, arbitrary types.

* `.with_cursor(cursor: dict[str, Any] | None = None) -> ListQuery`

  * Enters cursor mode. `None`/`{}` means first page.
  * Requires prior `order_by(...)` (non-empty).
  * Cursor rule: key set and order must match `order_by`; values cannot be None.

* `.limit(size: int) -> ListQuery`

  * Cursor page size. `size>=1`. Cannot be combined with offset paging.

* `.paging(*, page: int, size: int) -> ListQuery`

  * Offset paging. `page>=1`, `size>=1`. Only once. Cannot be combined with cursor mode.

---

## 5) BaseRepoFilter

* Converts dataclass fields into WHERE criteria automatically

Rules

* `bool` -> `.is_(val)`
* sequence -> `.in_(...)` (empty sequences are skipped)
* single value -> `==`
* `__aliases__` maps field name -> column name
* `__strict__ = True` raises if mapping fails

Example

```python
@dataclass
class UserFilter(BaseRepoFilter):
    id: int | list[int] | None = None
    active: bool | None = None
    __aliases__ = {"org_ids": "org_id"}
```

* To filter by multiple ids, use `UserFilter(id=[1, 2, 3])`.
* BaseRepoFilter detects sequence types and translates them into an IN condition automatically.

---

## 6) Mapping (Schema Conversion) Options

* If `mapping_schema` is set, the default return is Schema (Pydantic)
* You can return ORM objects by passing `convert_schema=False`
* If you set a `BaseMapper`, you can customize Schema ↔ ORM conversions

Example

```python
class UserMapper(BaseMapper):
    def to_schema(self, db: User) -> UserSchema:
        return UserSchema(id=db.id, name=db.name, email="Changed")

    def to_orm(self, dm: UserSchema) -> User:
        return User(**dm.model_dump(exclude=["name"]), name="fixed")

class UserRepo(BaseRepository[User, UserSchema]):
    filter_class = UserFilter
    mapper = UserMapper

row = await repo.get(UserFilter(id=1))
assert row.email == "Changed"
```

### 6.1 Schema Validation Behavior When Using a Mapper

When you set `mapper(BaseMapper)`, BaseRepository does not validate a strict 1:1 match between
`mapping_schema` field names and ORM model column names.

Intent

* Allow mapping schema fields with different names
* Allow custom conversions such as combining multiple fields into a single column

Summary

```python
class UserRepo(BaseRepository[User, UserSchema]):
    filter_class = UserFilter
    mapper = UserMapper  # if mapper exists, column-only strict validation is disabled
```

---

## 7) Performance Tests

Command list

* Check the Makefile targets.

* `perf-list`

  * Prints previously executed RUN_ID list
  * Results are stored as jsonl under `tests/perf/results`

* `perf-cpu`

  * Runs CPU-bound tests

* `perf-db`

  * Runs DB-included tests (requires Docker)

* `perf-view`

  * Visualizes the most recent RUN_ID as graphs
  * Add `RUN_ID={RUN_ID}` to visualize a specific run

Configuration

1. CPU

* You can change `ROW_VALUES` and `ITERATIONS` near the top of `tests/perf/perf_cpu_only.py`.

2. DB

* You can change `SEED_DATA_ROWS` in `tests/perf/seed.config.py`.
* If you change table fields or data rules, you must also update the tests (currently not designed to be flexible).

