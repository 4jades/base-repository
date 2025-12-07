<div align="right">
  <a href="./README.md">English</a> | <a href="./README.ko.md">한국어</a>
</div>

# Base Repository

![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-informational)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![License](https://img.shields.io/github/license/4jades/base-repository)


A repository library that wraps SQLAlchemy and provides built-in CRUD and a query DSL.    
Once you inherit from `BaseRepository`, you can use create/read/update/delete right away.

- No need to re-implement simple CRUD over and over.
- If you need custom repo methods, you can add them in your project and extend freely.
- Supports introducing a Mapper for conversions between Pydantic schemas and SQLAlchemy ORM models.

## Supported Dependency Versions

The table below lists the minimum required versions for each supported dependency.

To see more about [how to test](./tox.ini) and the [result](./docs/dependency_test.md).

| python_version | sqlalchemy         | pydantic          |
|----------------|--------------------|-------------------|
| 3.10           | >= 1.4             | >= 1.10           |
| >= 3.13        | >= 1.4             | >= 2.8, 1.7-1.10  |



## Links
- [How to use](https://4jades.github.io/base-repository/how_to_use.html)
- [Performance](https://4jades.github.io/base-repository/about_performance.html)

---

## Installation

```bash
not yet
```

---

## Quick Start

### 1) Define Filter and Repo

```python
from dataclasses import dataclass
from pydantic import BaseModel
from base_repository import BaseRepoFilter
from base_repository.repository import BaseRepository

# Example: existing SQLAlchemy ORM model and Pydantic schema in your project
class Base(DeclarativeBase):
    pass

class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)

class UserSchema(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


# What you need to add for Base Repository: Filter + Repo
@dataclass
class UserFilter(BaseRepoFilter):
    id: int | iterable[int] | None = None
    name: str | iterable[str] | None = None

class UserRepo(BaseRepository[UserModel]):
    filter_class = UserFilter
    mapping_schema = UserSchema  # Optional: return Pydantic objects by default
```

### 2) Plug in a SessionProvider

Decide how the repository should obtain an `AsyncSession`.    
Recommended: inject a `SessionProvider` once, so the repo can fetch sessions when needed.

```python
from typing import Protocol
from base_repository import SessionProvider, BaseRepository

# Example SessionProvider implementation
class MysqlSessionProvider(SessionProvider):
    def get_session(self) -> AsyncSession:
        return Mysql.current_session()

BaseRepository.configure_session_provider(MysqlSessionProvider())
```

Alternatively, you can pass a session directly when creating the repo.

```python
async with AsyncSession(engine) as session:
    repo = UserRepo(session)
```

### 3) Use CRUD immediately

```python
repo = UserRepo()

# Create
created = await repo.create({"name": "Alice", "email": "a@test.com"})

# Get one
user = await repo.get(UserFilter(name=["Alice", "Bob"]))
user_orm = await repo.get(UserFilter(name="Alice"), convert_domain=False)

# List (OFFSET paging)
q = (
    repo.list()
        .where(UserFilter(name="A"))
        .order_by(["id"])
        .paging(page=1, size=20)
)
users = await repo.execute(q)

# List (CURSOR paging)
q1 = (
    repo.list()
        .order_by(["id"])
        .with_cursor(None)
        .limit(20)
)
users1 = await repo.execute(q1)

# Update / Delete / Count
cnt = await repo.count(UserFilter(name="Alice"))
updated_rows = await repo.update(UserFilter(name="Bob"), {"email": "bob@new"})
deleted_rows = await repo.delete(UserFilter(name="Alice"))
```

---
